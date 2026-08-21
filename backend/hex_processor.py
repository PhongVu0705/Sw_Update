import os
from intelhex import IntelHex

def convert_bin_to_hex_temp(bin_path, output_dir, base_address=0x08000000):
    """Chuyển file .bin thành file .hex tạm thời trong thư mục temp"""
    file_name = os.path.splitext(os.path.basename(bin_path))[0] + ".temp.hex"
    hex_temp_path = os.path.join(output_dir, file_name)
    
    ih = IntelHex()
    ih.loadbin(bin_path, offset=base_address)
    ih.tofile(hex_temp_path, format='hex')
    return hex_temp_path

def process_hex_to_blocks(hex_path, block_size=246):
    """
    Xử lý file HEX:
    - Lọc record type (byte thứ 3) == '00'
    - Xóa 3 byte đầu (Byte Count + Address) và 1 byte cuối (Checksum)
    - Concatenate data và chia thành các block 246 bytes
    """
    full_data_hex = ""

    with open(hex_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line.startswith(':'):
                continue

            raw_hex = line[1:]
            if len(raw_hex) < 10:
                continue

            # Ký tự index 6:8 tương ứng với byte thứ 3 (Record Type)
            record_type = raw_hex[6:8]

            if record_type == '00':
                # Bỏ 4 byte đầu (Byte Count + Address + Record Type) và 1 byte cuối (Checksum)
                data_payload = raw_hex[8:-2]
                full_data_hex += data_payload

    # 1 Byte = 2 ký tự HEX -> Block 246 Bytes = 492 ký tự HEX
    char_block_size = block_size * 2
    blocks = [
        full_data_hex[i:i + char_block_size]
        for i in range(0, len(full_data_hex), char_block_size)
    ]

    return blocks, full_data_hex

def process_pipeline(bin_path, base_address=0x08000000, block_size=246):
    """
    Hàm pipeline xử lý chính:
    - Lấy đường dẫn file BIN
    - Tạo thư mục temp ở cấp script
    - Convert BIN -> HEX -> Lọc Record '00' -> Chia Block -> Xuất TXT
    """
    bin_path = bin_path.strip("'\"").strip()

    if not os.path.exists(bin_path):
        print(f"\n[LỖI] Không tìm thấy file: {bin_path}")
        return None

    # Xác định thư mục 'temp' cùng cấp script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    temp_dir = os.path.join(script_dir, "temp")
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir, exist_ok=True)

    # 1. Convert .bin sang file .hex tạm
    hex_temp_path = convert_bin_to_hex_temp(bin_path, temp_dir, base_address)

    try:
        # 2. Lọc, xóa byte thừa, concate & phân block
        blocks, full_data = process_hex_to_blocks(hex_temp_path, block_size=block_size)

        # 3. Xuất ra file .txt trong thư mục temp
        base_name = os.path.splitext(os.path.basename(bin_path))[0]
        txt_out_path = os.path.join(temp_dir, f"{base_name}_blocks.txt")

        with open(txt_out_path, 'w', encoding='utf-8') as f:
            for block in blocks:
                f.write(f"{block}\n")

        return {
            "status": "SUCCESS",
            "total_bytes": len(full_data) // 2,
            "total_blocks": len(blocks),
            "output_path": txt_out_path
        }

    except Exception as e:
        return {
            "status": "ERROR",
            "message": str(e)
        }

    finally:
        # Xóa file HEX tạm thời sau khi xử lý xong
        if os.path.exists(hex_temp_path):
            os.remove(hex_temp_path)