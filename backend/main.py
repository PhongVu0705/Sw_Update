import os
import queue
import time
from csv_processor import export_filtered_csv
from opelink_comm import OpenLinkComm, select_port

# INIT_COMMANDS = [
#     "70 01 01 01",
#     "01 01 0A 00 3B 33 33 33 33 33 33 33 33 01 DF"
# ]

# msg_queue = queue.Queue()
# last_rx_frame = None  # Lưu trữ frame phản hồi gần nhất để kiểm tra Header

# def on_rx_callback(frame: bytes):
#     global last_rx_frame
#     last_rx_frame = frame
#     msg_queue.put(f"[MCU RX]: {frame.hex(' ').upper()}")

# def on_tx_callback(frame: bytes):
#     msg_queue.put(f"[TX  ->]: {frame.hex(' ').upper()}")

# def print_queued_messages():
#     while not msg_queue.empty():
#         print(msg_queue.get())

# def execute_command_list(comm: OpenLinkComm, cmd_list: list) -> bool:
#     """
#     Gửi lần lượt tập lệnh xuống MCU.
#     Trả về False và dừng gửi ngay nếu bị Timeout hoặc nhận được Header 82/83.
#     """
#     global last_rx_frame

#     for idx, cmd in enumerate(cmd_list, start=1):
#         print(f"\n--- [Lệnh {idx}/{len(cmd_list)}]: {cmd} ---")
        
#         last_rx_frame = None  # Reset lại frame phản hồi trước khi gửi lệnh mới
#         success = comm.send_hex(cmd, timeout_ms=5000)

#         time.sleep(0.02)
#         print_queued_messages()

#         # 1. Kiểm tra Timeout (Quá 5s không có ACK)
#         if not success:
#             print("⚠️ Timeout (5s): Không nhận được phản hồi từ MCU. Dừng toàn bộ chương trình!")
#             return False

#         # 2. Kiểm tra nếu tín hiệu nhận được có Header là 82 hoặc 83
#         # if last_rx_frame and last_rx_frame[0] in (0x82, 0x83):
#         #     header_hex = f"{last_rx_frame[0]:02X}"
#         #     print(f"🛑 Nhận tín hiệu Header {header_hex} từ MCU. Dừng toàn bộ chương trình!")
#         #     return False

#     return True

# def read_commands_from_filtered_csv(csv_path: str) -> list:
#     commands = []
#     try:
#         with open(csv_path, mode="r", encoding="utf-8") as f:
#             for line in f:
#                 cmd = line.strip()
#                 if cmd:
#                     commands.append(cmd)
#     except Exception as e:
#         print(f"❌ Lỗi khi đọc file CSV kết quả: {e}")
#     return commands

# def main():
#     selected_port = select_port()
#     if not selected_port:
#         print("No com port selected. Exiting the program.")
#         return

#     port_name = selected_port["port"]

#     comm = OpenLinkComm(
#         port=port_name,
#         baud_rate=115200,
#         on_rx=on_rx_callback,
#         on_tx=on_tx_callback,
#     )

#     if not comm.connect():
#         print(f"Cannot connect to the port: {port_name}!")
#         return

#     print(f"\n✅ Đã kết nối thành công tới cổng {port_name}")
#     print("👉 Nhập đường dẫn file CSV để xử lý & gửi tập lệnh.")
#     print("👉 Nhập trực tiếp lệnh Hex để gửi đơn lẻ.")
#     print("👉 Nhập 'q' hoặc 'exit' để thoát.\n")

#     try:
#         while True:
#             print_queued_messages()
#             user_input = input("[HEX / CSV INPUT] > ").strip().strip("\"'")

#             if user_input.lower() in ["q", "exit"]:
#                 print("Đang dừng chương trình...")
#                 break

#             if not user_input:
#                 continue

#             # Xử lý khi input là file CSV
#             if user_input.lower().endswith(".csv") or os.path.exists(user_input):
#                 if not os.path.exists(user_input):
#                     print(f"❌ File không tồn tại: {user_input}")
#                     continue

#                 try:
#                     print(f"\n🔄 Đang xử lý lọc dữ liệu CSV từ: {user_input}...")
                    
#                     filtered_csv_path = export_filtered_csv(
#                         input_path=user_input, 
#                         prefix="74", 
#                         message_only=True
#                     )
#                     print(f"✅ Đã lọc thành công. File lưu tại: {filtered_csv_path}")

#                     csv_cmds = read_commands_from_filtered_csv(filtered_csv_path)

#                     if not csv_cmds:
#                         print("⚠️ Không tìm thấy lệnh phù hợp trong file CSV!")
#                         continue

#                     full_cmd_list = INIT_COMMANDS + csv_cmds

#                     print(f"🚀 Bắt đầu gửi {len(full_cmd_list)} lệnh (2 lệnh Init + {len(csv_cmds)} lệnh CSV)...")
                    
#                     # Thực thi truyền danh sách lệnh và kiểm tra trạng thái trả về
#                     completed = execute_command_list(comm, full_cmd_list)
#                     if completed:
#                         print("\n✅ Hoàn tất gửi toàn bộ tập lệnh thành công!")
#                     else:
#                         print("\n❌ Tiến trình bị hủy bỏ do lỗi / tín hiệu dừng từ MCU!")

#                 except Exception as e:
#                     print(f"❌ Lỗi trong quá trình xử lý file CSV: {e}")

#             # Xử lý khi nhập 1 lệnh Hex đơn lẻ
#             else:
#                 execute_command_list(comm, [user_input])

#             print()

#     except KeyboardInterrupt:
#         print("\nĐã hủy bởi người dùng.")
#     except Exception as e:
#         print(f"\nĐã xảy ra lỗi: {e}")
#     finally:
#         comm.disconnect()
#         print("🔌 Đã ngắt kết nối cổng COM.")

from hex_processor import process_pipeline

def main():
    print("=== CHƯƠNG TRÌNH XỬ LÝ FIRMWARE BIN -> BLOCK TXT ===")
    user_input = input("Nhập đường dẫn file .bin (hoặc kéo thả file vào đây): ")
    
    if not user_input.strip():
        print("[LỖI] Đường dẫn không được để trống!")
        return

    print("\nĐang xử lý dữ liệu...")
    result = process_pipeline(user_input, base_address=0x08000000, block_size=246)

    if result and result.get("status") == "SUCCESS":
        print(f"\n[OK] Xử lý hoàn tất!")
        print(f" - Tổng dung lượng Data : {result['total_bytes']} Bytes")
        print(f" - Tổng số Block        : {result['total_blocks']} Block(s)")
        print(f" - File TXT đầu ra      : {result['output_path']}")
    elif result and result.get("status") == "ERROR":
        print(f"\n[LỖI] Xử lý thất bại: {result['message']}")

if __name__ == "__main__":
    main()