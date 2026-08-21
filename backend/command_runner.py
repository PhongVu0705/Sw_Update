import queue
import time
from opelink_comm import OpenLinkComm
from script_builder import build_frame

# Manage TX/RX state
msg_queue = queue.Queue()
last_rx_frame = None

def on_rx_callback(frame: bytes):
    global last_rx_frame
    last_rx_frame = frame
    msg_queue.put(f"[MCU RX]: {frame.hex(' ').upper()}")

def on_tx_callback(frame: bytes):
    msg_queue.put(f"[TX  ->]: {frame.hex(' ').upper()}")

def print_queued_messages(log_callback=None):
    """Print messages from the queue to Console or send to GUI log."""
    while not msg_queue.empty():
        msg = msg_queue.get()
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

def _log(message: str, log_callback=None):
    """Helper: log via callback if available, otherwise print to console."""
    if log_callback:
        log_callback(message)
    else:
        print(message)

def send_and_get_rx(comm: OpenLinkComm, hex_cmd: str, timeout_ms=5000, log_callback=None) -> bytes:
    """Send command and wait for response from MCU"""
    global last_rx_frame
    last_rx_frame = None

    _log(f"\n--- [TX]: {hex_cmd} ---", log_callback)
    success = comm.send_hex(hex_cmd, timeout_ms=timeout_ms)
    time.sleep(0.05)
    print_queued_messages(log_callback)

    if not success or not last_rx_frame:
        _log("⚠️ Timeout or no response from MCU!", log_callback)
        return None

    return last_rx_frame


def send_and_get_final_rx(comm: OpenLinkComm, hex_cmd: str, timeout_ms=5000, log_callback=None) -> bytes:
    """
    Send command and wait for the final response from MCU.
    - 0x85: keep waiting (multi-frame response)
    - 0x80/0x81: show result
    - 0x82/0x83: cannot get data
    """
    global last_rx_frame
    last_rx_frame = None

    _log(f"\n--- [TX]: {hex_cmd} ---", log_callback)
    success = comm.send_no_wait(bytes.fromhex("".join(hex_cmd.strip().split())))
    time.sleep(0.05)
    print_queued_messages(log_callback)

    if not success:
        _log("⚠️ Failed to send command!", log_callback)
        return None

    # Wait for the final response (0x80/0x81/0x82/0x83), skipping 0x85 frames
    deadline = time.time() + timeout_ms / 1000.0
    while time.time() < deadline:
        time.sleep(0.05)
        print_queued_messages(log_callback)

        if last_rx_frame is not None:
            first_byte = last_rx_frame[0]
            if first_byte == 0x85:
                # Keep waiting for more frames
                last_rx_frame = None
                continue
            elif first_byte in (0x80, 0x81, 0x82, 0x83):
                return last_rx_frame

    _log("⚠️ Timeout or no response from MCU!", log_callback)
    return None

def execute_command_list(comm: OpenLinkComm, cmd_list: list, log_callback=None, progress_callback=None) -> bool:
    """Send commands sequentially from a prepared list (for CSV or single Hex)"""
    total = len(cmd_list)
    for idx, cmd in enumerate(cmd_list, start=1):
        # Report progress (0.0 to 1.0)
        if progress_callback:
            progress_callback(idx / total, idx, total)

        rx = send_and_get_rx(comm, cmd, log_callback=log_callback)
        if rx is None:
            return False
    return True

def execute_bin_flashing_sequence(comm: OpenLinkComm, script_data: dict, log_callback=None, progress_callback=None) -> bool:
    """Execute the Update Flashing command sequence to the MCU (for BIN file)"""
    script_commands = script_data["script_commands"]
    total_bytes = script_data["total_bytes"]
    total_commands = len(script_commands)

    # Calculate X5 X6 from total bytes
    bytes_3le = total_bytes.to_bytes(3, byteorder='little')
    x5 = f"{bytes_3le[0]:02X}"
    x6 = f"{bytes_3le[1]:02X}"

    _log("\n🚀 Starting to send Update command sequence to Tool...", log_callback)
    x1, x2, x3, x4 = None, None, None, None

    for idx, cmd in enumerate(script_commands, start=1):
        # Report progress (0.0 to 1.0)
        if progress_callback:
            progress_callback(idx / total_commands, idx, total_commands)
        
        # 1. Handle DYNAMIC_CMD_4 (New structure: 00 X4 X1 X2 X3 00 00)
        if cmd.startswith("DYNAMIC_CMD_4:"):
            seq_id_4 = cmd.split(":")[1]
            if not x4:
                _log("❌ Missing X4 parameter to create step 4 command!", log_callback)
                return False
            
            # New command: 74 <SeqID> 08 11 00 X4 X1 X2 X3 00 00
            cmd = build_frame(f"74 {seq_id_4} 08 11 00 {x4} {x1} {x2} {x3} 00 00")

        # 2. Handle DYNAMIC_CMD_5 (New structure: X5 X6 X1 X2 X3 00 00)
        elif cmd.startswith("DYNAMIC_CMD_5:"):
            seq_id = cmd.split(":")[1]
            if not x1:
                _log("❌ Missing X1..X3 parameters to create step 5 command!", log_callback)
                return False
            # New command: 74 <SeqID> 08 11 X5 X6 X1 X2 X3 00 00
            cmd = build_frame(f"74 {seq_id} 08 11 {x5} {x6} {x1} {x2} {x3} 00 00")

        # 3. Send the command
        rx_bytes = send_and_get_rx(comm, cmd, log_callback=log_callback)
        if rx_bytes is None:
            _log(f"🛑 Failed at command {idx}/{len(script_commands)}", log_callback)
            return False

        # 4. Extract Params if this is a "74 <SeqID> 01 15" command
        if "01 15" in cmd and len(rx_bytes) >= 14: # Ensure minimum length (3 byte header + up to X4 position)
            # Check if Header is 81, 83, or 85 (Header with payload)
            if rx_bytes[0] in (0x81, 0x83, 0x85):
                # Skip first 3 bytes (Header, SeqID, Length), actual data starts at index 3
                x1 = f"{rx_bytes[3]:02X}"
                x2 = f"{rx_bytes[4]:02X}"
                x3 = f"{rx_bytes[5]:02X}"
                x4 = f"{rx_bytes[13]:02X}"
                _log(f"🔑 [Response Extracted] X1={x1}, X2={x2}, X3={x3}, X4={x4}", log_callback)
            else:
                _log(f"⚠️ Warning: Unexpected response header: {rx_bytes[0]:02X}", log_callback)

    _log("\n🎉 === FIRMWARE UPDATE PROCESS COMPLETED SUCCESSFULLY ===", log_callback)
    return True