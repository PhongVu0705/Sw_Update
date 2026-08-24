import os
import sys
import threading
import queue
import webview

# Import các module backend hiện có
from opelink_comm import list_ports, OpenLinkComm
from command_runner import (
    execute_command_list,
    execute_bin_flashing_sequence,
    on_rx_callback,
    on_tx_callback,
)
from script_builder import generate_and_save_bin_script
from csv_processor import get_commands_from_csv


class JSAPI:
    def __init__(self):
        self.comm: OpenLinkComm = None
        self._window = None
        self.is_connected = False
        self.worker_thread = None

    def set_window(self, window):
        """Gán instance window của pywebview để gọi callback JS khi cần."""
        self._window = window

    # ------------------------------------------------------------------
    # Helper Logging & Progress Callbacks
    # ------------------------------------------------------------------
    def log(self, message: str):
        """Gửi log tin nhắn về React Frontend."""
        print(message)  # Vẫn print ra terminal nếu cần debug
        if self._window:
            # Gọi hàm window.onLogFromPy(msg) phía React
            self._window.evaluate_js(f"window.onLogFromPy && window.onLogFromPy({repr(message)});")

    def report_progress(self, ratio: float, current: int, total: int):
        """Gửi tiến độ công việc về React Frontend."""
        if self._window:
            percent = round(ratio * 100, 2)
            self._window.evaluate_js(
                f"window.onProgressFromPy && window.onProgressFromPy({percent}, {current}, {total});"
            )

    # ------------------------------------------------------------------
    # API Methods (React frontend gọi qua window.pywebview.api)
    # ------------------------------------------------------------------
    def get_ports(self):
        """Lấy danh sách các cổng COM khả dụng."""
        try:
            return {"status": "SUCCESS", "ports": list_ports()}
        except Exception as e:
            return {"status": "ERROR", "message": str(e)}

    def connect_port(self, port: str, baud_rate: int = 115200):
        """Kết nối tới cổng COM."""
        if self.is_connected and self.comm:
            self.disconnect_port()

        # Đăng ký callback RX/TX để đẩy log ra giao diện
        def _rx_cb(frame: bytes):
            self.log(f"[MCU RX]: {frame.hex(' ').upper()}")

        def _tx_cb(frame: bytes):
            self.log(f"[TX  ->]: {frame.hex(' ').upper()}")

        self.comm = OpenLinkComm(
            port=port,
            baud_rate=int(baud_rate),
            on_rx=_rx_cb,
            on_tx=_tx_cb
        )

        if self.comm.connect():
            self.is_connected = True
            self.log(f"✅ Connected to {port} at {baud_rate} baud.")
            return {"status": "SUCCESS", "message": f"Connected to {port}"}
        else:
            self.comm = None
            self.is_connected = False
            self.log(f"❌ Failed to connect to {port}")
            return {"status": "ERROR", "message": f"Failed to connect to {port}"}

    def disconnect_port(self):
        """Ngắt kết nối cổng COM."""
        if self.comm:
            self.comm.disconnect()
            self.comm = None
        self.is_connected = False
        self.log("🔌 Disconnected from port.")
        return {"status": "SUCCESS"}

    def run_hex_command(self, hex_cmd: str):
        """Gửi một câu lệnh Hex đơn lẻ."""
        if not self.is_connected or not self.comm:
            return {"status": "ERROR", "message": "Serial port not connected"}

        def _task():
            self.log(f"\n--- Running Hex Command: {hex_cmd} ---")
            success = execute_command_list(
                self.comm,
                [hex_cmd],
                log_callback=self.log,
                progress_callback=self.report_progress
            )
            if success:
                self.log("✅ Command executed successfully.")
            else:
                self.log("❌ Command execution failed.")

        threading.Thread(target=_task, daemon=True).start()
        return {"status": "STARTED"}

    def run_csv_file(self, csv_path: str, prefix: str = "74"):
        """Nạp và chạy tập lệnh từ file CSV."""
        if not self.is_connected or not self.comm:
            return {"status": "ERROR", "message": "Serial port not connected"}

        if not os.path.exists(csv_path):
            return {"status": "ERROR", "message": "CSV file does not exist"}

        def _task():
            self.log(f"\n--- Processing CSV File: {csv_path} ---")
            cmds = get_commands_from_csv(csv_path, prefix=prefix, log_callback=self.log)
            if not cmds:
                self.log("⚠️ No valid commands extracted from CSV.")
                return

            self.log(f"📋 Loaded {len(cmds)} commands from CSV. Executing...")
            success = execute_command_list(
                self.comm,
                cmds,
                log_callback=self.log,
                progress_callback=self.report_progress
            )
            if success:
                self.log("🎉 CSV Commands execution finished successfully!")
            else:
                self.log("🛑 CSV Commands execution failed or stopped.")

        threading.Thread(target=_task, daemon=True).start()
        return {"status": "STARTED"}

    def run_bin_flashing(self, bin_path: str, tool_type: str = "M12"):
        """Nạp firmware file BIN và thực hiện quy trình Update Flashing."""
        if not self.is_connected or not self.comm:
            return {"status": "ERROR", "message": "Serial port not connected"}

        if not os.path.exists(bin_path):
            return {"status": "ERROR", "message": "BIN file does not exist"}

        def _task():
            self.log(f"\n--- Generating BIN Script for: {bin_path} (Tool: {tool_type}) ---")
            script_data = generate_and_save_bin_script(
                bin_path,
                tool_type=tool_type,
                log_callback=self.log
            )

            if not script_data:
                self.log("❌ Failed to process BIN file and generate script.")
                return

            self.log("\n🚀 Starting Flashing Sequence...")
            success = execute_bin_flashing_sequence(
                self.comm,
                script_data,
                log_callback=self.log,
                progress_callback=self.report_progress
            )
            if success:
                self.log("🎉 Flashing process completed successfully!")
            else:
                self.log("🛑 Flashing process failed.")

        threading.Thread(target=_task, daemon=True).start()
        return {"status": "STARTED"}


# ----------------------------------------------------------------------
# Application Entry Point
# ----------------------------------------------------------------------
def main():
    api = JSAPI()

    # Đường dẫn đến ứng dụng React Build hoặc Dev Server
    # 1. Nếu chạy Dev Server React (VD: Vite / Create React App):
    # gui_url = "http://localhost:5173"
    
    # 2. Nếu load trực tiếp file build tĩnh HTML/JS:
    gui_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist")
    gui_url = os.path.join(gui_dir, "index.html") if os.path.exists(gui_dir) else "http://localhost:5173"

    window = webview.create_window(
        title="Software Update Tool",
        url=gui_url,
        js_api=api,
        width=1280,
        height=720,
        resizable=True
    )
    
    api.set_window(window)
    webview.start(debug=True)


if __name__ == "__main__":
    main()