"""Desktop composition and native window/splash lifecycle."""

import logging
import os
import threading

import webview

from backend.adapters.desktop_events import DesktopEvents
from backend.adapters.file_dialog import FirmwareDialog
from backend.api import JSAPI
from backend.app_paths import frontend_index
from backend.services.device_service import DeviceService

logger = logging.getLogger(__name__)


def close_boot_splash():
    try:
        import pyi_splash
    except ImportError:
        return
    try:
        pyi_splash.close()
    except Exception:
        logger.debug("Boot splash already closed")


def run():
    source = os.environ.get("FW_UPDATE_UI_URL")
    if not source:
        index = frontend_index()
        if not index.is_file():
            raise FileNotFoundError("Vite UI build not found. Run 'npm.cmd --prefix fw_update_UI run build' first.")
        source = str(index)
    events = DesktopEvents()
    file_dialog = FirmwareDialog()
    service = DeviceService(events)
    api = JSAPI(service, file_dialog)
    window = webview.create_window(
        title="FW Update Tool", url=source, js_api=api,
        width=1280, height=800, min_size=(1024, 700), resizable=True,
    )
    events.attach(window)
    file_dialog.attach(window)
    watchdog = threading.Timer(20, close_boot_splash)
    watchdog.daemon = True

    def shown():
        watchdog.cancel()
        close_boot_splash()

    def closing():
        # Closing runs on the native UI thread: evaluate_js here would deadlock.
        events.attach(None)
        service.shutdown()

    window.events.shown += shown
    window.events.closing += closing
    watchdog.start()
    logger.info("Desktop application starting")
    try:
        webview.start(debug=False, http_server=True)
    finally:
        watchdog.cancel()
        events.attach(None)
        service.shutdown()
        close_boot_splash()
        logger.info("Desktop application stopped")
    return 0
