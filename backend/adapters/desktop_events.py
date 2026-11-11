"""Deliver pywebview callbacks and redact authentication bytes from UI logs."""

import json
import logging
import re
import threading

logger = logging.getLogger(__name__)
EVENTS = frozenset(("onLogFromPy", "onConnectionState", "onProgressFromPy", "onMassStage", "onMassResult", "onMassFinished"))
AUTH_FRAME = re.compile(r"\b01\s+[0-9A-F]{2}\s+0A\s+00\s+3B(?:\s+[0-9A-F]{2})+", re.IGNORECASE)


class DesktopEvents:
    def __init__(self):
        self._window = None
        self._lock = threading.RLock()

    def attach(self, window):
        with self._lock:
            self._window = window

    def emit(self, event, *args):
        if event not in EVENTS:
            raise ValueError("Unsupported desktop event")
        with self._lock:
            window = self._window
        if window is None:
            return
        payload = ", ".join(json.dumps(value, ensure_ascii=True) for value in args)
        try:
            window.evaluate_js(f"window.{event} && window.{event}({payload});")
        except Exception:
            # Window teardown can race a worker callback; never fail a flash for this.
            logger.debug("Desktop callback unavailable: %s", event)

    def log(self, message):
        text = AUTH_FRAME.sub("[authentication frame redacted]", str(message))
        text = " ".join(text.split())
        self.emit("onLogFromPy", text)
        # Transport payloads are for the live terminal, never the persistent log.
        if not re.search(r"\b(?:[0-9A-F]{2}\s+){3,}[0-9A-F]{2}\b|\[TX|\[MCU RX|Data:", text, re.IGNORECASE):
            logger.info("%s", text)
