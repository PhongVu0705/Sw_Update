"""PCBA presence requires two positive replies; absence needs one negative."""


def classify_feedback(target, fw_version):
    if target in (0x80, 0x81) and fw_version in (0x80, 0x81):
        return "present"
    if target in (0x82, 0x83) or fw_version in (0x82, 0x83):
        return "absent"
    return "unknown"


class PcbaCycle:
    def __init__(self):
        self.phase = "programming"

    def observe(self, target, fw_version):
        """Consume one fresh pair. Never combine replies from different polls."""
        feedback = classify_feedback(target, fw_version)
        if self.phase == "waiting_for_next_target" and feedback == "present":
            self.phase = "programming"
        elif self.phase == "waiting_for_unplug" and feedback == "absent":
            self.phase = "waiting_for_next_target"
        return self.phase

    def updated(self):
        if self.phase != "programming":
            raise RuntimeError("PCBA update completed outside the programming phase")
        self.phase = "waiting_for_unplug"
