"""Read-only bundle resources and user-writable application log paths."""

import os
from pathlib import Path
import sys


def is_frozen():
    return bool(getattr(sys, "frozen", False))


def resource_base():
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[1]


def frontend_index():
    return resource_base() / "fw_update_UI" / "dist" / "index.html"


def log_file():
    if override := os.environ.get("FW_UPDATE_LOG_DIR"):
        return Path(override).expanduser().resolve() / "app.log"
    if is_frozen():
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "FWUpdateTool" / "logs" / "app.log"
    return resource_base() / "logs" / "app.log"
