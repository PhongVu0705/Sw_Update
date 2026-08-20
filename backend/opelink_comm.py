"""
Module: opelink_comm
Mô tả: Thư viện kết nối và truyền nhận dữ liệu Hex với MCU qua giao thức OpenLink.
"""

import serial
import serial.tools.list_ports
import time
import threading
from typing import Callable, List, Dict, Optional


def list_ports() -> List[Dict[str, str]]:
    """Trả về danh sách các cổng COM khả dụng trên hệ thống."""
    return [
        {"port": p.device, "description": p.description, "hwid": p.hwid}
        for p in serial.tools.list_ports.comports()
    ]

def select_port():
    ports = list_ports()
    if not ports:
        print("No COM ports found. Please connect a device and try again.")
        return None

    print("Available COM ports:")
    for idx, p in enumerate(ports, start=1):
        print(f"  [{idx}] {p['port']}: {p['description']}")

    while True:
        try:
            choice = int(input(f"\nChoose port: (1-{len(ports)}): "))
            if 1 <= choice <= len(ports):
                selected_port = ports[choice - 1]
                print(f"-> Port chossen {selected_port['port']}")
                return selected_port
            else:
                print(f"Please input again. Number must be in range 1-{len(ports)}.")
        except ValueError:
            print("Invalid input. Please enter a number.")

class OpenLinkComm:
    def __init__(
        self,
        port: str,
        baud_rate: int = 115200,
        on_rx: Optional[Callable[[bytes], None]] = None,
        on_tx: Optional[Callable[[bytes], None]] = None,
    ):
        """
        Khởi tạo OpenLinkClient.
        :param port: Tên cổng COM (ví dụ: 'COM3' hoặc '/dev/ttyUSB0')
        :param baud_rate: Tốc độ Baud (mặc định 115200)
        :param on_rx: Hàm callback xử lý dữ liệu nhận về (truyền vào tham số bytes)
        :param on_tx: Hàm callback xử lý dữ liệu gửi đi (truyền vào tham số bytes)
        """
        self.port = port
        self.baud_rate = baud_rate
        self.on_rx = on_rx
        self.on_tx = on_tx

        self.ser = None
        self.seq_counter = 0
        self.is_running = False
        self.rx_buffer = bytearray()
        self.rx_thread = None

        self.pending_seq_events = {}
        self.seq_lock = threading.Lock()

    def _get_next_seq_id(self) -> int:
        with self.seq_lock:
            seq_id = self.seq_counter
            self.seq_counter = (self.seq_counter + 1) & 0xFF
            return seq_id

    @staticmethod
    def ensure_checksum(data: bytes) -> bytes:
        """Tự động bổ sung 2 byte Checksum nếu chưa có."""
        if len(data) >= 3 and (len(data) - 3) == data[2]:
            checksum = sum(data) & 0xFFFF
            return data + bytes([(checksum >> 8) & 0xFF, checksum & 0xFF])
        return data

    def connect(self) -> bool:
        """Mở cổng Serial và khởi chạy luồng đọc RX."""
        try:
            self.ser = serial.Serial(self.port, self.baud_rate, timeout=0.1)
            self.is_running = True
            self.rx_thread = threading.Thread(target=self._receiver_loop, daemon=True)
            self.rx_thread.start()
            return True
        except Exception:
            return False

    def disconnect(self):
        """Đóng cổng Serial và dừng luồng RX."""
        self.is_running = False
        if self.rx_thread and self.rx_thread.is_alive():
            self.rx_thread.join(timeout=1.0)
        if self.ser and self.ser.is_open:
            self.ser.close()

    def send_hex(self, raw_hex: str, timeout_ms: int = 5000) -> bool:
        """
        Gửi chuỗi Hex (ví dụ: "70010111") xuống MCU.
        :param raw_hex: Chuỗi Hex cần gửi.
        :param timeout_ms: Thời gian chờ phản hồi (ms).
        :return: True nếu nhận phản hồi thành công, False nếu timeout hoặc lỗi.
        """
        clean_hex = "".join(raw_hex.strip().split())
        if not clean_hex or len(clean_hex) % 2 != 0:
            return False

        try:
            raw_bytes = bytes.fromhex(clean_hex)
            return self.send_bytes(raw_bytes, timeout_ms=timeout_ms)
        except ValueError:
            return False

    def send_bytes(self, raw_bytes: bytes, timeout_ms: int = 5000) -> bool:
        """Gửi mảng bytes trực tiếp xuống MCU."""
        if not self.ser or not self.ser.is_open:
            return False

        frame = bytearray(self.ensure_checksum(raw_bytes))

        if len(frame) >= 2:
            seq_id = frame[1]
        else:
            seq_id = self._get_next_seq_id()
            # Đảm bảo frame có đủ 2 byte để chứa header + seq_id
            while len(frame) < 2:
                frame.append(0)
            frame[1] = seq_id

        frame = bytes(frame)

        event = threading.Event()
        with self.seq_lock:
            self.pending_seq_events[seq_id] = event

        self.ser.write(frame)

        # Trigger callback TX nếu có
        if self.on_tx:
            self.on_tx(frame)

        success = event.wait(timeout=timeout_ms / 1000.0)

        with self.seq_lock:
            self.pending_seq_events.pop(seq_id, None)

        return success

    def _receiver_loop(self):
        while self.is_running:
            try:
                if self.ser and self.ser.in_waiting > 0:
                    chunk = self.ser.read(self.ser.in_waiting)
                    if chunk:
                        if self.on_rx:
                            self.on_rx(chunk)
                        self.rx_buffer.extend(chunk)
                        self._process_rx_buffer()
                else:
                    time.sleep(0.02)
            except Exception:
                break

    def _process_rx_buffer(self):
        while len(self.rx_buffer) >= 2:
            first_byte = self.rx_buffer[0]
            seq_id = self.rx_buffer[1]

            # Xử lý Khung ngắn 2 Bytes (80 01, 82 01, 85 01)
            # Lưu ý: khung ngắn được nhận diện khi buffer CHỈ có đúng 2 byte
            # tại thời điểm xử lý. Nếu MCU gửi tiếp dữ liệu ngay sau đó và
            # 2 byte này thực chất là phần đầu của một khung dài hơn, đoạn
            # code dưới có thể hiểu nhầm. Giữ nguyên hành vi gốc ở đây vì
            # đây là đặc tả giao thức (không thể suy luận thêm nếu không có
            # tài liệu OpenLink), nhưng đã ghi chú rõ rủi ro.
            if len(self.rx_buffer) == 2:
                del self.rx_buffer[:2]
                if first_byte == 0x85:
                    continue
                with self.seq_lock:
                    if event := self.pending_seq_events.get(seq_id):
                        event.set()
                continue

            # Xử lý Khung chuẩn >= 3 Bytes
            if len(self.rx_buffer) < 3:
                break

            payload_len = self.rx_buffer[2]

            # FIX #3: bản gốc quyết định "khung có 2 byte checksum hay
            # không" dựa vào việc buffer HIỆN TẠI đã đủ dài hay chưa
            # (target_len = 3+payload_len+2 nếu đủ, ngược lại 3+payload_len).
            # Đây là race condition: nếu dữ liệu đến rời rạc qua serial,
            # 2 byte checksum có thể chưa kịp tới khi hàm này chạy, khiến
            # khung bị cắt thiếu checksum -> 2 byte checksum đến sau sẽ bị
            # hiểu nhầm thành đầu của khung tiếp theo (frame desync toàn bộ
            # phần còn lại).
            #
            # Sửa: luôn coi khung chuẩn có đủ checksum 2 byte (đúng như cách
            # ensure_checksum() luôn thêm checksum khi gửi đi). Nếu buffer
            # chưa đủ độ dài cần thiết, dừng lại và CHỜ thêm dữ liệu thay vì
            # đoán mò.
            target_len = 3 + payload_len + 2

            if len(self.rx_buffer) < target_len:
                break

            del self.rx_buffer[:target_len]
            if first_byte == 0x85:
                continue

            with self.seq_lock:
                if event := self.pending_seq_events.get(seq_id):
                    event.set()

    # Hỗ trợ dùng với cú pháp "with"
    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
