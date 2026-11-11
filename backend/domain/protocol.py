"""OpenLink commands, validation, framing, and response interpretation."""

import re

from backend.domain.errors import InputError

BAUD_RATE = 115200
FW_CHECK_DELAY_S = 5.0
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
    "fw_version": "Check FW Version", "mpbid": "Check MPBID",
    "fw_pn": "Check FW P/N", "calibration": "Read Data Calibration",
    "target_m18": "Target M18", "target_m12": "Target M12",
    "metco_password": "Send Default METCO Password",
    "wipe_counters": "Wipe Counters And Histograms",
}


def validate_version(value):
    if not isinstance(value, str) or len(value) > 32 or not re.fullmatch(r"\d+(\.\d+){0,3}", value.strip(), re.ASCII):
        raise InputError("Enter the expected firmware version as decimal numbers separated by dots, e.g. 1.4.2.")
    return value.strip()


def normalize_version(value):
    parts = validate_version(value).split(".")
    while len(parts) > 1 and parts[-1] == "0":
        parts.pop()
    return ".".join(parts)


def validate_tool(value):
    if value not in ("M12", "M18"):
        raise InputError("Select tool type M12 or M18.")
    return value


def validate_port(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise InputError("Select a valid COM port.")
    return value.strip()


def validate_hex(value):
    if not isinstance(value, str) or len(value) > 12288:
        raise InputError("Enter a hexadecimal command of at most 4096 bytes.")
    try:
        data = bytes.fromhex(value)
    except ValueError as error:
        raise InputError("Enter hexadecimal bytes, for example: 01 00 03 00 0D 04 00 15.") from error
    if not data or len(data) > 4096:
        raise InputError("Enter a hexadecimal command of 1 to 4096 bytes.")
    return data.hex(" ").upper()


def build_frame(hex_command):
    command = validate_hex(hex_command)
    checksum = sum(bytes.fromhex(command)) & 0xFFFF
    return f"{command} {checksum >> 8:02X} {checksum & 0xFF:02X}"


def ensure_checksum(data):
    if len(data) >= 3 and len(data) - 3 == data[2]:
        return data + (sum(data) & 0xFFFF).to_bytes(2, "big")
    return data


class SeqIdTracker:
    """Increment by four: 01 -> 05 -> ... -> FD -> 01."""

    def __init__(self, start=1):
        self.value = start

    def get_and_inc(self):
        value = self.value
        self.value = self.value + 4 if self.value < 0xFD else 1
        return f"{value:02X}"


def response_data(frame):
    if not frame or frame[0] not in (0x80, 0x81):
        raise InputError("Device reported: cannot get data.")
    if frame[0] == 0x80:
        return b""
    if len(frame) < 5 or len(frame) != 5 + frame[2]:
        raise InputError("Device returned an incomplete response.")
    return frame[3:3 + frame[2]]


def parse_quick_response(key, frame):
    data = response_data(frame)
    if not data:
        return None
    if key == "fw_version":
        return "FW Version: " + ".".join(str(byte) for byte in data)
    if key == "fw_pn":
        return f"FW P/N (Decimal): {int.from_bytes(data, 'big')}"
    return "Data: " + data.hex(" ").upper()


def verify_version(frame, expected):
    if frame is None:
        return {"pass": False, "detected": None, "reason": "Timeout waiting for FW version response"}
    try:
        data = response_data(frame)
        if len(data) < 4:
            raise InputError("Response too short to contain version data.")
    except InputError as error:
        return {"pass": False, "detected": None, "reason": str(error)}
    detected = ".".join(str(byte) for byte in data[:4])
    passed = normalize_version(detected) == normalize_version(expected)
    return {"pass": passed, "detected": detected, "reason": "" if passed else "FW version mismatch"}
