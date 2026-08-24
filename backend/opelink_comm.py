"""
Module: opelink_comm
Description: Library for connecting and sending/receiving Hex data with MCU via OpenLink protocol.
"""

import serial
import serial.tools.list_ports
import time
import threading
from typing import Callable, List, Dict, Optional


def list_ports() -> List[Dict[str, str]]:
    """Return the list of available COM ports on the system."""
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
        self.last_rx_time = time.time()  # Track the time of the last received byte

        self.pending_seq_events = {}
        self.seq_lock = threading.Lock()

    def _get_next_seq_id(self) -> int:
        with self.seq_lock:
            seq_id = self.seq_counter
            self.seq_counter = (self.seq_counter + 1) & 0xFF
            return seq_id

    @staticmethod
    def ensure_checksum(data: bytes) -> bytes:
        """Automatically append 2-byte Checksum if not already present."""
        if len(data) >= 3 and (len(data) - 3) == data[2]:
            checksum = sum(data) & 0xFFFF
            return data + bytes([(checksum >> 8) & 0xFF, checksum & 0xFF])
        return data

    def connect(self) -> bool:
        """Open Serial port and start RX reading thread."""
        try:
            self.ser = serial.Serial(self.port, self.baud_rate, timeout=0.1)
            self.is_running = True
            self.rx_thread = threading.Thread(target=self._receiver_loop, daemon=True)
            self.rx_thread.start()
            return True
        except Exception:
            return False

    def disconnect(self):
        """Close Serial port and stop RX thread."""
        self.is_running = False
        if self.rx_thread and self.rx_thread.is_alive():
            self.rx_thread.join(timeout=1.0)
        if self.ser and self.ser.is_open:
            self.ser.close()

    def send_hex(self, raw_hex: str, timeout_ms: int = 10000) -> bool:
        """
        Send Hex string to MCU.
        :param timeout_ms: Time to wait for ACK response (default 10000ms = 10s).
        """
        clean_hex = "".join(raw_hex.strip().split())
        if not clean_hex or len(clean_hex) % 2 != 0:
            return False

        try:
            raw_bytes = bytes.fromhex(clean_hex)
            return self.send_bytes(raw_bytes, timeout_ms=timeout_ms)
        except ValueError:
            return False

    def send_no_wait(self, raw_bytes: bytes) -> bool:
        """Send bytes without waiting for ACK response (used for multi-frame responses)."""
        if not self.ser or not self.ser.is_open:
            return False

        frame = bytes(raw_bytes)

        self.ser.write(frame)

        if self.on_tx:
            self.on_tx(frame)

        return True

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

        # Wait up to 10s (timeout_ms) for ACK
        success = event.wait(timeout=timeout_ms / 1000.0)

        with self.seq_lock:
            self.pending_seq_events.pop(seq_id, None)

        return success

    def _receiver_loop(self):
        """Continuously read from Serial and check 5s timeout for incomplete buffer."""
        while self.is_running:
            try:
                if self.ser and self.ser.in_waiting > 0:
                    chunk = self.ser.read(self.ser.in_waiting)
                    if chunk:
                        self.last_rx_time = time.time()  # Update timestamp of last received data
                        self.rx_buffer.extend(chunk)
                        self._process_rx_buffer()
                else:
                    # If buffer has incomplete data and no new byte received for 5s -> Reset buffer
                    if len(self.rx_buffer) > 0 and (time.time() - self.last_rx_time > 5.0):
                        self.rx_buffer.clear()
                    time.sleep(0.005)
            except Exception:
                break

    def _process_rx_buffer(self):
        """Extract packets as soon as enough bytes are received."""
        while len(self.rx_buffer) > 0:
            first_byte = self.rx_buffer[0]

            # 1. 2-Byte Frame (Header 80, 82)
            if first_byte in (0x80, 0x82):
                if len(self.rx_buffer) < 2:
                    break  # Not enough 2 bytes -> wait

                seq_id = self.rx_buffer[1]
                frame = bytes(self.rx_buffer[:2])
                del self.rx_buffer[:2]

                if self.on_rx:
                    self.on_rx(frame)

                with self.seq_lock:
                    if event := self.pending_seq_events.get(seq_id):
                        event.set()

            # 2. Long Frame (Header 85, 83, 81)
            elif first_byte in (0x85, 0x83, 0x81):
                if len(self.rx_buffer) < 3:
                    break  # Not enough 3 bytes to get payload_len -> wait

                payload_len = self.rx_buffer[2]
                total_len = 3 + payload_len + 2  # Total = Header(1) + Seq(1) + Len(1) + Data + Checksum(2)

                if len(self.rx_buffer) < total_len:
                    break  # Not enough full packet -> wait

                seq_id = self.rx_buffer[1]
                frame = bytes(self.rx_buffer[:total_len])
                del self.rx_buffer[:total_len]

                if self.on_rx:
                    self.on_rx(frame)

                # Only unlock sending new command with ACK belonging to 81, 83
                if first_byte in (0x81, 0x83):
                    with self.seq_lock:
                        if event := self.pending_seq_events.get(seq_id):
                            event.set()

            # 3. Remove garbage byte
            else:
                del self.rx_buffer[:1]

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()