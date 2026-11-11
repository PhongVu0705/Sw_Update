import itertools
import json
from pathlib import Path
import unittest

from backend.domain.pcba_cycle import PcbaCycle, classify_feedback


class PcbaPresenceTests(unittest.TestCase):
    def test_presence_and_removal_rules_for_every_pair_in_every_waiting_stage(self):
        cases = json.loads((Path(__file__).parents[1] / 'fixtures' / 'pcba_presence.json').read_text())
        pairs = [tuple(pair) for group in cases.values() for pair in group]
        headers = [None, 0x80, 0x81, 0x82, 0x83, 0x85, 0x84]
        self.assertEqual(len(pairs), 49)
        self.assertEqual(set(pairs), set(itertools.product(headers, repeat=2)))
        for feedback, group in cases.items():
            for pair in group:
                self.assertEqual(classify_feedback(*pair), feedback, pair)
                for stage in ['waiting_for_unplug', 'waiting_for_next_target', 'programming']:
                    with self.subTest(stage=stage, pair=pair):
                        machine = PcbaCycle()
                        machine.phase = stage
                        expected = stage
                        if feedback == 'present':
                            expected = {
                                'waiting_for_next_target': 'programming',
                            }.get(stage, stage)
                        elif feedback == 'absent' and stage == 'waiting_for_unplug':
                            expected = 'waiting_for_next_target'
                        self.assertEqual(machine.observe(*pair), expected)

    def test_update_returns_directly_to_removal_even_if_board_is_already_removed(self):
        machine = PcbaCycle()
        self.assertEqual(machine.phase, 'programming')
        machine.updated()
        self.assertEqual(machine.observe(0x80, 0x81), 'waiting_for_unplug')
        self.assertEqual(machine.observe(0x82, 0x81), 'waiting_for_next_target')
        self.assertEqual(machine.observe(0x80, 0x81), 'programming')
        machine.updated()
        self.assertEqual(machine.phase, 'waiting_for_unplug')
        self.assertEqual(machine.observe(None, 0x83), 'waiting_for_next_target')
        self.assertEqual(machine.observe(0x81, 0x80), 'programming')


if __name__ == '__main__':
    unittest.main()
