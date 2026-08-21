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
            choice = int(input(f"\nChoose port (1-{len(ports)}): "))
            if 1 <= choice <= len(ports):
                selected_port = ports[choice - 1]
                print(f"-> Port chosen: {selected_port['port']}")
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
        self.port = port
        self.baud_rate = baud_rate
        self.on_rx = on_rx
        self.on_tx = on_tx

        self.ser = None
        self.seq_counter = 0
        self.is_running = False
        self.rx_buffer = bytearray()
        self.rx_thread = None
        self.last_rx_time = time.time()  # Theo dõi thời điểm nhận byte cuối cùng

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
        Gửi chuỗi Hex xuống MCU.
        :param timeout_ms: Thời gian chờ phản hồi ACK (mặc định 5000ms = 5s).
        """
        clean_hex = "".join(raw_hex.strip().split())
        if not clean_hex or len(clean_hex) % 2 != 0:
            return False

        try:
            raw_bytes = bytes.fromhex(clean_hex)
            return self.send_bytes(raw_bytes, timeout_ms=timeout_ms)
        except ValueError:
            return False

    def send_bytes(self, raw_bytes: bytes, timeout_ms: int = 10000) -> bool:
        if not self.ser or not self.ser.is_open:
            return False

        frame = bytearray(self.ensure_checksum(raw_bytes))

        if len(frame) >= 2:
            seq_id = frame[1]
        else:
            seq_id = self._get_next_seq_id()
            while len(frame) < 2:
                frame.append(0)
            frame[1] = seq_id

        frame = bytes(frame)

        event = threading.Event()
        with self.seq_lock:
            self.pending_seq_events[seq_id] = event

        self.ser.write(frame)

        if self.on_tx:
            self.on_tx(frame)

        # Chờ tối đa 10s (timeout_ms) cho tới khi nhận ACK
        success = event.wait(timeout=timeout_ms / 1000.0)

        with self.seq_lock:
            self.pending_seq_events.pop(seq_id, None)

        return success

    def _receiver_loop(self):
        """Đọc liên tục từ Serial và kiểm tra timeout 5s cho buffer dở dang."""
        while self.is_running:
            try:
                if self.ser and self.ser.in_waiting > 0:
                    chunk = self.ser.read(self.ser.in_waiting)
                    if chunk:
                        self.last_rx_time = time.time()  # Cập nhật mốc thời gian nhận dữ liệu mới
                        self.rx_buffer.extend(chunk)
                        self._process_rx_buffer()
                else:
                    # Nếu buffer còn dữ liệu dở dang mà quá 5s không nhận được byte mới -> Reset buffer
                    if len(self.rx_buffer) > 0 and (time.time() - self.last_rx_time > 5.0):
                        self.rx_buffer.clear()
                    time.sleep(0.005)
            except Exception:
                break

    def _process_rx_buffer(self):
        """Cắt gói tin ngay khi nhận đủ byte."""
        while len(self.rx_buffer) > 0:
            first_byte = self.rx_buffer[0]

            # 1. Khung 2 Bytes (Header 80, 82)
            if first_byte in (0x80, 0x82):
                if len(self.rx_buffer) < 2:
                    break  # Chưa đủ 2 byte -> chờ tiếp

                seq_id = self.rx_buffer[1]
                frame = bytes(self.rx_buffer[:2])
                del self.rx_buffer[:2]

                if self.on_rx:
                    self.on_rx(frame)

                with self.seq_lock:
                    if event := self.pending_seq_events.get(seq_id):
                        event.set()

            # 2. Khung dài (Header 85, 83, 81)
            elif first_byte in (0x85, 0x83, 0x81):
                if len(self.rx_buffer) < 3:
                    break  # Chưa đủ 3 byte để lấy payload_len -> chờ tiếp

                payload_len = self.rx_buffer[2]
                total_len = 3 + payload_len + 2  # Total = Header(1) + Seq(1) + Len(1) + Data + Checksum(2)

                if len(self.rx_buffer) < total_len:
                    break  # Chưa đủ toàn bộ gói tin -> chờ tiếp

                seq_id = self.rx_buffer[1]
                frame = bytes(self.rx_buffer[:total_len])
                del self.rx_buffer[:total_len]

                if self.on_rx:
                    self.on_rx(frame)

                # Chỉ mở khóa gửi lệnh mới với ACK thuộc 81, 83
                if first_byte in (0x81, 0x83):
                    with self.seq_lock:
                        if event := self.pending_seq_events.get(seq_id):
                            event.set()

            # 3. Loại bỏ byte rác
            else:
                del self.rx_buffer[:1]

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()