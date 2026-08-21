import os
import pandas as pd

def export_filtered_csv(
    input_path: str,
    prefix: str = "74",
    message_only: bool = True,
) -> str:
    """Lọc dữ liệu và tự động xuất ra file CSV mới trong thư mục 'temp'."""
    input_path = input_path.strip("\"'")

    # 1. Xác định thư mục root và tạo thư mục 'temp' nếu chưa có
    root_dir = os.path.dirname(os.path.abspath(__file__))
    temp_dir = os.path.join(root_dir, "temp")
    os.makedirs(temp_dir, exist_ok=True)

    # 2. Tự động lấy tên file gốc để đặt tên file output
    base_filename = os.path.basename(input_path)
    if not base_filename.lower().endswith(".csv"):
        base_filename += ".csv"

    output_filename = f"filtered_{base_filename}"
    final_output_path = os.path.join(temp_dir, output_filename)

    # 3. Lọc và xuất dữ liệu
    df = pd.read_csv(input_path)
    condition = df["Message"].astype(str).str.strip().str.startswith(prefix)
    filtered_df = df[condition]

    if message_only:
        filtered_df[["Message"]].to_csv(
            final_output_path, index=False, header=False
        )
    else:
        filtered_df.to_csv(final_output_path, index=False, header=False)

    return final_output_path

def get_commands_from_csv(input_path: str, prefix: str = "74") -> list:
    """
    Hàm xử lý trọn gói: Lọc CSV -> Xuất file Temp -> Đọc ra danh sách lệnh.
    Trả về dạng list các chuỗi Hex.
    """
    commands = []
    try:
        # Bước 1: Lọc dữ liệu bằng hàm có sẵn
        filtered_csv_path = export_filtered_csv(input_path, prefix=prefix, message_only=True)
        
        # Bước 2: Đọc file vừa lọc thành list
        with open(filtered_csv_path, mode="r", encoding="utf-8") as f:
            for line in f:
                cmd = line.strip()
                if cmd:
                    commands.append(cmd)
                    
    except Exception as e:
        print(f"❌ Lỗi trong quá trình xử lý file CSV: {e}")
        
    return commands