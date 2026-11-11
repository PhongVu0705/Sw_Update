"""Build the existing BIN flashing sequence without intermediate HEX/TXT files."""

from backend.domain.errors import InputError
from backend.domain.protocol import SeqIdTracker, build_frame, validate_tool

MAX_BIN_BYTES = 0xFFFFFF  # The wire protocol has a three-byte firmware size.
MAX_CSV_BYTES = 32 * 1024 * 1024


def build_bin_script(data, tool_type="M12"):
    validate_tool(tool_type)
    if not data or len(data) > MAX_BIN_BYTES:
        raise InputError("BIN firmware must contain 1 to 16777215 bytes.")
    seq = SeqIdTracker()
    target = "11" if tool_type == "M12" else "01"
    commands = [build_frame(f"70 01 01 {target}")]
    for _ in range(2):
        commands.append(build_frame(f"01 {seq.get_and_inc()} 0A 00 3B 33 33 33 33 33 33 33 33"))
    commands.append(build_frame(f"74 {seq.get_and_inc()} 01 15"))
    commands.append(f"DYNAMIC_CMD_4:{seq.get_and_inc()}")
    commands.append(f"DYNAMIC_CMD_5:{seq.get_and_inc()}")
    commands.append(build_frame(f"70 {seq.get_and_inc()} 01 {target}"))
    commands.append(build_frame(f"74 {seq.get_and_inc()} 01 10"))
    commands.append("DELAY:3000")
    commands.append(build_frame(f"70 {seq.get_and_inc()} 01 {target}"))
    commands.append(build_frame(f"74 {seq.get_and_inc()} 01 13"))
    commands.append("DELAY:3000")
    for offset in range(0, len(data), 246):
        block = data[offset:offset + 246]
        payload = f"74 {seq.get_and_inc()} {len(block) + 4:02X} 12 {offset.to_bytes(3, 'big').hex(' ').upper()} {block.hex(' ').upper()}"
        commands.append(build_frame(payload))
    commands.append(build_frame(f"74 {seq.get_and_inc()} 01 03"))
    commands.append(build_frame(f"74 {seq.get_and_inc()} 01 13"))
    return {"script_commands": commands, "total_bytes": len(data)}


def csv_initial_commands(tool_type):
    validate_tool(tool_type)
    target = "11" if tool_type == "M12" else "01"
    return [
        build_frame(f"70 01 01 {target}"),
        build_frame("01 05 0A 00 3B 33 33 33 33 33 33 33 33"),
    ]
