import queue
import time
from opelink_comm import OpenLinkComm
from script_builder import build_frame

# Quản lý State của việc truyền nhận
msg_queue = queue.Queue()
last_rx_frame = None

def on_rx_callback(frame: bytes):
    global last_rx_frame
    last_rx_frame = frame
    msg_queue.put(f"[MCU RX]: {frame.hex(' ').upper()}")

def on_tx_callback(frame: bytes):
    msg_queue.put(f"[TX  ->]: {frame.hex(' ').upper()}")

def print_queued_messages():
    """In các tin nhắn trong hàng đợi ra màn hình Console"""
    while not msg_queue.empty():
        print(msg_queue.get())

def send_and_get_rx(comm: OpenLinkComm, hex_cmd: str, timeout_ms=5000) -> bytes:
    """Gửi lệnh và chờ phản hồi từ MCU"""
    global last_rx_frame
    last_rx_frame = None

    print(f"\n--- [TX]: {hex_cmd} ---")
    success = comm.send_hex(hex_cmd, timeout_ms=timeout_ms)
    time.sleep(0.05)
    print_queued_messages()

    if not success or not last_rx_frame:
        print("⚠️ Timeout hoặc không nhận được phản hồi từ MCU!")
        return None

    return last_rx_frame

def execute_command_list(comm: OpenLinkComm, cmd_list: list) -> bool:
    """Gửi lần lượt danh sách lệnh đã chuẩn bị sẵn (Dùng cho CSV hoặc Hex đơn lẻ)"""
    for idx, cmd in enumerate(cmd_list, start=1):
        rx = send_and_get_rx(comm, cmd)
        if rx is None:
            return False
    return True

def execute_bin_flashing_sequence(comm: OpenLinkComm, script_data: dict) -> bool:
    """Thực thi truyền tập lệnh Update Flashing xuống MCU (Dùng cho file BIN)"""
    script_commands = script_data["script_commands"]
    total_bytes = script_data["total_bytes"]

    # Tính X5 X6 từ tổng số byte
    bytes_3le = total_bytes.to_bytes(3, byteorder='little')
    x5 = f"{bytes_3le[0]:02X}"
    x6 = f"{bytes_3le[1]:02X}"

    print("\n🚀 Bắt đầu gửi tập lệnh Update xuống Tool...")
    x1, x2, x3, x4 = None, None, None, None

    for idx, cmd in enumerate(script_commands, start=1):
        
        # 1. Xử lý DYNAMIC_CMD_4 (Cấu trúc mới: 00 X4 X1 X2 X3 00 00)
        if cmd.startswith("DYNAMIC_CMD_4:"):
            seq_id_4 = cmd.split(":")[1]
            if not x4:
                print("❌ Thiếu thông số X4 để tạo lệnh bước 4!")
                return False
            
            # Lệnh mới: 74 <SeqID> 08 11 00 X4 X1 X2 X3 00 00
            cmd = build_frame(f"74 {seq_id_4} 08 11 00 {x4} {x1} {x2} {x3} 00 00")

            # # ========================================================
            # # 🛠️ [DEBUG MODE] - HIỂN THỊ LỆNH 4, 5 VÀ HỎI USER
            # # ========================================================
            # if idx < len(script_commands) and script_commands[idx].startswith("DYNAMIC_CMD_5:"):
            #     seq_id_5 = script_commands[idx].split(":")[1]
            #     # Lệnh mới: 74 <SeqID> 08 11 X5 X6 X1 X2 X3 00 00 (Đã bỏ byte 01 thừa)
            #     cmd_5_preview = build_frame(f"74 {seq_id_5} 08 11 {x5} {x6} {x1} {x2} {x3} 00 00")
                
            #     print("\n" + "="*60)
            #     print("🛠️ [DEBUG MODE] KIỂM TRA LỆNH DYNAMIC TRƯỚC KHI GỬI")
            #     print(f" - Params trích xuất : X1={x1}, X2={x2}, X3={x3}, X4={x4}")
            #     print(f" - Size file (X5, X6): X5={x5}, X6={x6}")
            #     print(f" 👉 Lệnh 4 sẽ gửi   : {cmd}")
            #     print(f" 👉 Lệnh 5 sẽ gửi   : {cmd_5_preview}")
            #     print("="*60)
                
            #     debug_confirm = input("❓ [DEBUG] Bạn có đồng ý gửi tiếp 2 lệnh này không? (Y/N): ").strip().upper()
            #     if debug_confirm not in ["Y", "YES"]:
            #         print("⏸️ [DEBUG] Đã hủy tiến trình Update theo yêu cầu.")
            #         return False
            # # ========================================================

        # 2. Xử lý DYNAMIC_CMD_5 (Cấu trúc mới: X5 X6 X1 X2 X3 00 00)
        elif cmd.startswith("DYNAMIC_CMD_5:"):
            seq_id = cmd.split(":")[1]
            if not x1:
                print("❌ Thiếu thông số X1..X3 để tạo lệnh bước 5!")
                return False
            # Lệnh mới: 74 <SeqID> 08 11 X5 X6 X1 X2 X3 00 00
            cmd = build_frame(f"74 {seq_id} 08 11 {x5} {x6} {x1} {x2} {x3} 00 00")

        # 3. Gửi lệnh đi
        rx_bytes = send_and_get_rx(comm, cmd)
        if rx_bytes is None:
            print(f"🛑 Thất bại tại lệnh thứ {idx}/{len(script_commands)}")
            return False

        # 4. Trích xuất Params nếu đây là lệnh "74 <SeqID> 01 15"
        if "01 15" in cmd and len(rx_bytes) >= 14: # Đảm bảo độ dài tối thiểu (3 byte header + tới vị trí X4)
            # Kiểm tra xem Header có đúng là 81, 83, hoặc 85 (Header có payload) không
            if rx_bytes[0] in (0x81, 0x83, 0x85):
                # Bỏ qua 3 byte đầu (Header, SeqID, Length), data thực bắt đầu từ index 3
                x1 = f"{rx_bytes[3]:02X}"
                x2 = f"{rx_bytes[4]:02X}"
                x3 = f"{rx_bytes[5]:02X}"
                x4 = f"{rx_bytes[13]:02X}"
                print(f"🔑 [Trích xuất Response] X1={x1}, X2={x2}, X3={x3}, X4={x4}")
            else:
                print(f"⚠️ Cảnh báo: Header phản hồi không mong muốn: {rx_bytes[0]:02X}")

    print("\n🎉 === QUY TRÌNH UPDATE FIRMWARE THÀNH CÔNG ===")
    return True