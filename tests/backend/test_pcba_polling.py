import unittest
from types import SimpleNamespace

from backend.domain.errors import UpdateCancelled
from backend.domain.protocol import QUICK_COMMANDS
from backend.services.command_runner import CommandRunner
from backend.services.pcba_auto_cycle import PcbaAutoCycle
from backend.services.run_control import RunController


class Events:
    def __init__(self):
        self.phase = None
        self.stages = []
        self.logs = []

    def emit(self, event, phase):
        if event == 'onMassStage':
            self.phase = phase
            self.stages.append(phase)

    def log(self, message):
        self.logs.append(message)


class BudgetController(RunController):
    def __init__(self):
        super().__init__()
        self.checks = 0

    def checkpoint(self):
        self.checks += 1
        if self.checks > 2000:
            raise AssertionError('Polling stopped sending commands or advancing')
        super().checkpoint()


class PcbaPollingTests(unittest.TestCase):
    def test_every_gate_retries_both_commands_until_required_feedback(self):
        for tool in ['M12', 'M18']:
            with self.subTest(tool=tool):
                events = Events()
                controller = BudgetController()
                runner = CommandRunner(events.log, controller)
                cycle = PcbaAutoCycle(events, poll_interval=0, timeout_ms=1)
                invalid = [(None, 0x81), (0x80, None), (0x80, 0x82), (0x82, 0x81), (0x85, 0x85)] * 5
                plans = {
                    'waiting_for_unplug': [(None, 0x81), (0x80, None), (0x80, 0x81), (0x81, 0x80), (0x85, 0x85)] * 5
                        + ([(0x82, 0x81)] if tool == 'M12' else [(0x80, 0x83)]),
                    'waiting_for_next_target': invalid + [(0x80, 0x80)],
                }
                sent = []
                rounds = {phase: 0 for phase in plans}
                target = bytes.fromhex(QUICK_COMMANDS[f'target_{tool.lower()}'])
                version = bytes.fromhex(QUICK_COMMANDS['fw_version'])
                pair = None

                def send(frame):
                    nonlocal pair
                    sent.append(frame)
                    runner.on_tx(frame)
                    phase = events.phase
                    if len(sent) % 2:
                        self.assertEqual(frame, target)
                        pair = plans[phase][rounds[phase] % len(plans[phase])]
                        header = pair[0]
                    else:
                        self.assertEqual(frame, version)
                        header = pair[1]
                        rounds[phase] += 1
                    if header is not None:
                        # Deliberately unreadable FW payload: presence uses only header.
                        runner.on_rx(bytes([header, frame[1], 4, 0xDE, 0xAD, 0xBE, 0xEF, 0, 0]))
                    return True

                runner.comm = SimpleNamespace(is_running=True, send_no_wait=send)
                flashes = []

                def flash():
                    runner.on_tx(bytes.fromhex('70 FF'))
                    runner.on_rx(bytes.fromhex('80 FF'))
                    flashes.append(len(sent))
                    if len(flashes) == 2:
                        controller.stop()

                with self.assertRaises(UpdateCancelled):
                    cycle.run(runner, tool, flash)
                self.assertEqual(rounds, {phase: 26 for phase in plans})
                self.assertEqual(flashes, [0, 104], 'first board must flash before any presence probes')
                self.assertEqual(events.stages[:5], [
                    'programming', 'waiting_for_unplug', 'waiting_for_next_target',
                    'programming', 'waiting_for_unplug',
                ])
                self.assertEqual(events.logs, [
                    '[TX ->]: 70 FF', '[MCU RX]: 80 FF',
                    'Tool removed', 'Tool attached',
                    '[TX ->]: 70 FF', '[MCU RX]: 80 FF',
                ])
                # Stop remains latched; another attempt sends nothing.
                with self.assertRaises(UpdateCancelled):
                    runner.send(QUICK_COMMANDS['fw_version'], wait_if_busy=False)
                self.assertEqual(len(sent), 104)

    def test_stop_between_target_and_fw_sends_no_more_packets(self):
        controller = RunController()
        events = Events()
        runner = CommandRunner(events.log, controller)
        sent = []
        flashes = []

        def send(frame):
            sent.append(frame)
            runner.on_tx(frame)
            runner.on_rx(bytes([0x80, frame[1]]))
            controller.stop()
            return True

        runner.comm = SimpleNamespace(is_running=True, send_no_wait=send)
        with self.assertRaises(UpdateCancelled):
            PcbaAutoCycle(events, poll_interval=0, timeout_ms=1).run(
                runner, 'M12', lambda: flashes.append('flash'))
        self.assertEqual(flashes, ['flash'])
        self.assertEqual(sent, [bytes.fromhex(QUICK_COMMANDS['target_m12'])])
        self.assertEqual(events.logs, [])
        runner.on_tx(bytes.fromhex('70 FF'))
        runner.on_rx(bytes.fromhex('80 FF'))
        self.assertEqual(events.logs, ['[TX ->]: 70 FF', '[MCU RX]: 80 FF'])

    def test_presence_probe_retries_after_busy_but_normal_commands_keep_busy_guard(self):
        runner = CommandRunner(lambda message: None)
        sent = []

        def send(frame):
            sent.append(frame)
            runner.on_rx(bytes([0x80, frame[1]]))
            return True

        runner.comm = SimpleNamespace(is_running=True, send_no_wait=send)
        runner.on_rx(bytes([0x85, 0, 0, 0, 0]))
        self.assertIsNone(runner.send(QUICK_COMMANDS['fw_version'], timeout_ms=1))
        self.assertEqual(sent, [])
        response = runner.send(QUICK_COMMANDS['fw_version'], timeout_ms=1, wait_if_busy=False)
        self.assertEqual(response[0], 0x80)
        self.assertEqual(len(sent), 1)


if __name__ == '__main__':
    unittest.main()
