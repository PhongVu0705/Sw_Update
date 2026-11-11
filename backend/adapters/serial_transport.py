"""Serial I/O and OpenLink RX packet assembly; no workflow/UI state."""

import threading
import time

import serial
from serial.tools import list_ports as serial_ports

from backend.domain.errors import InputError


def list_ports():
    return [{"port": item.device, "description": item.description, "hwid": item.hwid}
            for item in serial_ports.comports()]


def extract_frames(buffer):
    frames = []
    while buffer:
        header = buffer[0]
        if header in (0x80, 0x82):
            size = 2
        elif header in (0x81, 0x83, 0x85):
            if len(buffer) < 3:
                break
            size = 5 + buffer[2]
        else:
            del buffer[0]
            continue
        if len(buffer) < size:
            break
        frames.append(bytes(buffer[:size]))
        del buffer[:size]
    return frames


class OpenLinkComm:
    def __init__(self, port, baud_rate=115200, on_rx=None, on_tx=None, on_error=None):
        self.port = port
        self.baud_rate = baud_rate
        self.on_rx = on_rx or (lambda frame: None)
        self.on_tx = on_tx or (lambda frame: None)
        self.on_error = on_error or (lambda: None)
        self.ser = None
        self.is_running = False
        self._thread = None
        self._write_lock = threading.Lock()

    def connect(self):
        try:
            self.ser = serial.Serial(self.port, self.baud_rate, timeout=0.1, write_timeout=2)
        except (serial.SerialException, OSError) as error:
            raise InputError("Cannot open the COM port. Check its cable, driver, and whether another app is using it.") from error
        self.is_running = True
        self._thread = threading.Thread(target=self._receiver_loop, name="openlink-rx", daemon=True)
        try:
            self._thread.start()
        except Exception:
            self.is_running = False
            self.ser.close()
            raise
        return True

    def disconnect(self):
        self.is_running = False
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=1)
        with self._write_lock:
            if self.ser and self.ser.is_open:
                self.ser.close()

    def send_no_wait(self, frame):
        with self._write_lock:
            if not self.is_running or not self.ser or not self.ser.is_open:
                return False
            try:
                if self.ser.write(frame) != len(frame):
                    return False
            except (serial.SerialException, OSError):
                return False
        self.on_tx(bytes(frame))
        return True

    def _receiver_loop(self):
        buffer = bytearray()
        last_rx = time.monotonic()
        try:
            while self.is_running:
                chunk = self.ser.read(max(1, self.ser.in_waiting))
                if chunk:
                    last_rx = time.monotonic()
                    buffer.extend(chunk)
                    for frame in extract_frames(buffer):
                        self.on_rx(frame)
                elif buffer and time.monotonic() - last_rx > 5:
                    buffer.clear()
        except (serial.SerialException, OSError):
            if self.is_running:
                self.on_error()
        finally:
            self.is_running = False
            with self._write_lock:
                if self.ser and self.ser.is_open:
                    self.ser.close()
