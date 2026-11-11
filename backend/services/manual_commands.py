"""Manual and quick-command workflows using an owned command runner."""

from backend.domain.errors import InputError
from backend.domain.protocol import QUICK_COMMANDS, QUICK_TITLES, parse_quick_response, response_data, validate_hex


def run_hex(runner, command):
    command = validate_hex(command)
    if not runner.execute_list([command]):
        raise InputError("Command failed or timed out. Check the device connection.")
    runner.log("Command executed successfully.")
    return {"status": "SUCCESS", "message": "Command executed"}


def run_quick(runner, key):
    if not isinstance(key, str) or key not in QUICK_COMMANDS:
        raise InputError("Unknown quick command.")
    title = QUICK_TITLES[key]
    if key == "calibration":
        runner.log("Sending default METCO password before reading calibration data...")
        auth = runner.send(QUICK_COMMANDS["metco_password"], add_checksum=False)
        if auth is None:
            return {"status": "TIMEOUT", "title": title, "result": "Timeout waiting for METCO password response"}
        try:
            response_data(auth)
        except InputError:
            return {"status": "ERROR", "title": title, "result": "Cannot get data (METCO password)"}
    frame = runner.send(QUICK_COMMANDS[key], add_checksum=False)
    if frame is None:
        return {"status": "TIMEOUT", "title": title, "result": "Timeout or no response from MCU!"}
    try:
        result = parse_quick_response(key, frame)
    except InputError as error:
        return {"status": "ERROR", "title": title, "result": str(error)}
    return {"status": "NO_DATA" if result is None else "SUCCESS", "title": title,
            "result": result if result is not None else "Command executed (no data)"}
