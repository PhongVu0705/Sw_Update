"""
Software Update Tool — pywebview entry point.

Serves the static frontend (../frontend/index.html) inside a native window
and exposes a JavaScript API (window.pywebview.api.*) for:
  - COM port listing / connect / disconnect
  - Native file selection (.bin / .csv)
  - Firmware update dispatch (BIN flashing or CSV command replay)
  - Automatic post-update FW version verification (PASS / FAIL)
  - Manual hex commands and quick commands
"""

import json
import os
import re
import shutil
import threading
import time

import webview

import app_paths

import command_runner  # module-level last_rx_frame access for mass polling
from opelink_comm import OpenLinkComm, list_ports
from command_runner import (
    execute_bin_flashing_sequence,
    execute_command_list,
    on_rx_callback,
    on_tx_callback,
    print_queued_messages,
    send_and_get_final_rx,
)
from csv_processor import get_commands_from_csv
from script_builder import SeqIdTracker, build_frame, generate_and_save_bin_script

FRONTEND_INDEX = app_paths.frontend_index()
TEMP_DIR = os.path.join(app_paths.writable_base(), "temp")

DEBUG_MODE = False
SPLASH_WATCHDOG_SECONDS = 20.0
BAUD_RATE = 115200

FW_CHECK_CMD = "01 00 03 00 0D 04 00 15"
FW_CHECK_DELAY_S = 3.0

FW_DATA_START = 3
FW_DATA_LENGTH = 4

# Mass Update Headers
TARGET_ACK_HEADERS = (0x80, 0x81)
TARGET_UNPLUG_HEADERS = (0x82, 0x83)

QUICK_COMMANDS = {
    "fw_version": "01 00 03 00 0D 04 00 15",
    "mpbid": "01 00 03 00 04 05 00 0D",
    "fw_pn": "01 00 03 00 09 04 00 11",
    "calibration": "01 00 03 61 00 FA 01 5F",
    "target_m18": "70 01 01 01 00 73",
    "target_m12": "70 01 01 11 00 83",
    "metco_password": "01 01 0A 00 3B 33 33 33 33 33 33 33 33 01 DF",
    "wipe_counters": "01 01 03 A0 1D 01 00 C3",
}

QUICK_TITLES = {
    "fw_version": "Check FW Version",
    "mpbid": "Check MPBID",
    "fw_pn": "Check FW P/N",
    "calibration": "Read Data Calibration",
    "target_m18": "Target M18",
    "target_m12": "Target M12",
    "metco_password": "Send Default METCO Password",
    "wipe_counters": "Wipe Counters And Histograms",
}


class RunController:
    """Cooperative pause/stop control checked from progress callbacks."""

    def __init__(self):
        self._pause = threading.Event()
        self._stop = threading.Event()

    def reset(self):
        self._pause.clear()
        self._stop.clear()

    def pause(self):
        self._pause.set()

    def resume(self):
        self._pause.clear()

    def stop(self):
        self._stop.set()

    def checkpoint(self):
        """Block while paused; raise to abort the run when stopped."""
        while self._pause.is_set() and not self._stop.is_set():
            time.sleep(0.1)
        if self._stop.is_set():
            raise RuntimeError("Aborted by operator")

    def stop_requested(self) -> bool:
        """Non-blocking stop check usable inside retry loops."""
        return self._stop.is_set()


def sanitize_log(message: str) -> str:
    cleaned = "".join(ch for ch in str(message) if ch.isascii())
    return " ".join(cleaned.split())


def normalize_version(value: str) -> str:
    parts = [p.strip() for p in str(value).strip().split(".") if p.strip() != ""]
    while len(parts) > 1 and parts[-1] == "0":
        parts.pop()
    return ".".join(parts)


class JSAPI:
    """JavaScript API exposed to the frontend as window.pywebview.api."""

    def __init__(self):
        self.comm: OpenLinkComm = None
        self._window = None
        self.is_connected = False
        self.connected_port = None
        self.controller = RunController()
        self.mass_running = False

    def set_window(self, window):
        self._window = window

    def _push(self, event: str, *args):
        if not self._window:
            return
        try:
            payload = ", ".join(json.dumps(a) for a in args)
            self._window.evaluate_js(
                f"window.{event} && window.{event}({payload});"
            )
        except Exception:
            pass

    def log(self, message: str):
        clean = sanitize_log(message)
        try:
            print(clean)
        except Exception:
            pass
        self._push("onLogFromPy", clean)

    def report_progress(self, ratio: float, current: int, total: int):
        self._push("onProgressFromPy", round(ratio * 100, 2), current, total)

    def _push_connection(self):
        self._push(
            "onConnectionState",
            {"connected": self.is_connected, "port": self.connected_port},
        )

    def _guarded_progress(self, ratio: float, current: int, total: int):
        self.controller.checkpoint()
        self.report_progress(ratio, current, total)

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------
    def get_ports(self):
        try:
            return {"status": "SUCCESS", "ports": list_ports()}
        except Exception as e:
            return {"status": "ERROR", "message": str(e)}

    def get_connection_state(self):
        return {"connected": self.is_connected, "port": self.connected_port}

    def connect_port(self, port: str, baud_rate: int = BAUD_RATE):
        if self.is_connected:
            self.disconnect_port()

        port_name = str(port).split(" - ")[0].strip()

        try:
            self.comm = OpenLinkComm(
                port=port_name,
                baud_rate=int(baud_rate),
                on_rx=on_rx_callback,
                on_tx=on_tx_callback,
            )

            if self.comm.connect():
                self.is_connected = True
                self.connected_port = port_name
                self._push_connection()
                self.log(f"Connected to {port_name} at {baud_rate} baud.")
                return {"status": "SUCCESS", "message": f"Connected to {port_name}"}
        except Exception as e:
            self.log(f"Connection exception on {port_name}: {e}")

        self.comm = None
        self.is_connected = False
        self.connected_port = None
        self._push_connection()
        self.log(f"Failed to connect to {port_name}")
        return {"status": "ERROR", "message": f"Failed to connect to {port_name}"}

    def disconnect_port(self):
        if self.comm:
            try:
                self.comm.disconnect()
            except Exception as e:
                self.log(f"Error during disconnect: {e}")
            finally:
                self.comm = None
        self.is_connected = False
        self.connected_port = None
        self._push_connection()
        self.log("Disconnected from COM port.")
        return {"status": "SUCCESS"}

    # ------------------------------------------------------------------
    # File selection
    # ------------------------------------------------------------------
    def select_file(self):
        if not self._window:
            return {"status": "ERROR", "message": "File dialog unavailable"}

        result = self._window.create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=False,
            file_types=(
                "Firmware Files (*.bin;*.csv)",
                "All Files (*.*)",
            ),
        )
        if not result:
            return {"status": "CANCELLED"}

        path = result[0]
        name = os.path.basename(path)
        ext = os.path.splitext(name)[1].lower().lstrip(".")
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0

        return {"status": "SUCCESS", "path": path, "name": name, "size": size, "ext": ext}

    # ------------------------------------------------------------------
    # Update dispatch (BIN or CSV) + automatic FW verification
    # ------------------------------------------------------------------
    def run_update(self, file_path: str, tool_type: str = "M12", expected_fw: str = ""):
        if not self.is_connected or not self.comm:
            return {"status": "ERROR", "message": "Serial port not connected"}

        file_path = str(file_path).strip().strip("\"'")
        if not os.path.exists(file_path):
            return {"status": "ERROR", "message": f"File does not exist: {file_path}"}

        ext = os.path.splitext(file_path)[1].lower().lstrip(".")
        if ext not in ("bin", "csv"):
            return {"status": "ERROR", "message": "Unsupported file type — choose a .bin or .csv file"}

        tool_type = "M18" if str(tool_type).upper() == "M18" else "M12"
        expected_fw = str(expected_fw).strip()
        if expected_fw and not re.fullmatch(r"\d+(\.\d+){0,3}", expected_fw):
            return {
                "status": "ERROR",
                "message": "Invalid FW version format — use decimal numbers separated by dots, e.g. 1.4.2",
            }

        self.controller.reset()
        threading.Thread(
            target=self._update_worker,
            args=(file_path, ext, tool_type, expected_fw),
            daemon=True,
        ).start()
        return {"status": "STARTED"}

    def _update_worker(self, file_path: str, ext: str, tool_type: str, expected_fw: str):
        update_ok = False
        fail_reason = ""

        try:
            self.log("=" * 60)
            self.log(
                f"STARTING UPDATE — {os.path.basename(file_path)} "
                f"({ext.upper()}, Tool: {tool_type})"
            )
            self.log("=" * 60)

            if ext == "bin":
                self.log("\nGenerating flashing script from BIN file...")
                script_data = generate_and_save_bin_script(
                    file_path, tool_type=tool_type, log_callback=self.log
                )
                if not script_data:
                    raise RuntimeError("Failed to process BIN file / generate script")

                self.log("\nStarting flashing sequence...")
                update_ok = execute_bin_flashing_sequence(
                    self.comm,
                    script_data,
                    log_callback=self.log,
                    progress_callback=self._guarded_progress,
                )
                if not update_ok:
                    fail_reason = "Flashing sequence failed"
            else:
                self.log("\nProcessing CSV command filter...")
                csv_cmds = get_commands_from_csv(
                    file_path, prefix="74", log_callback=self.log
                )
                if not csv_cmds:
                    raise RuntimeError("No valid commands found in CSV")

                init_cmds = []
                cmd1_base = "70 01 01 11" if tool_type == "M12" else "70 01 01 01"
                init_cmds.append(build_frame(cmd1_base))

                seq = SeqIdTracker(start=5)
                init_cmds.append(
                    build_frame(f"01 {seq.get_and_inc()} 0A 00 3B 33 33 33 33 33 33 33 33")
                )

                full_cmds = init_cmds + csv_cmds
                self.log(
                    f"Sending {len(full_cmds)} commands "
                    f"(2 init + {len(csv_cmds)} CSV commands)...",
                )
                update_ok = execute_command_list(
                    self.comm,
                    full_cmds,
                    log_callback=self.log,
                    progress_callback=self._guarded_progress,
                )
                if not update_ok:
                    fail_reason = "CSV command execution failed"

        except RuntimeError as e:
            update_ok = False
            fail_reason = str(e)
        except Exception as e:
            update_ok = False
            fail_reason = f"Unexpected error: {e}"

        detected_fw = None
        check_state = None

        if update_ok:
            if expected_fw:
                self.log(f"Update done - waiting {FW_CHECK_DELAY_S:.0f} s before FW check...")
                time.sleep(FW_CHECK_DELAY_S)

                self.log("Verifying firmware version...")
                check = self.verify_fw_version(expected_fw)
                detected_fw = check.get("detected")
                check_state = check["pass"]
            else:
                self.log("\nNo expected FW version provided — skipping verification.")
        elif not fail_reason:
            fail_reason = "Update failed"

        overall = "PASS" if update_ok else "FAIL"

        if overall == "PASS":
            self.log("\n=== UPDATE FINISHED: PASS ===")
            if check_state is True:
                self.log(f"FW version verified: {detected_fw}")
            elif check_state is False:
                self.log(
                    f"WARNING: FW version check FAILED - "
                    f"detected {detected_fw}, expected {expected_fw}"
                )
        else:
            self.log(f"\n=== UPDATE FINISHED: FAIL — {fail_reason} ===")

        self._push(
            "onUpdateFinished",
            {
                "status": overall,
                "reason": "" if overall == "PASS" else fail_reason,
                "fwCheck": {
                    "pass": check_state,
                    "detected": detected_fw,
                    "expected": expected_fw or None,
                },
            },
        )

    def verify_fw_version(self, expected_fw: str):
        rx = send_and_get_final_rx(
            self.comm, FW_CHECK_CMD, timeout_ms=10000, log_callback=self.log
        )
        if rx is None:
            return {"pass": False, "detected": None, "reason": "Timeout waiting for FW version response"}

        first_byte = rx[0]
        if first_byte in (0x82, 0x83):
            return {"pass": False, "detected": None, "reason": "Device reported: cannot get data"}
        if first_byte not in (0x80, 0x81):
            return {
                "pass": False,
                "detected": None,
                "reason": f"Unexpected response header: {rx.hex(' ').upper()}",
            }
        if len(rx) < FW_DATA_START + FW_DATA_LENGTH:
            return {"pass": False, "detected": None, "reason": "Response too short to contain version data"}

        segments = [str(rx[i]) for i in range(FW_DATA_START, FW_DATA_START + FW_DATA_LENGTH)]
        detected = ".".join(segments)

        passed = normalize_version(detected) == normalize_version(expected_fw)
        return {
            "pass": passed,
            "detected": detected,
            "reason": "" if passed else "FW version mismatch",
        }

    # ------------------------------------------------------------------
    # Mass update: New State Machine Flow
    # ------------------------------------------------------------------
    def run_mass_update(
        self, port: str, file_path: str, tool_type: str = "M12", expected_fw: str = ""
    ):
        if self.mass_running:
            return {"status": "ERROR", "message": "A mass update is already running"}

        if not self.is_connected or not self.comm:
            return {"status": "ERROR", "message": "Connect to the selected COM port before starting"}

        if not port or not str(port).strip():
            return {"status": "ERROR", "message": "No COM port selected"}

        file_path = str(file_path).strip().strip("\"'")
        if not os.path.exists(file_path):
            return {"status": "ERROR", "message": f"File does not exist: {file_path}"}

        ext = os.path.splitext(file_path)[1].lower().lstrip(".")
        if ext not in ("bin", "csv"):
            return {
                "status": "ERROR",
                "message": "Unsupported file type — choose a .bin or .csv file",
            }

        tool_type = "M18" if str(tool_type).upper() == "M18" else "M12"

        expected_fw = str(expected_fw).strip()
        if not expected_fw:
            return {
                "status": "ERROR",
                "message": "Fw version check is REQUIRED - enter the expected firmware version to run.",
            }
        if not re.fullmatch(r"\d+(\.\d+){0,3}", expected_fw):
            return {
                "status": "ERROR",
                "message": "Invalid FW version format — use decimal numbers separated by dots, e.g. 1.4.2",
            }

        port_name = str(port).split(" - ")[0].strip()
        if port_name != self.connected_port:
            return {"status": "ERROR", "message": "Selected COM port is not connected"}

        self.controller.reset()
        self.mass_running = True
        threading.Thread(
            target=self._continuous_mass_update_worker,
            args=(port_name, file_path, ext, tool_type, expected_fw),
            daemon=True,
        ).start()
        return {"status": "STARTED"}

    def _wait_with_cancel(self, seconds: float):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.controller.checkpoint()
            time.sleep(min(0.1, deadline - time.monotonic()))

    def _flash_and_verify_mass_target(self, file_path, ext, tool_type, expected_fw):
        try:
            self._push("onMassStage", "programming")
            if ext == "bin":
                script_data = generate_and_save_bin_script(
                    file_path, tool_type=tool_type, log_callback=self.log
                )
                if not script_data:
                    return {"pass": False, "detected": None, "reason": "Failed to generate BIN flashing script"}
                update_ok = execute_bin_flashing_sequence(
                    self.comm, script_data, log_callback=self.log,
                    progress_callback=self._guarded_progress,
                )
            else:
                csv_cmds = get_commands_from_csv(file_path, prefix="74", log_callback=self.log)
                if not csv_cmds:
                    return {"pass": False, "detected": None, "reason": "No valid commands found in CSV"}
                target_base = "70 01 01 11" if tool_type == "M12" else "70 01 01 01"
                seq = SeqIdTracker(start=5)
                init_cmds = [
                    build_frame(target_base),
                    build_frame(f"01 {seq.get_and_inc()} 0A 00 3B 33 33 33 33 33 33 33 33"),
                ]
                update_ok = execute_command_list(
                    self.comm, init_cmds + csv_cmds, log_callback=self.log,
                    progress_callback=self._guarded_progress,
                )

            if not update_ok:
                return {"pass": False, "detected": None, "reason": "Flashing sequence failed"}

            self._push("onMassStage", "verifying")
            self._wait_with_cancel(FW_CHECK_DELAY_S)
            check = self.verify_fw_version(expected_fw)
            return {
                "pass": bool(check.get("pass")),
                "detected": check.get("detected"),
                "reason": check.get("reason") or "FW verification failed",
            }
        except RuntimeError:
            raise
        except Exception as exc:
            return {"pass": False, "detected": None, "reason": f"Update error: {exc}"}

    def _send_target_and_get_rx(self, tool_type: str, timeout_s: float = 0.5):
        """Sends single target command and waits for response byte[0] safely."""
        target_base = "70 01 01 01" if tool_type == "M18" else "70 01 01 11"
        target_frame = bytes.fromhex(build_frame(target_base))
        
        command_runner.last_rx_frame = None
        if not self.comm or not self.comm.send_no_wait(target_frame):
            return None

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self.controller.stop_requested():
                raise RuntimeError("Aborted by operator")
            time.sleep(0.05)
            print_queued_messages(self.log)
            rx = command_runner.last_rx_frame
            if rx and len(rx) > 0:
                return rx
        return None

    def _continuous_mass_update_worker(self, port_name, file_path, ext, tool_type, expected_fw):
        """
        Implementation of the Refactored Mass Update Flow:
        - Post-update close port & 1s delay
        - State WAIT_UNPLUG_LOOP (Cycling Port)
        - State WAIT_NEXT_TARGET_LOOP (Strict debounce with >= 3x 82/83)
        """
        terminal_reason = ""
        try:
            self.log(f"Continuous mass update loop active on {port_name}.")
            
            while not self.controller.stop_requested():
                # --- STAGE 1: Flash & Verify current target ---
                self.log("\n--- STARTING FLASH & VERIFY SEQUENCE ---")
                result = self._flash_and_verify_mass_target(file_path, ext, tool_type, expected_fw)
                self._push("onMassResult", {**result, "expected": expected_fw})
                
                if result["pass"]:
                    self.log(f"MASS UPDATE PASS: FW {result.get('detected') or '?'}")
                else:
                    self.log(f"MASS UPDATE FAIL: {result.get('reason') or 'unknown error'}")

                # --- STAGE 2: Post-Update Disconnect & Delay ---
                self.log("Post-Update: Closing Serial Port & Waiting 1.0s to clear hardware buffer...")
                self.disconnect_port()
                self._wait_with_cancel(1.0)

                # --- STAGE 3: [WAIT_UNPLUG_LOOP] (Cycling Port Connection) ---
                self._push("onMassStage", "waiting_for_unplug")
                self.log("Entering WAIT_UNPLUG_LOOP (Cycling port connection)...")

                while not self.controller.stop_requested():
                    # Step A: Open port safely
                    try:
                        self.comm = OpenLinkComm(
                            port=port_name,
                            baud_rate=BAUD_RATE,
                            on_rx=on_rx_callback,
                            on_tx=on_tx_callback,
                        )
                        if not self.comm.connect():
                            raise IOError("Port open failed")
                        self.is_connected = True
                        self.connected_port = port_name
                        self._push_connection()
                    except Exception as e:
                        self.log(f"Failed to open port {port_name}: {e}. Retrying in 1.0s...")
                        self.disconnect_port()
                        self._wait_with_cancel(1.0)
                        continue

                    # Step B & C: Send target once & check Rx
                    rx = self._send_target_and_get_rx(tool_type, timeout_s=0.5)
                    first_byte = rx[0] if rx else None

                    if first_byte in TARGET_ACK_HEADERS:
                        self.log(f"[MCU RX]: {first_byte:02X} - Target still attached. Closing port & waiting 1.0s...")
                        self.disconnect_port()
                        self._wait_with_cancel(1.0)
                    elif first_byte in TARGET_UNPLUG_HEADERS:
                        self.log(f"[MCU RX]: {first_byte:02X} - Unplug/Ready response detected! Keeping port OPEN.")
                        break
                    else:
                        header_str = f"{first_byte:02X}" if first_byte is not None else "Timeout"
                        self.log(f"[MCU RX]: {header_str} - No target ACK. Re-cycling port...")
                        self.disconnect_port()
                        self._wait_with_cancel(1.0)

                # --- STAGE 4: [WAIT_NEXT_TARGET_LOOP] (Continuous Polling & Debounce) ---
                self._push("onMassStage", "waiting_for_next_target")
                self.log("Entering WAIT_NEXT_TARGET_LOOP (Continuous polling with strict debounce)...")

                consecutive_nack_counter = 1  # First 0x82/0x83 count from Stage 3
                ready_to_flash = False

                while not self.controller.stop_requested():
                    self._wait_with_cancel(0.5)
                    rx = self._send_target_and_get_rx(tool_type, timeout_s=0.5)
                    first_byte = rx[0] if rx else None

                    if first_byte in TARGET_UNPLUG_HEADERS:
                        consecutive_nack_counter += 1
                        self.log(f"Target unplug status {first_byte:02X}: {consecutive_nack_counter}/3 consecutive.")
                        if consecutive_nack_counter >= 3:
                            if not ready_to_flash:
                                self.log("READY_TO_FLASH = TRUE. Place next PCBA target.")
                            ready_to_flash = True
                    elif first_byte in TARGET_ACK_HEADERS:
                        if ready_to_flash:
                            self.log(f"New PCBA detected with header {first_byte:02X}! Starting update sequence.")
                            break
                        else:
                            self.log(f"Header {first_byte:02X} received, but debounce counter ({consecutive_nack_counter}/3) insufficient. Resetting counter.")
                            consecutive_nack_counter = 0
                    else:
                        header_str = f"{first_byte:02X}" if first_byte is not None else "Timeout"
                        self.log(f"Unexpected response ({header_str}). Resetting debounce counter to 0.")
                        consecutive_nack_counter = 0
                        ready_to_flash = False

        except RuntimeError as exc:
            terminal_reason = str(exc)
        except Exception as exc:
            terminal_reason = f"Unexpected mass update error: {exc}"
        finally:
            stopped = self.controller.stop_requested()
            self.mass_running = False
            self.controller.reset()
            self.disconnect_port()
            self._push("onMassStage", "done")
            self._push("onMassFinished", {"stopped": stopped, "reason": terminal_reason})
            if stopped:
                self.log("Continuous mass update stopped by operator.")
            elif terminal_reason:
                self.log(f"Continuous mass update ended: {terminal_reason}")

    # ------------------------------------------------------------------
    # Run controls
    # ------------------------------------------------------------------
    def pause_update(self):
        self.controller.pause()
        self.log("Update paused.")
        return {"status": "SUCCESS"}

    def resume_update(self):
        self.controller.resume()
        self.log("Update resumed.")
        return {"status": "SUCCESS"}

    def stop_update(self):
        self.controller.stop()
        self.log("Stop requested — aborting update...")
        return {"status": "SUCCESS"}

    # ------------------------------------------------------------------
    # Manual commands
    # ------------------------------------------------------------------
    def run_hex_command(self, hex_cmd: str):
        if not self.is_connected or not self.comm:
            return {"status": "ERROR", "message": "Serial port not connected"}

        hex_cmd = str(hex_cmd).strip()
        if not hex_cmd:
            return {"status": "ERROR", "message": "Empty command"}

        self.log(f"\n--- Running Hex Command: {hex_cmd} ---")
        ok = execute_command_list(self.comm, [hex_cmd], log_callback=self.log)
        if ok:
            self.log("Command executed successfully.")
            return {"status": "SUCCESS", "message": "Command executed"}
        return {"status": "ERROR", "message": "Command failed or timed out"}

    def run_quick_command(self, cmd_type: str):
        if not self.is_connected or not self.comm:
            return {"status": "ERROR", "message": "Serial port not connected"}

        cmd = QUICK_COMMANDS.get(cmd_type)
        if not cmd:
            return {"status": "ERROR", "message": f"Unknown quick command: {cmd_type}"}

        title = QUICK_TITLES.get(cmd_type, cmd_type)

        def quick_log(message):
            text = str(message)
            stripped = text.strip()
            if stripped.startswith("--- [TX]") or stripped.startswith("QUICK COMMAND"):
                return
            self.log(text)

        if cmd_type == "calibration":
            self.log("Sending default METCO password before reading calibration data...")
            auth_rx = send_and_get_final_rx(
                self.comm,
                QUICK_COMMANDS["metco_password"],
                timeout_ms=10000,
                log_callback=quick_log,
            )
            if auth_rx is None:
                return {
                    "status": "TIMEOUT",
                    "title": title,
                    "result": "Timeout waiting for METCO password response",
                }
            if auth_rx[0] in (0x82, 0x83):
                return {
                    "status": "ERROR",
                    "title": title,
                    "result": "Cannot get data (METCO password)",
                }

        rx = send_and_get_final_rx(
            self.comm, cmd, timeout_ms=10000, log_callback=quick_log
        )
        if rx is None:
            return {"status": "TIMEOUT", "title": title, "result": "Timeout or no response from MCU!"}

        first_byte = rx[0]
        if first_byte in (0x82, 0x83):
            return {"status": "ERROR", "title": title, "result": "Cannot get data"}
        if first_byte not in (0x80, 0x81):
            return {
                "status": "ERROR",
                "title": title,
                "result": f"Unexpected response: {rx.hex(' ').upper()}",
            }

        parsed = self._parse_quick_response(cmd_type, rx)
        if parsed is None:
            return {"status": "NO_DATA", "title": title, "result": "Command executed (no data)"}

        return {"status": "SUCCESS", "title": title, "result": parsed}

    @staticmethod
    def _parse_quick_response(cmd_type: str, rx: bytes):
        data_len = rx[2] if len(rx) >= 3 else max(0, len(rx) - 3)
        data = rx[3 : 3 + data_len]

        if not data:
            return None

        if cmd_type == "fw_version":
            return "FW Version: " + ".".join(str(byte) for byte in data)

        if cmd_type == "fw_pn":
            dec_value = int(data.hex(), 16)
            return f"FW P/N (Decimal): {dec_value}"

        return f"Data: {data.hex(' ').upper()}"


# ----------------------------------------------------------------------
# Cleanup
# ----------------------------------------------------------------------
def cleanup_on_exit(api: "JSAPI"):
    try:
        if api.is_connected and api.comm:
            api.comm.disconnect()
            print("Disconnected from COM port.")
    except Exception as e:
        print(f"Unable to disconnect COM port: {e}")

    try:
        if os.path.exists(TEMP_DIR):
            shutil.rmtree(TEMP_DIR)
            print("Temp folder deleted successfully.")
    except Exception as e:
        print(f"Unable to delete temp folder: {e}")


# ----------------------------------------------------------------------
# Boot splash
# ----------------------------------------------------------------------
def close_boot_splash():
    try:
        import pyi_splash

        pyi_splash.close()
    except Exception:
        pass


# ----------------------------------------------------------------------
# Application entry point
# ----------------------------------------------------------------------
def main():
    api = JSAPI()

    window = webview.create_window(
        title="FW Update Tool",
        url=FRONTEND_INDEX,
        js_api=api,
        width=1280,
        height=800,
        min_size=(1024, 700),
        resizable=True,
    )

    api.set_window(window)

    splash_watchdog = threading.Timer(SPLASH_WATCHDOG_SECONDS, close_boot_splash)
    splash_watchdog.daemon = True

    def _on_window_shown():
        splash_watchdog.cancel()
        close_boot_splash()

    window.events.shown += _on_window_shown
    splash_watchdog.start()

    window.events.closed += lambda: cleanup_on_exit(api)

    webview.start(debug=DEBUG_MODE)


if __name__ == "__main__":
    main()