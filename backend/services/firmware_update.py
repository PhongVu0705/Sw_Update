"""Flash one prepared PCBA and verify its version; no file/dialog ownership."""

from backend.domain.protocol import FW_CHECK_DELAY_S, QUICK_COMMANDS, build_frame, verify_version


class FirmwareUpdater:
    def __init__(self, events, verify_delay=FW_CHECK_DELAY_S):
        self.events = events
        self.verify_delay = verify_delay

    def run(self, runner, prepared, tool_type, expected_fw):
        self.events.emit("onMassStage", "programming")
        progress = lambda ratio, current, total: self.events.emit("onProgressFromPy", round(ratio * 100, 2), current, total)
        if isinstance(prepared, dict):
            updated = runner.execute_bin(prepared, progress)
        else:
            updated = runner.execute_list(prepared, progress)
        if not updated:
            return {"pass": False, "detected": None, "reason": "Flashing sequence failed"}
        self.events.emit("onMassStage", "verifying")
        runner.controller.wait(self.verify_delay)
        target = "11" if tool_type == "M12" else "01"
        self.events.log("Sending target and default password before FW version check...")
        for command in (build_frame(f"70 01 01 {target}"), build_frame("01 01 0A 00 3B 33 33 33 33 33 33 33 33")):
            if runner.send(command, timeout_ms=500, add_checksum=False) is None:
                self.events.log("Warning: no response to verification handshake command.")
        frame = runner.send(QUICK_COMMANDS["fw_version"], add_checksum=False)
        return verify_version(frame, expected_fw)
