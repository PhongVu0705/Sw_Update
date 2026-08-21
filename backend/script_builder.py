import os
from hex_processor import process_pipeline


def build_frame(hex_cmd_str: str) -> str:
    """
    Tự động tính checksum:
    - Tính tổng tất cả các byte.
    - Format thành 2 bytes (XX XX) và nối vào cuối chuỗi.
    """
    data_bytes = bytes.fromhex(hex_cmd_str.strip())
    total_sum = sum(data_bytes)
    
    # Ép về định dạng 4 ký tự Hex (vd: 013A)
    cs_hex = f"{total_sum:04X}"
    
    # Cắt thành 2 số XX XX (vd: "01 3A")
    cs_str = f"{cs_hex[:2]} {cs_hex[2:]}"
    
    return f"{hex_cmd_str.strip()} {cs_str}"


class SeqIdTracker:
    """Tăng 4 mỗi bậc: 01 -> 05 -> 09 -> 0D ... FD -> 01"""
    def __init__(self, start=1):
        self.val = start

    def get_and_inc(self) -> str:
        current_str = f"{self.val:02X}"
        self.val += 4
        if self.val > 0xFD:
            self.val = 0x01
        return current_str


def generate_and_save_bin_script(bin_path: str, tool_type: str = "M12"):
    """
    Tiền xử lý file BIN và tạo sẵn danh sách lệnh Flashing.
    Ghi danh sách lệnh này ra file .txt trong thư mục temp.
    """
    print("\n🔄 1. Đang xử lý file BIN...")
    result = process_pipeline(bin_path, base_address=0x08000000, block_size=246)
    if not result or result.get("status") != "SUCCESS":
        print(f"❌ Lỗi xử lý file BIN: {result.get('message') if result else 'Unknown'}")
        return None

    # Đọc các block hex từ file trung gian
    with open(result["output_path"], "r", encoding="utf-8") as f:
        hex_blocks = [line.strip() for line in f if line.strip()]

    total_bytes = result["total_bytes"]
    seq = SeqIdTracker(start=1)
    
    script_commands = []

    # 1. Target (Không chứa ký tự M12/M18)
    cmd1 = "70 01 01 11" if tool_type == "M12" else "70 01 01 01"
    script_commands.append(build_frame(cmd1))

    # 2. Metcopassword
    seq_id = seq.get_and_inc()
    script_commands.append(build_frame(f"01 {seq_id} 0A 00 3B 33 33 33 33 33 33 33 33"))

    # 3. Lệnh Get Params
    seq_id = seq.get_and_inc()
    script_commands.append(build_frame(f"74 {seq_id} 01 15"))

    # 4. Lệnh 74 <SeqID> 08 11 00 X4 ... (Placeholder, không build frame ở bước này)
    seq_id = seq.get_and_inc()
    script_commands.append(f"DYNAMIC_CMD_4:{seq_id}")

    # 5. Lệnh 74 <SeqID> 08 11 X5 X6 ... (Placeholder, không build frame ở bước này)
    seq_id = seq.get_and_inc()
    script_commands.append(f"DYNAMIC_CMD_5:{seq_id}")

    # 6. Target
    seq_id = seq.get_and_inc()
    cmd6 = f"70 {seq_id} 01 11" if tool_type == "M12" else f"70 {seq_id} 01 01"
    script_commands.append(build_frame(cmd6))

    # 7. Lệnh cố định
    script_commands.append("74 F5 01 10 01 7A")

    # 8. Target
    seq_id = seq.get_and_inc()
    cmd8 = f"70 {seq_id} 01 11" if tool_type == "M12" else f"70 {seq_id} 01 01"
    script_commands.append(build_frame(cmd8))

    # 9. Lệnh cố định
    script_commands.append("74 FC 01 13 01 84")

    # 10. Tập gói A
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

        # Phân tách chuỗi data thành từng byte (cách nhau bởi khoảng trắng)
        spaced_block_hex = " ".join(block_hex[i:i+2] for i in range(0, len(block_hex), 2))

        # Ghép chuỗi lệnh với data đã có khoảng trắng
        payload_str = f"74 {seq_id} {len_str} 12 {d1} {d2} {d3} {spaced_block_hex}"
        script_commands.append(build_frame(payload_str))

        data_offset += block_len

    # 11 & 12. Lệnh kết thúc
    seq_id = seq.get_and_inc()
    script_commands.append(build_frame(f"74 {seq_id} 01 03"))

    seq_id = seq.get_and_inc()
    script_commands.append(build_frame(f"74 {seq_id} 01 13"))

    # Xuất ra file TXT kịch bản lệnh
    script_dir = os.path.dirname(os.path.abspath(__file__))
    temp_dir = os.path.join(script_dir, "temp")
    base_name = os.path.splitext(os.path.basename(bin_path))[0]
    script_txt_path = os.path.join(temp_dir, f"{base_name}_script_commands.txt")

    with open(script_txt_path, "w", encoding="utf-8") as f:
        for cmd in script_commands:
            f.write(f"{cmd}\n")

    print(f"✅ Đã tạo kịch bản tập lệnh thành công! TỔNG LỆNH: {len(script_commands)}")
    print(f"📄 File tập lệnh TXT: {script_txt_path}")

    return {
        "script_path": script_txt_path,
        "script_commands": script_commands,
        "total_bytes": total_bytes
    }