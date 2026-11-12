"""Flash the first board immediately, then poll removal and insertion gates."""

from backend.domain.errors import InputError
from backend.domain.pcba_cycle import PcbaCycle
from backend.domain.protocol import QUICK_COMMANDS, validate_tool


class PcbaAutoCycle:
    def __init__(self, events, poll_interval=0.5, timeout_ms=500):
        self.events = events
        self.poll_interval = poll_interval
        self.timeout_ms = timeout_ms

    def _stage(self, phase):
        self.events.emit("onMassStage", phase)

    def run(self, runner, tool_type, flash_one):
        validate_tool(tool_type)
        target_command = QUICK_COMMANDS["target_m12" if tool_type == "M12" else "target_m18"]
        machine = PcbaCycle()
        self._stage(machine.phase)
        while True:
            runner.controller.checkpoint()
            if machine.phase == "programming":
                flash_one()
                machine.updated()
                self._stage(machine.phase)
                continue
            with runner.suppress_frame_logs():
                while machine.phase != "programming":
                    runner.controller.checkpoint()
                    if not runner.comm or not runner.comm.is_running:
                        raise InputError("Serial connection lost. Reconnect before restarting Auto PCBA.")
                    # Presence probes must retry even if the previous reply was busy (85).
                    # Keep the normal busy guard for flashing and manual commands.
                    target = runner.send(target_command, timeout_ms=self.timeout_ms, add_checksum=False, wait_if_busy=False)
                    runner.controller.checkpoint()
                    version = runner.send(QUICK_COMMANDS["fw_version"], timeout_ms=self.timeout_ms, add_checksum=False, wait_if_busy=False)
                    runner.controller.checkpoint()
                    if not runner.comm.is_running:
                        raise InputError("Serial connection lost. Reconnect before restarting Auto PCBA.")
                    # Only the reply header determines presence; FW payload is irrelevant.
                    pair = (target[0] if target else None,
                            version[0] if version else None)
                    phase = machine.phase
                    machine.observe(*pair)
                    if machine.phase != phase:
                        self.events.log("Tool removed" if phase == "waiting_for_unplug" else "Tool attached")
                        self._stage(machine.phase)
                    if machine.phase != "programming":
                        runner.controller.wait(self.poll_interval)
