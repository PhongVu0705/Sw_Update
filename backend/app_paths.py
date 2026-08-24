"""
app_paths.py — Central path resolution for development and frozen builds.

When packaged with PyInstaller / auto-py-to-exe (--onefile), all bundled
files are extracted to a temporary directory exposed as ``sys._MEIPASS``
which is DELETED when the app exits. Therefore:

- Read-only resources (the frontend bundle) must be resolved from
  ``sys._MEIPASS`` while frozen.
- Anything the app writes (the ``temp`` working folder) must go next to
  the executable, never inside the extraction dir.

In development (running main.py directly) behaviour is unchanged:
resources come from the project root and temp goes to ``backend/temp``.
"""

import os
import sys


def is_frozen() -> bool:
    """True when running from a PyInstaller bundle."""
    return bool(getattr(sys, "frozen", False))


def resource_base() -> str:
    """
    Base directory for READ-ONLY bundled resources (frontend files).

    Frozen : PyInstaller extraction dir (sys._MEIPASS)
    Dev    : project root (parent of the backend/ folder)
    """
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return meipass
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def writable_base() -> str:
    """
    Base directory for WRITABLE files created by the app.

    Frozen : folder containing the .exe (stable across runs)
    Dev    : backend/ folder (same as before packaging)
    """
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def temp_dir(create: bool = True) -> str:
    """
    Working 'temp' directory used by BIN/CSV processing
    (<writable_base>/temp). Created on demand unless create=False.
    """
    path = os.path.join(writable_base(), "temp")
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def frontend_index() -> str:
    """Path to the bundled frontend entry page (index.html)."""
    return os.path.join(resource_base(), "frontend", "index.html")