import os

import app_paths
from intelhex import IntelHex

def convert_bin_to_hex_temp(bin_path, output_dir, base_address=0x08000000):
    """Convert .bin file to temporary .hex file in the temp directory"""
    file_name = os.path.splitext(os.path.basename(bin_path))[0] + ".temp.hex"
    hex_temp_path = os.path.join(output_dir, file_name)
    
    ih = IntelHex()
    ih.loadbin(bin_path, offset=base_address)
    ih.tofile(hex_temp_path, format='hex')
    return hex_temp_path

def process_hex_to_blocks(hex_path, block_size=246):
    """
    Process HEX file:
    - Filter record type (3rd byte) == '00'
    - Remove first 3 bytes (Byte Count + Address) and last byte (Checksum)
    - Concatenate data and split into 246-byte blocks
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

            # Character index 6:8 corresponds to 3rd byte (Record Type)
            record_type = raw_hex[6:8]

            if record_type == '00':
                # Remove first 4 bytes (Byte Count + Address + Record Type) and last byte (Checksum)
                data_payload = raw_hex[8:-2]
                full_data_hex += data_payload

    # 1 Byte = 2 HEX characters -> Block 246 Bytes = 492 HEX characters
    char_block_size = block_size * 2
    blocks = [
        full_data_hex[i:i + char_block_size]
        for i in range(0, len(full_data_hex), char_block_size)
    ]

    return blocks, full_data_hex

def _log(message: str, log_callback=None):
    """Helper: log via callback if available, otherwise print to console."""
    if log_callback:
        log_callback(message)
    else:
        print(message)

def process_pipeline(bin_path, base_address=0x08000000, block_size=246, log_callback=None):
    """
    Main pipeline processing function:
    - Get BIN file path
    - Create temp directory at script level
    - Convert BIN -> HEX -> Filter Record '00' -> Split Blocks -> Export TXT
    """
    bin_path = bin_path.strip("'\"").strip()

    if not os.path.exists(bin_path):
        _log(f"\n[ERROR] File not found: {bin_path}", log_callback)
        return None

    # 'temp' directory: beside the .exe when frozen, backend/ in dev
    temp_dir = app_paths.temp_dir()

    # 1. Convert .bin to temporary .hex file
    hex_temp_path = convert_bin_to_hex_temp(bin_path, temp_dir, base_address)

    try:
        # 2. Filter, remove extra bytes, concatenate & split blocks
        blocks, full_data = process_hex_to_blocks(hex_temp_path, block_size=block_size)

        # 3. Export to .txt file in temp directory
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
        # Remove temporary HEX file after processing
        if os.path.exists(hex_temp_path):
            os.remove(hex_temp_path)