import os
from hex_processor import process_pipeline

def build_frame(hex_cmd_str: str) -> str:
    """
    Automatically calculate checksum:
    - Sum all bytes.
    - Format as 2 bytes (XX XX) and append to the end of the string.
    """
    data_bytes = bytes.fromhex(hex_cmd_str.strip())
    total_sum = sum(data_bytes)
    
    # Force to 4-character Hex format (e.g. 013A)
    cs_hex = f"{total_sum:04X}"
    
    # Split into 2 numbers XX XX (e.g. "01 3A")
    cs_str = f"{cs_hex[:2]} {cs_hex[2:]}"
    
    return f"{hex_cmd_str.strip()} {cs_str}"


def build_frame_custom_checksum(hex_cmd_str: str) -> str:
    """
    Calculate checksum per spec:
    - Data starts from byte 4 (index 3).
    - Length of data is byte 3 (index 2).
    - Checksum = sum of the data bytes, formatted as 2 bytes (XX XX).
    """
    data_bytes = bytes.fromhex(hex_cmd_str.strip())
    if len(data_bytes) < 3:
        raise ValueError("Command too short to calculate checksum")

    data_len = data_bytes[2]
    data_start = 3
    data_end = data_start + data_len
    data_slice = data_bytes[data_start:data_end]

    total_sum = sum(data_slice)

    # Force to 4-character Hex format (e.g. 013A)
    cs_hex = f"{total_sum:04X}"

    # Split into 2 numbers XX XX (e.g. "01 3A")
    cs_str = f"{cs_hex[:2]} {cs_hex[2:]}"

    return f"{hex_cmd_str.strip()} {cs_str}"


class SeqIdTracker:
    """Increment by 4 each step: 01 -> 05 -> 09 -> 0D ... FD -> 01"""
    def __init__(self, start=1):
        self.val = start

    def get_and_inc(self) -> str:
        current_str = f"{self.val:02X}"
        self.val += 4
        if self.val > 0xFD:
            self.val = 0x01
        return current_str


def _log(message: str, log_callback=None):
    """Helper: log via callback if available, otherwise print to console."""
    if log_callback:
        log_callback(message)
    else:
        print(message)


def generate_and_save_bin_script(bin_path: str, tool_type: str = "M12", log_callback=None):
    """
    Pre-process BIN file and generate the Flashing command list.
    Write this command list to a .txt file in the temp directory.
    """
    _log("\n🔄 1. Processing BIN file...", log_callback)
    result = process_pipeline(bin_path, base_address=0x08000000, block_size=246, log_callback=log_callback)
    if not result or result.get("status") != "SUCCESS":
        _log(f"❌ Error processing BIN file: {result.get('message') if result else 'Unknown'}", log_callback)
        return None

    # Read hex blocks from intermediate file
    with open(result["output_path"], "r", encoding="utf-8") as f:
        hex_blocks = [line.strip() for line in f if line.strip()]

    total_bytes = result["total_bytes"]
    seq = SeqIdTracker(start=1)
    
    script_commands = []

    # 1. Target
    cmd1 = "70 01 01 11" if tool_type == "M12" else "70 01 01 01"
    script_commands.append(build_frame(cmd1))

    # 2. Metcopassword
    seq_id = seq.get_and_inc()
    script_commands.append(build_frame(f"01 {seq_id} 0A 00 3B 33 33 33 33 33 33 33 33"))

    # 3. Lệnh trùng lặp theo yêu cầu quy trình
    seq_id = seq.get_and_inc()
    script_commands.append(build_frame(f"01 {seq_id} 0A 00 3B 33 33 33 33 33 33 33 33"))

    # 4. Get Params command
    seq_id = seq.get_and_inc()
    script_commands.append(build_frame(f"74 {seq_id} 01 15"))

    # 5. Dynamic Command 4: 74 <SeqID> 08 11 00 X5 X6 X1 X2 X3 X4 <checksum>
    seq_id = seq.get_and_inc()
    script_commands.append(f"DYNAMIC_CMD_4:{seq_id}")

    # 6. Dynamic Command 5: 74 <SeqID> 08 11 X7 X8 X9 X1 X2 X3 X4 <checksum>
    seq_id = seq.get_and_inc()
    script_commands.append(f"DYNAMIC_CMD_5:{seq_id}")

    # 7. Target
    seq_id = seq.get_and_inc()
    cmd7 = f"70 {seq_id} 01 11" if tool_type == "M12" else f"70 {seq_id} 01 01"
    script_commands.append(build_frame(cmd7))

    # 8. Lệnh 74 <SeqID> 01 10 <Checksum>
    seq_id = seq.get_and_inc()
    script_commands.append(build_frame(f"74 {seq_id} 01 10"))

    # 8.1 Delay 3s
    script_commands.append("DELAY:3000")

    # 9. Target
    seq_id = seq.get_and_inc()
    cmd9 = f"70 {seq_id} 01 11" if tool_type == "M12" else f"70 {seq_id} 01 01"
    script_commands.append(build_frame(cmd9))

    # 10. Lệnh 74 <SeqID> 01 13 <Checksum>
    seq_id = seq.get_and_inc()
    script_commands.append(build_frame(f"74 {seq_id} 01 13"))

    # 10.1 Delay 3s
    script_commands.append("DELAY:3000")

    # 11. Packet set A
    data_offset = 0
    for block_hex in hex_blocks:
        seq_id = seq.get_and_inc()
        block_bytes = bytes.fromhex(block_hex)
        block_len = len(block_bytes)

        offset_3bytes = data_offset.to_bytes(3, byteorder='big')
        d1 = f"{offset_3bytes[0]:02X}"
        d2 = f"{offset_3bytes[1]:02X}"
        d3 = f"{offset_3bytes[2]:02X}"

        cmd_length = 1 + 3 + block_len
        len_str = f"{cmd_length:02X}"

        spaced_block_hex = " ".join(block_hex[i:i+2] for i in range(0, len(block_hex), 2))
        payload_str = f"74 {seq_id} {len_str} 12 {d1} {d2} {d3} {spaced_block_hex}"
        script_commands.append(build_frame(payload_str))

        data_offset += block_len

    # 12 & 13. End commands
    seq_id = seq.get_and_inc()
    script_commands.append(build_frame(f"74 {seq_id} 01 03"))

    seq_id = seq.get_and_inc()
    script_commands.append(build_frame(f"74 {seq_id} 01 13"))

    # Export command script to TXT file
    script_dir = os.path.dirname(os.path.abspath(__file__))
    temp_dir = os.path.join(script_dir, "temp")
    base_name = os.path.splitext(os.path.basename(bin_path))[0]
    script_txt_path = os.path.join(temp_dir, f"{base_name}_script_commands.txt")

    with open(script_txt_path, "w", encoding="utf-8") as f:
        for cmd in script_commands:
            f.write(f"{cmd}\n")

    _log(f"✅ Command script generated successfully! TOTAL COMMANDS: {len(script_commands)}", log_callback)
    _log(f"📄 Script TXT file: {script_txt_path}", log_callback)

    return {
        "script_path": script_txt_path,
        "script_commands": script_commands,
        "total_bytes": total_bytes
    }