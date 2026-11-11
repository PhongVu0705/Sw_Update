"""Interactive terminal UI; delegates device work to the desktop services."""

import threading

from backend.adapters.desktop_events import DesktopEvents
from backend.domain.errors import InputError
from backend.services.device_service import DeviceService


class ConsoleEvents(DesktopEvents):
    def __init__(self):
        super().__init__()
        self.finished = threading.Event()

    def emit(self, event, *args):
        if event == "onLogFromPy" and args[0].startswith(("[TX", "[MCU RX")):
            print(args[0])
        elif event == "onMassResult":
            print("PASS" if args[0]["pass"] else "FAIL", args[0].get("detected"), args[0].get("reason"))
        elif event == "onMassFinished":
            self.finished.set()


def run():
    events = ConsoleEvents()
    service = DeviceService(events)
    try:
        ports = service.get_ports()["ports"]
        if not ports:
            print("No COM ports found. Connect a device and try again.")
            return 0
        for index, item in enumerate(ports, start=1):
            print(f"[{index}] {item['port']}: {item['description']}")
        choice = input("Choose port number: ").strip()
        if not choice.isdigit() or not 1 <= int(choice) <= len(ports):
            raise InputError("Invalid port selection.")
        port = ports[int(choice) - 1]["port"]
        service.connect(port)
        while True:
            choice = input("\n1. Flash BIN/CSV and verify\n2. Quick command\n3. Raw HEX\nq. Exit\n> ").strip()
            if choice.lower() in ("q", "exit"):
                break
            try:
                if choice == "1":
                    selected = service.select_file(lambda: input("Firmware path: ").strip().strip("\"'"))
                    tool = input("Tool (M12/M18) [M12]: ").strip().upper() or "M12"
                    expected = input("Expected firmware version: ").strip()
                    events.finished.clear()
                    service.start_update(port, selected["id"], tool, expected)
                    events.finished.wait()
                elif choice == "2":
                    from backend.domain.protocol import QUICK_COMMANDS
                    print(", ".join(QUICK_COMMANDS))
                    print(service.run_quick(input("Command key: ").strip()))
                else:
                    command = input("HEX: ").strip() if choice == "3" else choice
                    print(service.run_hex(command))
            except InputError as error:
                print(error)
    except KeyboardInterrupt:
        print("\nCancelled by operator.")
    finally:
        service.shutdown()
    return 0
