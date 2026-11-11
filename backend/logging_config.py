"""Application-owned UTF-8 rotating logging and uncaught exception hooks."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys
import threading

from backend.app_paths import log_file


def configure_logging(path=None):
    destination = Path(path) if path is not None else log_file()
    root = logging.getLogger()
    for handler in root.handlers[:]:
        if getattr(handler, "_fw_update_owned", False):
            root.removeHandler(handler)
            handler.close()
    root.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    console = logging.StreamHandler(sys.stderr)
    console._fw_update_owned = True
    console.setFormatter(formatter)
    root.addHandler(console)
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(destination, maxBytes=5 * 1024 * 1024,
                                           backupCount=3, encoding="utf-8")
        file_handler._fw_update_owned = True
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError:
        logging.getLogger(__name__).warning("Cannot open log file %s; continuing with stderr", destination)

    def uncaught(exc_type, value, traceback):
        if not issubclass(exc_type, SystemExit):
            logging.getLogger("backend.unhandled").critical("Unhandled exception", exc_info=(exc_type, value, traceback))

    def thread_uncaught(args):
        if not issubclass(args.exc_type, SystemExit):
            logging.getLogger("backend.unhandled").error("Unhandled thread exception: %s", args.thread.name,
                exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    sys.excepthook = uncaught
    threading.excepthook = thread_uncaught
    return destination
