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

# Bundled frontend (resolved from sys._MEIPASS when frozen) and the
# writable temp folder (next to the .exe when frozen, backend/ in dev).
FRONTEND_INDEX = app_paths.frontend_index()
TEMP_DIR = os.path.join(app_paths.writable_base(), "temp")

# Disable devtools in packaged builds
DEBUG_MODE = False

# Force-close the PyInstaller boot splash after this many seconds even if
# the main window never fires 'shown' (a stuck splash would block the UI).
SPLASH_WATCHDOG_SECONDS = 20.0

BAUD_RATE = 115200

# Check FW version command: 01 00 03 00 0D 04 00 15
FW_CHECK_CMD = "01 00 03 00 0D 04 00 15"

# Delay after a finished update before sending the FW check command,
# giving the device time to reboot / settle into application mode.
FW_CHECK_DELAY_S = 3.0

# Response frame layout: Header(1) + SeqID(1) + Len(1) + Data(Len) + Checksum(2)
# Version data = 4 bytes starting at byte 4 (index 3).
FW_DATA_START = 3
FW_DATA_LENGTH = 4

# Continuous mass-update polling cadence and Target response headers.
MASS_TARGET_RETRY_S = 0.5
TARGET_ACK_HEADER = 0x80
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
    """
    Strip all non-ASCII characters (emoji, symbols, special dashes)
    so logs are safe for any console encoding (e.g. cp1252) and free
    of special characters. Collapses leftover double spaces.
    """
    cleaned = "".join(ch for ch in str(message) if ch.isascii())
    return " ".join(cleaned.split())


def normalize_version(value: str) -> str:
    """Normalize a dotted version string (strips trailing zero segments)."""
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

    # ------------------------------------------------------------------
    # Window & push helpers
    # ------------------------------------------------------------------
    def set_window(self, window):
        self._window = window

    def _push(self, event: str, *args):
        """Call window.<event>(...) in the frontend with JSON-safe args."""
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
            pass  # never let console encoding break the app
        self._push("onLogFromPy", clean)

    def report_progress(self, ratio: float, current: int, total: int):
        self._push("onProgressFromPy", round(ratio * 100, 2), current, total)

    def _push_connection(self):
        self._push(
            "onConnectionState",
            {"connected": self.is_connected, "port": self.connected_port},
        )

    def _guarded_progress(self, ratio: float, current: int, total: int):
        """Progress callback that honors pause/stop."""
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

        # Accept either a bare "COM3" or a display string "COM3 - Description"
        port_name = str(port).split(" - ")[0].strip()

        # Use the shared command_runner callbacks so incoming frames update
        # last_rx_frame / msg_queue - required by send_and_get_rx(),
        # execute_bin_flashing_sequence() and print_queued_messages().
        # (Custom log-only callbacks here would break response detection.)
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
            self.log(f"✅ Connected to {port_name} at {baud_rate} baud.")
            return {"status": "SUCCESS", "message": f"Connected to {port_name}"}

        self.comm = None
        self.is_connected = False
        self.connected_port = None
        self._push_connection()
        self.log(f"❌ Failed to connect to {port_name}")
        return {"status": "ERROR", "message": f"Failed to connect to {port_name}"}

    def disconnect_port(self):
        if self.comm:
            self.comm.disconnect()
            self.comm = None
        self.is_connected = False
        self.connected_port = None
        self._push_connection()
        self.log("🔌 Disconnected from COM port.")
        return {"status": "SUCCESS"}

    # ------------------------------------------------------------------
    # File selection
    # ------------------------------------------------------------------
    def select_file(self):
        """Native open dialog filtered to .bin / .csv files."""
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
                self.log("\n🔄 Generating flashing script from BIN file...")
                script_data = generate_and_save_bin_script(
                    file_path, tool_type=tool_type, log_callback=self.log
                )
                if not script_data:
                    raise RuntimeError("Failed to process BIN file / generate script")

                self.log("\n🚀 Starting flashing sequence...")
                update_ok = execute_bin_flashing_sequence(
                    self.comm,
                    script_data,
                    log_callback=self.log,
                    progress_callback=self._guarded_progress,
                )
                if not update_ok:
                    fail_reason = "Flashing sequence failed"
            else:
                self.log("\n🔄 Processing CSV command filter...")
                csv_cmds = get_commands_from_csv(
                    file_path, prefix="74", log_callback=self.log
                )
                if not csv_cmds:
                    raise RuntimeError("No valid commands found in CSV")

                # Init commands: Target + Default METCO password
                init_cmds = []
                cmd1_base = "70 01 01 11" if tool_type == "M12" else "70 01 01 01"
                init_cmds.append(build_frame(cmd1_base))

                seq = SeqIdTracker(start=5)
                init_cmds.append(
                    build_frame(f"01 {seq.get_and_inc()} 0A 00 3B 33 33 33 33 33 33 33 33")
                )

                full_cmds = init_cmds + csv_cmds
                self.log(
                    f"📋 Sending {len(full_cmds)} commands "
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

        except RuntimeError as e:  # aborted via Stop
            update_ok = False
            fail_reason = str(e)
        except Exception as e:
            update_ok = False
            fail_reason = f"Unexpected error: {e}"

        # ----------------------------------------------------------
        # Post-update FW version verification
        # NOTE: The FW version comparison has its OWN pass/fail result
        # ('fwCheck') reported to the frontend separately. It NEVER flips
        # the update result to FAIL - the update only fails when a
        # command could not be completed.
        # ----------------------------------------------------------
        detected_fw = None
        check_state = None  # True / False / None (skipped)

        if update_ok:
            if expected_fw:
                # Let the device settle after flashing before asking for
                # the FW version.
                self.log(f"⏳ Update done - waiting {FW_CHECK_DELAY_S:.0f} s before FW check...")
                time.sleep(FW_CHECK_DELAY_S)

                self.log("🔎 Verifying firmware version...")
                check = self.verify_fw_version(expected_fw)
                detected_fw = check.get("detected")
                check_state = check["pass"]
            else:
                self.log("\nℹ️ No expected FW version provided — skipping verification.")
        elif not fail_reason:
            fail_reason = "Update failed"

        # UPDATE RESULT = PASS only when every command was sent and
        # acknowledged successfully; FAIL as soon as one command fails.
        overall = "PASS" if update_ok else "FAIL"

        if overall == "PASS":
            self.log("\n🎉 === UPDATE FINISHED: PASS ===")
            if check_state is True:
                self.log(f"✅ FW version verified: {detected_fw}")
            elif check_state is False:
                self.log(
                    f"⚠️ WARNING: FW version check FAILED - "
                    f"detected {detected_fw}, expected {expected_fw}"
                )
        else:
            self.log(f"\n🛑 === UPDATE FINISHED: FAIL — {fail_reason} ===")

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
        """
        Send the Check-FW-Version command and compare against the expected
        decimal version. Version data = 4 bytes starting at byte 4 (index 3),
        converted to decimal and joined with dots (e.g. 1.4.2.0).
        """
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
    # Mass update: auto-connect -> Target ACK 0x80 -> flash -> verify
    # ------------------------------------------------------------------
    def run_mass_update(
        self, port: str, file_path: str, tool_type: str = "M12", expected_fw: str = ""
    ):
        """
        Start one mass-update cycle in a background thread.

        The worker:
          1. retries opening the selected COM port every 0.5 s
          2. sends the Target select command (M12/M18) every 0.5 s until the
             response header byte is 0x80
          3. flashes the firmware exactly like the Update page
          4. reads back the FW version and compares it with the REQUIRED
             user input, disconnects and pushes 'onMassFinished'.
        """
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

        # FW check input is REQUIRED for mass update.
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

    def _wait_for_target_header(
        self, tool_type: str, expected_headers, stage: str,
        poll_delay_s: float = MASS_TARGET_RETRY_S, consecutive_required: int = 1,
    ) -> int:
        """Poll Target until the requested header has passed its debounce check."""
        target_base = "70 01 01 01" if tool_type == "M18" else "70 01 01 11"
        target_frame = bytes.fromhex(build_frame(target_base))
        sends = 0
        consecutive_matches = 0
        self._push("onMassStage", stage)

        while not self.controller.stop_requested():
            if not self.is_connected or not self.comm:
                raise RuntimeError("Serial port disconnected")

            cycle_start = time.monotonic()
            sends += 1
            command_runner.last_rx_frame = None
            if not self.comm.send_no_wait(target_frame):
                consecutive_matches = 0
                self.log("Target send failed; unplug feedback counter reset.")
                self._wait_with_cancel(poll_delay_s)
                continue

            received_expected_header = False
            while time.monotonic() - cycle_start < poll_delay_s:
                if self.controller.stop_requested():
                    raise RuntimeError("Aborted by operator")
                time.sleep(0.05)
                print_queued_messages(self.log)
                rx = command_runner.last_rx_frame
                if rx:
                    header = rx[0]
                    self.log(f"[MCU RX]: {rx.hex(' ').upper()} (header {header:02X})")
                    if header in expected_headers:
                        consecutive_matches += 1
                        received_expected_header = True
                        if consecutive_matches >= consecutive_required:
                            return header
                        self.log(
                            f"Target feedback {header:02X}: "
                            f"{consecutive_matches}/{consecutive_required} consecutive."
                        )
                    else:
                        consecutive_matches = 0
                    break

            if not received_expected_header:
                consecutive_matches = 0

            if sends == 1 or sends % 10 == 0:
                wanted = "/".join(f"{value:02X}" for value in expected_headers)
                self.log(f"Waiting for Target response {wanted}; sent {sends} command(s).")

        raise RuntimeError("Aborted by operator")

    def _wait_with_cancel(self, seconds: float):
        """Cancellable delay used while the device reboots after flashing."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.controller.checkpoint()
            time.sleep(min(0.1, deadline - time.monotonic()))

    def _flash_and_verify_mass_target(self, file_path, ext, tool_type, expected_fw):
        """Flash the currently selected target and return one PCBA result."""
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

    def _continuous_mass_update_worker(self, port_name, file_path, ext, tool_type, expected_fw):
        """Run Target -> flash -> verify -> unplug -> next Target until stopped."""
        terminal_reason = ""
        try:
            self.log(f"Continuous mass update started on {port_name}.")
            while not self.controller.stop_requested():
                self._wait_for_target_header(tool_type, (TARGET_ACK_HEADER,), "waiting_for_target")
                self.log("Target acknowledged; starting flash and verification.")
                result = self._flash_and_verify_mass_target(file_path, ext, tool_type, expected_fw)
                self._push("onMassResult", {**result, "expected": expected_fw})
                if result["pass"]:
                    self.log(f"MASS UPDATE PASS: FW {result.get('detected') or '?'}")
                else:
                    self.log(f"MASS UPDATE FAIL: {result.get('reason') or 'unknown error'}")

                # Do not flash the same PCBA again. Wait until it reports that
                # it is complete/unplugged, then return to target discovery.
                self._wait_for_target_header(
                    tool_type,
                    TARGET_UNPLUG_HEADERS,
                    "waiting_for_unplug",
                    poll_delay_s=1.0,
                    consecutive_required=3,
                )
                self.log("Target removed or completed; waiting for next PCBA.")
                self._push("onMassStage", "waiting_for_next_target")
        except RuntimeError as exc:
            terminal_reason = str(exc)
        except Exception as exc:
            terminal_reason = f"Unexpected mass update error: {exc}"
        finally:
            stopped = self.controller.stop_requested()
            self.mass_running = False
            self.controller.reset()
            if terminal_reason and not stopped:
                # A transport failure is terminal; reflect it in the UI rather
                # than leaving a stale connected state after a cable/device loss.
                self.disconnect_port()
            self._push("onMassStage", "done")
            self._push("onMassFinished", {"stopped": stopped, "reason": terminal_reason})
            if stopped:
                self.log("Continuous mass update stopped by operator.")
            elif terminal_reason:
                self.log(f"Continuous mass update ended: {terminal_reason}")

    def _mass_connect_loop(self, port_name: str) -> bool:
        """Retry connecting every 0.5 s until success / stop request."""
        attempts = 0
        while not self.controller.stop_requested():
            attempts += 1
            if attempts == 1 or attempts % 10 == 0:
                self.log(f"🔌 Connect attempt {attempts} on {port_name}...")

            # Shared command_runner callbacks keep last_rx_frame / msg_queue
            # working for the later flashing + FW-read stages.
            comm = OpenLinkComm(
                port=port_name,
                baud_rate=BAUD_RATE,
                on_rx=on_rx_callback,
                on_tx=on_tx_callback,
            )
            if comm.connect():
                self.comm = comm
                self.is_connected = True
                self.connected_port = port_name
                self._push_connection()
                self.log(f"✅ Connected to {port_name} after {attempts} attempt(s).")
                return True

            time.sleep(MASS_TARGET_RETRY_S)
        return False

    def _mass_target_ack_loop(self, tool_type: str) -> bool:
        """Poll Target select every 0.5 s until response header byte == 0x80."""
        target_base = "70 01 01 01" if tool_type == "M18" else "70 01 01 11"
        target_frame = bytes.fromhex(build_frame(target_base))
        label = "M18" if tool_type == "M18" else "M12"

        sends = 0
        while True:
            if self.controller.stop_requested():
                return False

            cycle_start = time.monotonic()
            sends += 1

            command_runner.last_rx_frame = None
            self.log(
                f"[TX]: Sending Target {label} select command (attempt {sends})..."
            )
            if not self.comm.send_no_wait(target_frame):
                self.log("⚠️ Failed to send Target command!")
            else:
                # Wait up to one retry cycle (0.5 s) for a frame from the device
                rx = None
                deadline = cycle_start + MASS_TARGET_RETRY_S
                while time.monotonic() < deadline:
                    time.sleep(0.05)
                    print_queued_messages(self.log)
                    rx = command_runner.last_rx_frame
                    if rx is not None:
                        break

                if rx is not None:
                    first_byte = rx[0]
                    self.log(f"[MCU RX]: {rx.hex(' ').upper()} (header {first_byte:02X})")
                    if first_byte == TARGET_ACK_HEADER:
                        self.log(
                            f"🎯 Target ACK (80) received after {sends} send(s) - starting programming."
                        )
                        return True
                elif sends == 1 or sends % 10 == 0:
                    self.log(f"⚠️ No response after Target attempt {sends} - retrying...")

            remaining = MASS_TARGET_RETRY_S - (time.monotonic() - cycle_start)
            if remaining > 0:
                time.sleep(remaining)

    def _mass_update_worker(
        self, port_name: str, file_path: str, ext: str, tool_type: str, expected_fw: str
    ):
        update_ok = False
        fail_reason = ""
        detected_fw = None
        verified = False

        try:
            self.log("=" * 60)
            self.log(
                f"MASS UPDATE — {os.path.basename(file_path)} "
                f"({ext.upper()}, Tool: {tool_type}, Port: {port_name})"
            )
            self.log("=" * 60)

            # Stage 1 - auto-connect every 0.5 s ------------------------
            self._push("onMassStage", "connecting")
            connected = self._mass_connect_loop(port_name)
            if not connected:
                raise RuntimeError("Stopped by operator")

            # Stage 2 - Target ACK polling (first byte must be 0x80) ---
            self._push("onMassStage", "targeting")
            acked = self._mass_target_ack_loop(tool_type)
            if not acked:
                raise RuntimeError("Stopped by operator")

            # Stage 3 - programming (identical to the Update page) -----
            self._push("onMassStage", "programming")
            if ext == "bin":
                self.log("\n🔄 Generating flashing script from BIN file...")
                script_data = generate_and_save_bin_script(
                    file_path, tool_type=tool_type, log_callback=self.log
                )
                if not script_data:
                    raise RuntimeError("Failed to process BIN file / generate script")

                self.log("\n🚀 Starting flashing sequence...")
                update_ok = execute_bin_flashing_sequence(
                    self.comm,
                    script_data,
                    log_callback=self.log,
                    progress_callback=self._guarded_progress,
                )
                if not update_ok:
                    fail_reason = "Flashing sequence failed"
            else:
                self.log("\n🔄 Processing CSV command filter...")
                csv_cmds = get_commands_from_csv(
                    file_path, prefix="74", log_callback=self.log
                )
                if not csv_cmds:
                    raise RuntimeError("No valid commands found in CSV")

                # Init commands: Target + Default METCO password
                init_cmds = []
                cmd1_base = "70 01 01 11" if tool_type == "M12" else "70 01 01 01"
                init_cmds.append(build_frame(cmd1_base))

                seq = SeqIdTracker(start=5)
                init_cmds.append(
                    build_frame(f"01 {seq.get_and_inc()} 0A 00 3B 33 33 33 33 33 33 33 33")
                )

                full_cmds = init_cmds + csv_cmds
                self.log(
                    f"📋 Sending {len(full_cmds)} commands "
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

            # Stage 4 - required FW read-back & compare -----------------
            if update_ok:
                self._push("onMassStage", "verifying")
                self.log(f"\n⏳ Waiting {FW_CHECK_DELAY_S:.0f} s before FW read...")
                time.sleep(FW_CHECK_DELAY_S)

                self.log("🔎 Reading firmware version for verification...")
                check = self.verify_fw_version(expected_fw)
                detected_fw = check.get("detected")
                verified = bool(check.get("pass"))
                if not verified:
                    fail_reason = check.get("reason") or "FW verification failed"

        except RuntimeError as e:  # aborted via Stop
            update_ok = False
            fail_reason = str(e)
        except Exception as e:
            update_ok = False
            fail_reason = f"Unexpected error: {e}"

        # PASS only when flashing succeeded AND the FW read-back matches
        # the (required) user input. A mismatch or unreadable FW = FAIL.
        overall_pass = update_ok and verified

        if overall_pass:
            self.log(f"\n🎉 === MASS UPDATE FINISHED: PASS === (FW {detected_fw})")
        else:
            self.log(f"\n🛑 === MASS UPDATE FINISHED: FAIL — {fail_reason} ===")

        # Always disconnect so the next PCBA gets a fresh connection.
        try:
            if self.comm or self.is_connected:
                self.disconnect_port()
        except Exception as e:
            self.log(f"⚠️ Disconnect error: {e}")

        self.controller.reset()
        self.mass_running = False
        self._push("onMassStage", "done")
        self._push(
            "onMassFinished",
            {
                "pass": overall_pass,
                "detected": detected_fw,
                "expected": expected_fw,
                "reason": "" if overall_pass else fail_reason,
            },
        )



    # ------------------------------------------------------------------
    # Run controls
    # ------------------------------------------------------------------
    def pause_update(self):
        self.controller.pause()
        self.log("⏸ Update paused.")
        return {"status": "SUCCESS"}

    def resume_update(self):
        self.controller.resume()
        self.log("▶️ Update resumed.")
        return {"status": "SUCCESS"}

    def stop_update(self):
        self.controller.stop()
        self.log("🛑 Stop requested — aborting update...")
        return {"status": "SUCCESS"}

    # ------------------------------------------------------------------
    # Manual commands
    # ------------------------------------------------------------------
    def run_hex_command(self, hex_cmd: str):
        """Send a single hex command synchronously."""
        if not self.is_connected or not self.comm:
            return {"status": "ERROR", "message": "Serial port not connected"}

        hex_cmd = str(hex_cmd).strip()
        if not hex_cmd:
            return {"status": "ERROR", "message": "Empty command"}

        self.log(f"\n--- Running Hex Command: {hex_cmd} ---")
        ok = execute_command_list(self.comm, [hex_cmd], log_callback=self.log)
        if ok:
            self.log("✅ Command executed successfully.")
            return {"status": "SUCCESS", "message": "Command executed"}
        return {"status": "ERROR", "message": "Command failed or timed out"}

    def run_quick_command(self, cmd_type: str):
        """Send one of the predefined quick commands and parse the reply."""
        if not self.is_connected or not self.comm:
            return {"status": "ERROR", "message": "Serial port not connected"}

        cmd = QUICK_COMMANDS.get(cmd_type)
        if not cmd:
            return {"status": "ERROR", "message": f"Unknown quick command: {cmd_type}"}

        title = QUICK_TITLES.get(cmd_type, cmd_type)

        def quick_log(message):
            """Suppress the banner/TX echo - terminal shows only TX/RX frames."""
            text = str(message)
            stripped = text.strip()
            if stripped.startswith("--- [TX]") or stripped.startswith("QUICK COMMAND"):
                return
            self.log(text)

        # Reading calibration data requires an authenticated session:
        # always send the default METCO password first.
        if cmd_type == "calibration":
            self.log(
                "🔑 Sending default METCO password before reading calibration data..."
            )
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
            # Response carried no data (plain ACK) - no popup needed
            return {"status": "NO_DATA", "title": title, "result": "Command executed (no data)"}

        return {"status": "SUCCESS", "title": title, "result": parsed}

    @staticmethod
    def _parse_quick_response(cmd_type: str, rx: bytes):
        """
        Parse the data section of a quick-command response.
        Returns None when the response carries no data (plain ACK),
        so the caller can skip showing a popup.
        """
        data_len = rx[2] if len(rx) >= 3 else max(0, len(rx) - 3)
        data = rx[3 : 3 + data_len]

        if not data:
            return None

        if cmd_type == "fw_version":
            # Convert every byte from hex to decimal, joined with dots
            # e.g. data 02 00 03 01 -> "2.0.3.1"
            return "FW Version: " + ".".join(str(byte) for byte in data)

        if cmd_type == "fw_pn":
            dec_value = int(data.hex(), 16)
            return f"FW P/N (Decimal): {dec_value}"

        return f"Data: {data.hex(' ').upper()}"


# ----------------------------------------------------------------------
# Cleanup
# ----------------------------------------------------------------------
def cleanup_on_exit(api: "JSAPI"):
    """Disconnect the serial port and delete the temp folder on app exit."""
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
# Boot splash (PyInstaller --splash icon/iconfw.png)
# ----------------------------------------------------------------------
def close_boot_splash():
    """
    Close the native PyInstaller splash screen.

    ``pyi_splash`` is injected by PyInstaller only inside frozen builds,
    so in development this is a silent no-op. It MUST be called once the
    real window is visible - otherwise the splash stays on top forever.
    """
    try:
        import pyi_splash  # provided by PyInstaller when --splash is used

        pyi_splash.close()
    except Exception:
        pass


# ----------------------------------------------------------------------
# Application entry point
# ----------------------------------------------------------------------
def main():
    api = JSAPI()

    window = webview.create_window(
        title="Software Update Tool",
        url=FRONTEND_INDEX,
        js_api=api,
        width=1280,
        height=800,
        min_size=(1024, 700),
        resizable=True,
    )

    api.set_window(window)

    # Close the PyInstaller splash as soon as the main window is visible.
    # A watchdog force-closes it if 'shown' never fires.
    splash_watchdog = threading.Timer(SPLASH_WATCHDOG_SECONDS, close_boot_splash)
    splash_watchdog.daemon = True

    def _on_window_shown():
        splash_watchdog.cancel()
        close_boot_splash()

    window.events.shown += _on_window_shown
    splash_watchdog.start()

    # Run cleanup when the window is closed
    window.events.closed += lambda: cleanup_on_exit(api)

    webview.start(debug=DEBUG_MODE)


if __name__ == "__main__":
    main()
