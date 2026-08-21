import os
import pandas as pd

def _log(message: str, log_callback=None):
    """Helper: log via callback if available, otherwise print to console."""
    if log_callback:
        log_callback(message)
    else:
        print(message)

def export_filtered_csv(
    input_path: str,
    prefix: str = "74",
    message_only: bool = True,
) -> str:
    """Filter data and automatically export to a new CSV file in the 'temp' directory."""
    input_path = input_path.strip("\"'")

    # 1. Determine root directory and create 'temp' directory if not exists
    root_dir = os.path.dirname(os.path.abspath(__file__))
    temp_dir = os.path.join(root_dir, "temp")
    os.makedirs(temp_dir, exist_ok=True)

    # 2. Automatically get original file name to name the output file
    base_filename = os.path.basename(input_path)
    if not base_filename.lower().endswith(".csv"):
        base_filename += ".csv"

    output_filename = f"filtered_{base_filename}"
    final_output_path = os.path.join(temp_dir, output_filename)

    # 3. Filter and export data
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

def get_commands_from_csv(input_path: str, prefix: str = "74", log_callback=None) -> list:
    """
    Full processing function: Filter CSV -> Export Temp File -> Read command list.
    Returns a list of Hex strings.
    """
    commands = []
    try:
        # Step 1: Filter data using existing function
        filtered_csv_path = export_filtered_csv(input_path, prefix=prefix, message_only=True)
        
        # Step 2: Read the filtered file into a list
        with open(filtered_csv_path, mode="r", encoding="utf-8") as f:
            for line in f:
                cmd = line.strip()
                if cmd:
                    commands.append(cmd)
                    
    except Exception as e:
        _log(f"❌ Error during CSV file processing: {e}", log_callback)
        
    return commands