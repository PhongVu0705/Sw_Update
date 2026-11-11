"""Native file selection; paths never originate in JavaScript requests."""

from backend.domain.errors import InputError


class FirmwareDialog:
    def __init__(self):
        self._window = None

    def attach(self, window):
        self._window = window

    def choose(self):
        if self._window is None:
            raise InputError("File dialog unavailable. Open the desktop app.")
        import webview

        open_dialog = webview.FileDialog.OPEN if hasattr(webview, "FileDialog") else webview.OPEN_DIALOG
        result = self._window.create_file_dialog(
            open_dialog,
            allow_multiple=False,
            file_types=("Firmware Files (*.bin;*.csv)",),
        )
        return result[0] if result else None
