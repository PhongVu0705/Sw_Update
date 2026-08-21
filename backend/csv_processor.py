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