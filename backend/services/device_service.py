"""Own the serial session and serialize workflows across pywebview threads."""

from contextlib import contextmanager
import logging
import threading
from uuid import uuid4

from backend.adapters.firmware_files import FirmwareRegistry, read_csv_commands
from backend.adapters.serial_transport import OpenLinkComm, list_ports
from backend.domain.errors import InputError, UpdateCancelled
from backend.domain.firmware import build_bin_script, csv_initial_commands
from backend.domain.protocol import BAUD_RATE, validate_port, validate_tool, validate_version
from backend.services.command_runner import CommandRunner
from backend.services.firmware_update import FirmwareUpdater
from backend.services.manual_commands import run_hex, run_quick
from backend.services.pcba_auto_cycle import PcbaAutoCycle

logger = logging.getLogger(__name__)


class DeviceService:
    def __init__(self, events, registry=None, transport_factory=OpenLinkComm,
                 ports_provider=list_ports, updater=None, thread_factory=threading.Thread, auto_cycle=None):
        self.events = events
        self.registry = registry or FirmwareRegistry()
        self._transport_factory = transport_factory
        self._ports_provider = ports_provider
        self._updater = updater or FirmwareUpdater(events)
        self._auto_cycle = auto_cycle or PcbaAutoCycle(events)
        self._thread_factory = thread_factory
        self._lock = threading.RLock()
        self._idle = threading.Condition(self._lock)
        self._operation = None
        self._closing = False
        self._runner = None
        self._comm = None
        self._worker = None

    def get_ports(self):
        return {"ports": self._ports_provider()}

    def connection_state(self):
        with self._lock:
            connected = self._comm is not None and self._comm.is_running
            return {"connected": connected, "port": self._comm.port if connected else None}

    def _claim(self, kind):
        with self._lock:
            if self._closing:
                raise InputError("The application is closing.")
            if self._operation:
                raise InputError("Another device operation is active. Wait for it to finish or stop the update first.")
            token = uuid4().hex[:12]
            self._operation = (token, kind)
            if kind in ("manual", "quick-command", "mass-update") and self._runner:
                self._runner.controller.reset()
        logger.info("operation=%s kind=%s started", token, kind)
        return token

    def _release(self, token, outcome):
        with self._lock:
            if self._operation and self._operation[0] == token:
                self._operation = None
                self._idle.notify_all()
        logger.info("operation=%s outcome=%s", token, outcome)

    @contextmanager
    def _scope(self, kind):
        token = self._claim(kind)
        try:
            yield
        except BaseException:
            self._release(token, "rejected_or_failed")
            raise
        else:
            self._release(token, "completed")

    def _connected_runner(self, port=None):
        with self._lock:
            if self._closing:
                raise InputError("The application is closing.")
            if not self._comm or not self._comm.is_running:
                raise InputError("Connect to the selected COM port first.")
            if port is not None and port != self._comm.port:
                raise InputError("Selected COM port is not connected.")
            return self._runner

    def connect(self, port, baud_rate=BAUD_RATE):
        with self._scope("connect"):
            port = validate_port(port)
            if type(baud_rate) is not int or baud_rate != BAUD_RATE:
                raise InputError("This tool requires a baud rate of 115200.")
            if not any(item["port"] == port for item in self._ports_provider()):
                raise InputError("Selected COM port is unavailable. Refresh the port list.")
            self._disconnect()
            runner = CommandRunner(self.events.log)

            def transport_error():
                runner.on_error()
                self.events.log("Warning: serial connection lost. Check the cable and reconnect.")
                self.events.emit("onConnectionState", {"connected": False, "port": None})

            comm = self._transport_factory(port=port, baud_rate=baud_rate, on_rx=runner.on_rx,
                                           on_tx=runner.on_tx, on_error=transport_error)
            try:
                if not comm.connect():
                    raise InputError("Cannot connect to the selected COM port.")
            except BaseException:
                comm.disconnect()
                raise
            runner.comm = comm
            with self._lock:
                self._runner, self._comm = runner, comm
            self.events.emit("onConnectionState", self.connection_state())
            self.events.log(f"Connected to {port} at {BAUD_RATE} baud.")
            return {"status": "SUCCESS"}

    def _disconnect(self):
        with self._lock:
            comm = self._comm
        if comm:
            comm.disconnect()
        with self._lock:
            self._comm = None
            self._runner = None
        self.events.emit("onConnectionState", {"connected": False, "port": None})

    def disconnect(self):
        with self._scope("disconnect"):
            self._disconnect()
            self.events.log("Disconnected from COM port.")
            return {"status": "SUCCESS"}

    def select_file(self, choose):
        with self._scope("select-file"):
            path = choose()
            return self.registry.register(path) if path else None

    def run_hex(self, command):
        with self._scope("manual"):
            runner = self._connected_runner()
            return run_hex(runner, command)

    def run_quick(self, key):
        with self._scope("quick-command"):
            runner = self._connected_runner()
            return run_quick(runner, key)

    def start_update(self, port, file_id, tool_type="M12", expected_fw="", auto_pcba=False):
        token = self._claim("mass-update")
        try:
            if type(auto_pcba) is not bool:
                raise InputError("Auto PCBA mode must be true or false.")
            port = validate_port(port)
            tool_type = validate_tool(tool_type)
            expected_fw = validate_version(expected_fw)
            runner = self._connected_runner(port)
            extension, snapshot = self.registry.snapshot(file_id)
            prepared = build_bin_script(snapshot, tool_type) if extension == "bin" else (
                csv_initial_commands(tool_type) + read_csv_commands(snapshot)
            )
            runner.controller.checkpoint()
            command_count = len(prepared["script_commands"] if isinstance(prepared, dict) else prepared)
            logger.info("operation=%s prepared bytes=%d commands=%d tool=%s", token, len(snapshot), command_count, tool_type)
            worker = self._thread_factory(
                target=self._update_worker, args=(token, runner, prepared, tool_type, expected_fw, auto_pcba),
                name=f"firmware-{token}", daemon=True,
            )
            with self._lock:
                self._worker = worker
            worker.start()
        except BaseException:
            self._release(token, "rejected_or_failed")
            raise
        return {"status": "STARTED"}

    def _update_worker(self, token, runner, prepared, tool_type, expected_fw, auto_pcba):
        reason = ""
        result = None
        flashing = False
        passed = failed = 0

        def record_result(value):
            nonlocal passed, failed, result
            result = value
            passed += int(value["pass"])
            failed += int(not value["pass"])
            self.events.emit("onMassResult", {**value, "expected": expected_fw})
            self.events.log(f"MASS UPDATE {'PASS' if value['pass'] else 'FAIL'}")

        def flash_one():
            nonlocal result, flashing
            result = None
            flashing = True
            self.events.emit("onMassStage", "programming")
            self.events.log("Starting flash and firmware verification sequence.")
            value = self._updater.run(runner, prepared, tool_type, expected_fw)
            runner.controller.checkpoint()
            record_result(value)
            flashing = False

        try:
            if auto_pcba:
                self._auto_cycle.run(runner, tool_type, flash_one)
            else:
                flash_one()
        except UpdateCancelled:
            self.events.log("Mass update stopped by operator.")
        except InputError as error:
            reason = str(error)
            logger.warning("operation=%s update rejected: %s", token, reason)
            if flashing and not runner.controller.stop_requested():
                record_result({"pass": False, "detected": None, "reason": reason})
        except Exception:
            logger.exception("operation=%s firmware update failed", token)
            reason = "Unable to update firmware. Check logs and retry."
            if flashing and not runner.controller.stop_requested():
                record_result({"pass": False, "detected": None, "reason": reason})
        finally:
            stopped = runner.controller.stop_requested()
            outcome = "cancelled" if stopped else "failed" if reason else "passed" if result and result["pass"] else "failed"
            logger.info("operation=%s completed=%d passed=%d failed=%d auto_pcba=%s", token, passed + failed, passed, failed, auto_pcba)
            self._release(token, outcome)
            self.events.emit("onMassStage", "done")
            self.events.emit("onMassFinished", {"stopped": stopped, "reason": reason})

    def control_update(self, action):
        with self._lock:
            if not self._operation or self._operation[1] != "mass-update" or not self._runner:
                raise InputError("No firmware update is running.")
            getattr(self._runner.controller, action)()
        self.events.log({"stop": "Stop requested — aborting update...", "pause": "Update paused.", "resume": "Update resumed."}[action])
        return {"status": "SUCCESS"}

    def shutdown(self):
        """Cancel active work before closing its serial transport."""
        with self._idle:
            self._closing = True
            if self._runner:
                self._runner.controller.stop()
            idle = self._idle.wait_for(lambda: self._operation is None, timeout=5)
        if not idle:
            logger.warning("Timed out waiting for active operation during shutdown")
        self._disconnect()
