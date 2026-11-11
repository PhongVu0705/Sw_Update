"""The only JavaScript API boundary; every call returns an ok/data envelope."""

from functools import wraps
from inspect import signature
import logging

from backend.domain.errors import InputError, UpdateCancelled
from backend.domain.protocol import BAUD_RATE

logger = logging.getLogger(__name__)


def response_boundary(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        try:
            return {"ok": True, "data": method(self, *args, **kwargs)}
        except InputError as error:
            logger.warning("%s rejected: %s", method.__name__, error)
            return {"ok": False, "error": str(error)}
        except UpdateCancelled:
            logger.info("%s cancelled", method.__name__)
            return {"ok": True, "data": {"cancelled": True}}
        except Exception:
            logger.exception("%s failed", method.__name__)
            return {"ok": False, "error": "Unable to complete the request. Check logs and try again."}
    # pywebview uses getfullargspec, which requires an explicit signature here.
    wrapped.__signature__ = signature(method)
    return wrapped


class JSAPI:
    def __init__(self, service, file_dialog):
        self._service = service
        self._file_dialog = file_dialog

    @response_boundary
    def get_ports(self):
        return self._service.get_ports()

    @response_boundary
    def get_connection_state(self):
        return self._service.connection_state()

    @response_boundary
    def connect_port(self, port, baud_rate=BAUD_RATE):
        return self._service.connect(port, baud_rate)

    @response_boundary
    def disconnect_port(self):
        return self._service.disconnect()

    @response_boundary
    def select_file(self):
        return self._service.select_file(self._file_dialog.choose)

    @response_boundary
    def run_mass_update(self, port, file_id, tool_type="M12", expected_fw="", auto_pcba=False):
        return self._service.start_update(port, file_id, tool_type, expected_fw, auto_pcba)

    @response_boundary
    def pause_update(self):
        return self._service.control_update("pause")

    @response_boundary
    def resume_update(self):
        return self._service.control_update("resume")

    @response_boundary
    def stop_update(self):
        return self._service.control_update("stop")

    @response_boundary
    def run_hex_command(self, hex_command):
        return self._service.run_hex(hex_command)

    @response_boundary
    def run_quick_command(self, command_type):
        return self._service.run_quick(command_type)
