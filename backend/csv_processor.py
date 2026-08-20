import os
import pandas as pd


def export_filtered_csv(
    input_path: str,
    output_path: str,
    prefix: str = "74",
    message_only: bool = True,
) -> None:
    """Lọc dữ liệu và xuất ra file CSV mới (không chứa dòng tiêu đề)."""
    input_path = input_path.strip("\"'")
    output_path = output_path.strip("\"'")

    # Tự động xử lý nếu người dùng nhập thư mục
    if os.path.isdir(output_path):
        output_path = os.path.join(output_path, f"filtered_output_{prefix}.csv")
    elif not output_path.lower().endswith(".csv"):
        output_path += ".csv"

    # Lọc dữ liệu
    df = pd.read_csv(input_path)
    condition = df["Message"].astype(str).str.strip().str.startswith(prefix)
    filtered_df = df[condition]

    # Xuất dữ liệu (thêm header=False để xóa tiêu đề)
    if message_only:
        filtered_df[["Message"]].to_csv(
            output_path, index=False, header=False
        )
    else:
        filtered_df.to_csv(output_path, index=False, header=False)