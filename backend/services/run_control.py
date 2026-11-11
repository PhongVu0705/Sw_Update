"""Cooperative pause/stop checks, including delays and response waits."""

import threading
import time

from backend.domain.errors import UpdateCancelled


class RunController:
    def __init__(self):
        self._stop = threading.Event()
        self._pause = threading.Event()

    def reset(self):
        self._stop.clear()
        self._pause.clear()

    def stop(self):
        self._stop.set()

    def pause(self):
        self._pause.set()

    def resume(self):
        self._pause.clear()

    def stop_requested(self):
        return self._stop.is_set()

    def checkpoint(self):
        while self._pause.is_set() and not self._stop.is_set():
            self._stop.wait(0.05)
        if self._stop.is_set():
            raise UpdateCancelled("Stopped by operator")

    def wait(self, seconds):
        remaining = seconds
        while remaining > 0:
            self.checkpoint()
            start = time.monotonic()
            self._stop.wait(min(0.05, remaining))
            remaining -= time.monotonic() - start
        self.checkpoint()
