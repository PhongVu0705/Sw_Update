"""Per-connection command exchange; no module-global RX/queue state."""

import threading
import time

from backend.domain.protocol import build_frame, ensure_checksum
from backend.services.run_control import RunController


class CommandRunner:
    def __init__(self, log, controller=None):
        self.log = log
        self.controller = controller or RunController()
        self.comm = None
        self._condition = threading.Condition()
        self._command_lock = threading.Lock()
        self._last_frame = None
        self._response = None
        self._expected_seq = None
        self._transport_failed = False

    def on_rx(self, frame):
        with self._condition:
            self._last_frame = frame
            if len(frame) >= 2 and frame[1] == self._expected_seq and frame[0] in (0x80, 0x81, 0x82, 0x83):
                self._response = frame
            self._condition.notify_all()
        # Deliver logs outside the RX condition; UI callbacks can be slow.
        self.log(f"[MCU RX]: {frame.hex(' ').upper()}")

    def on_tx(self, frame):
        self.log(f"[TX ->]: {frame.hex(' ').upper()}")

    def on_error(self):
        with self._condition:
            self._transport_failed = True
            self._condition.notify_all()

    def send(self, command, timeout_ms=10000, add_checksum=True, *, wait_if_busy=True):
        self.controller.checkpoint()
        frame = bytes.fromhex(command)
        if add_checksum:
            frame = ensure_checksum(frame)
        if len(frame) == 1:
            # Preserve the legacy transport's zero-sequence padding for raw bytes.
            frame += b"\x00"
        with self._command_lock:
            deadline = time.monotonic() + timeout_ms / 1000
            while True:
                self.controller.checkpoint()
                with self._condition:
                    if self._transport_failed:
                        return None
                    if not wait_if_busy or not self._last_frame or self._last_frame[0] != 0x85:
                        self._response = None
                        self._expected_seq = frame[1]
                        break
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        self.log("Timeout waiting for busy (0x85) response to clear.")
                        return None
                    self._condition.wait(min(0.05, remaining))
            try:
                if not self.comm or not self.comm.send_no_wait(frame):
                    return None
                while True:
                    self.controller.checkpoint()
                    with self._condition:
                        if self._response is not None:
                            return self._response
                        remaining = deadline - time.monotonic()
                        if self._transport_failed or remaining <= 0:
                            return None
                        self._condition.wait(min(0.05, remaining))
            finally:
                with self._condition:
                    self._expected_seq = None

    def _accepted(self, response):
        if response is None:
            self.log("Timeout or no response from MCU.")
            return False
        if response[0] in (0x82, 0x83):
            self.log("FAIL: device reported cannot get data. Update stopped.")
            return False
        return True

    def execute_list(self, commands, progress=None):
        for index, command in enumerate(commands, start=1):
            self.controller.checkpoint()
            if command.startswith("DELAY:"):
                self.controller.wait(int(command.split(":")[1]) / 1000)
                continue
            if progress:
                progress(index / len(commands), index, len(commands))
            if not self._accepted(self.send(command)):
                return False
        return True

    def execute_bin(self, script, progress=None):
        commands = script["script_commands"]
        size = script["total_bytes"].to_bytes(3, "little").hex(" ").upper()
        params = None
        for index, command in enumerate(commands, start=1):
            self.controller.checkpoint()
            if command.startswith("DELAY:"):
                self.controller.wait(int(command.split(":")[1]) / 1000)
                continue
            if progress:
                progress(index / len(commands), index, len(commands))
            if command.startswith("DYNAMIC_CMD_"):
                if params is None:
                    self.log("FAIL: device response is missing flashing parameters.")
                    return False
                kind, sequence = command.split(":")
                first, second = params
                payload = f"00 {second}" if kind == "DYNAMIC_CMD_4" else size
                command = build_frame(f"74 {sequence} 08 11 {payload} {first}")
            response = self.send(command)
            if not self._accepted(response):
                return False
            # Preserve the established parameter positions in the OpenLink reply.
            if bytes.fromhex(command)[0] == 0x74 and bytes.fromhex(command)[2:4] == b"\x01\x15":
                if len(response) < 18 or response[0] != 0x81:
                    self.log("FAIL: incomplete flashing parameters from device.")
                    return False
                params = (response[4:8].hex(" ").upper(), response[13:15].hex(" ").upper())
        self.log("Firmware command sequence completed successfully.")
        return True
