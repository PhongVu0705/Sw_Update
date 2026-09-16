import queue
import threading
import time
from opelink_comm import OpenLinkComm
from script_builder import build_frame

# Manage TX/RX state
msg_queue = queue.Queue()
last_rx_frame = None
rx_condition = threading.Condition()

def on_rx_callback(frame: bytes):
    global last_rx_frame
    with rx_condition:
        last_rx_frame = frame
        rx_condition.notify_all()
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

def wait_if_header_0x85(comm: OpenLinkComm, timeout_ms=10000, log_callback=None) -> bool:
    """
    Flow Control (0x85 Filter):
    Before transmitting the next command, inspect the last response byte (header).
    The system is ONLY allowed to transmit the next command if header != 0x85.
    If header == 0x85, hold and wait until header != 0x85.
    """
    global last_rx_frame
    deadline = time.monotonic() + timeout_ms / 1000.0
    logged_busy = False
    with rx_condition:
        while last_rx_frame is not None and len(last_rx_frame) > 0 and last_rx_frame[0] == 0x85:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _log("⚠️ Timeout waiting for 0x85 header to clear before command transmission!", log_callback)
                return False
            if not logged_busy:
                _log("Header is 0x85 (busy/multi-frame) — holding transmission...", log_callback)
                logged_busy = True
            rx_condition.wait(timeout=remaining)
            print_queued_messages(log_callback)
    return True


def _wait_for_response(timeout_ms=10000, final_only=False, log_callback=None):
    """Wait for the receiver thread to publish a response without polling."""
    global last_rx_frame
    deadline = time.monotonic() + timeout_ms / 1000.0
    with rx_condition:
        while True:
            frame = last_rx_frame
            if frame is not None and len(frame) > 0:
                first_byte = frame[0]
                if first_byte == 0x85:
                    _log(
                        "Received 0x85 header (busy/multi-frame) — waiting for final response...",
                        log_callback,
                    )
                    last_rx_frame = None
                elif not final_only or first_byte in (0x80, 0x81, 0x82, 0x83):
                    return frame

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            rx_condition.wait(timeout=remaining)
            print_queued_messages(log_callback)


def send_and_get_rx(comm: OpenLinkComm, hex_cmd: str, timeout_ms=10000, log_callback=None) -> bytes:
    """
    Send command and wait for response from MCU.
    Inspects 0x85 header flow control before transmitting and filters 0x85 response frames.
    """
    global last_rx_frame

    # 1. Flow control: inspect header before transmitting next command (header != 0x85)
    if not wait_if_header_0x85(comm, timeout_ms=timeout_ms, log_callback=log_callback):
        return None

    with rx_condition:
        last_rx_frame = None

    _log(f"\n--- [TX]: {hex_cmd} ---", log_callback)
    success = comm.send_hex(hex_cmd, timeout_ms=timeout_ms)
    print_queued_messages(log_callback)

    if not success:
        _log("Timeout or no response from MCU!", log_callback)
        return None

    response = _wait_for_response(timeout_ms=timeout_ms, log_callback=log_callback)
    if response is None:
        _log("Timeout or no final response (header != 0x85) from MCU!", log_callback)
    return response


def send_and_get_final_rx(comm: OpenLinkComm, hex_cmd: str, timeout_ms=10000, log_callback=None) -> bytes:
    """
    Send command and wait for the final response from MCU.
    - 0x85: keep waiting (multi-frame response)
    - 0x80/0x81: show result
    - 0x82/0x83: cannot get data
    """
    global last_rx_frame

    # Flow control: inspect header before transmitting next command (header != 0x85)
    if not wait_if_header_0x85(comm, timeout_ms=timeout_ms, log_callback=log_callback):
        return None

    with rx_condition:
        last_rx_frame = None

    _log(f"\n--- [TX]: {hex_cmd} ---", log_callback)
    success = comm.send_no_wait(bytes.fromhex("".join(hex_cmd.strip().split())))
    print_queued_messages(log_callback)

    if not success:
        _log("⚠️ Failed to send command!", log_callback)
        return None

    response = _wait_for_response(
        timeout_ms=timeout_ms, final_only=True, log_callback=log_callback
    )
    if response is None:
        _log("⚠️ Timeout or no response from MCU!", log_callback)
    return response

def _first_cmd_failed(rx_bytes, log_callback=None) -> bool:
    """
    Check the feedback of the FIRST script command (normally the Target
    select command '70 01 01 01' / '70 01 01 11').
    A response header of 0x82 / 0x83 means 'Cannot get data' ->
    show FAIL and stop the update immediately.
    Returns True when the update must be stopped.
    """
    if rx_bytes and rx_bytes[0] in (0x82, 0x83):
        _log(
            f"❌ FAIL: Device responded {rx_bytes.hex(' ').upper()} "
            f"(82/83 = Cannot get data) to the first command!",
            log_callback,
        )
        _log("🛑 Update stopped!", log_callback)
        return True
    return False


def execute_command_list(comm: OpenLinkComm, cmd_list: list, log_callback=None, progress_callback=None) -> bool:
    """Send commands sequentially from a prepared list (for CSV or single Hex)"""
    total = len(cmd_list)
    first_cmd_checked = False
    for idx, cmd in enumerate(cmd_list, start=1):
        # Handle DELAY tag in command list
        if cmd.startswith("DELAY:"):
            delay_ms = int(cmd.split(":")[1])
            # _log(f"Delaying for {delay_ms / 1000.0}s...", log_callback)
            time.sleep(delay_ms / 1000.0)
            continue

        # Report progress (0.0 to 1.0)
        if progress_callback:
            progress_callback(idx / total, idx, total)

        rx = send_and_get_rx(comm, cmd, log_callback=log_callback)
        if rx is None:
            return False

        # Check feedback of the FIRST command (normally Target select
        # "70 01 01 01" / "70 01 01 11"): 82/83 -> show FAIL and stop.
        if not first_cmd_checked:
            first_cmd_checked = True
            if cmd.strip().upper().startswith("70") and _first_cmd_failed(rx, log_callback):
                return False
    return True

def execute_bin_flashing_sequence(comm: OpenLinkComm, script_data: dict, log_callback=None, progress_callback=None) -> bool:
    """Execute the Update Flashing command sequence to the MCU (for BIN file)"""
    script_commands = script_data["script_commands"]
    total_bytes = script_data["total_bytes"]
    total_commands = len(script_commands)

    # Calculate X7 X8 X9 from total_bytes (Convert total_bytes -> Little Endian 3 bytes)
    bytes_3le = total_bytes.to_bytes(3, byteorder='little')
    x7 = f"{bytes_3le[0]:02X}"
    x8 = f"{bytes_3le[1]:02X}"
    x9 = f"{bytes_3le[2]:02X}"

    _log("\nStarting to send Update command sequence to Tool...", log_callback)
    x1, x2, x3, x4, x5, x6 = None, None, None, None, None, None
    first_cmd_checked = False

    for idx, cmd in enumerate(script_commands, start=1):
        # Handle DELAY command
        if cmd.startswith("DELAY:"):
            delay_ms = int(cmd.split(":")[1])
            # _log(f"Delaying for {delay_ms / 1000.0}s...", log_callback)
            time.sleep(delay_ms / 1000.0)
            continue

        # Report progress
        if progress_callback:
            progress_callback(idx / total_commands, idx, total_commands)

        # 1. Dynamic Command 4: 74 <SeqID> 08 11 00 X5 X6 X1 X2 X3 X4 <checksum>
        if cmd.startswith("DYNAMIC_CMD_4:"):
            seq_id = cmd.split(":")[1]
            if not all([x1, x2, x3, x4, x5, x6]):
                # _log("Missing parameters X1..X6 for step 4 command!", log_callback)
                _log("Cannot not send command")
                return False
            cmd = build_frame(f"74 {seq_id} 08 11 00 {x5} {x6} {x1} {x2} {x3} {x4}")

        # 2. Dynamic Command 5: 74 <SeqID> 08 11 X7 X8 X9 X1 X2 X3 X4 <checksum>
        elif cmd.startswith("DYNAMIC_CMD_5:"):
            seq_id = cmd.split(":")[1]
            if not all([x1, x2, x3, x4]):
                # _log("Missing parameters X1..X4 for step 5 command!", log_callback)
                _log("Cannot not send command")
                return False
            cmd = build_frame(f"74 {seq_id} 08 11 {x7} {x8} {x9} {x1} {x2} {x3} {x4}")

        # 3. Send the command
        rx_bytes = send_and_get_rx(comm, cmd, log_callback=log_callback)
        if rx_bytes is None:
            _log(f"Failed at command {idx}/{len(script_commands)}", log_callback)
            return False

        # Check feedback of the FIRST command (normally Target select
        # "70 01 01 01" / "70 01 01 11"): 82/83 -> show FAIL and stop.
        if not first_cmd_checked:
            first_cmd_checked = True
            if cmd.strip().upper().startswith("70") and _first_cmd_failed(rx_bytes, log_callback):
                return False

        # 4. Extract Params (X1, X2, X3, X4, X5, X6) if response to "74 <SeqID> 01 15"
        # Data format after header (3 bytes): 01 X1 X2 X3 X4 00 00 00 00 00 X5 X6 01 00 00 00
        if "01 15" in cmd and len(rx_bytes) >= 18:
            if rx_bytes[0] in (0x81, 0x83, 0x85):
                # rx_bytes[0..2] là Header + SeqID + Length
                # rx_bytes[3] = 01
                x1 = f"{rx_bytes[4]:02X}"
                x2 = f"{rx_bytes[5]:02X}"
                x3 = f"{rx_bytes[6]:02X}"
                x4 = f"{rx_bytes[7]:02X}"
                # rx_bytes[8..12] = 00 00 00 00 00
                x5 = f"{rx_bytes[13]:02X}"
                x6 = f"{rx_bytes[14]:02X}"
                
                # _log(f"[Extracted Params] X1={x1}, X2={x2}, X3={x3}, X4={x4}, X5={x5}, X6={x6}", log_callback)
            else:
                _log(f"Warning: Unexpected response header: {rx_bytes[0]:02X}", log_callback)

    _log("\n=== FIRMWARE UPDATE PROCESS COMPLETED SUCCESSFULLY ===", log_callback)
    return True