"""Register native-selected files and read validated, immutable snapshots."""

import csv
from dataclasses import dataclass
import io
import os
from pathlib import Path
import threading
from uuid import uuid4

from backend.domain.errors import InputError
from backend.domain.firmware import MAX_BIN_BYTES, MAX_CSV_BYTES
from backend.domain.protocol import validate_hex


@dataclass(frozen=True)
class RegisteredFile:
    path: Path
    size: int
    mtime_ns: int
    device: int
    inode: int


class FirmwareRegistry:
    def __init__(self):
        self._files = {}
        self._lock = threading.RLock()

    @staticmethod
    def _check_file(path, stat):
        limit = MAX_BIN_BYTES if path.suffix.lower() == ".bin" else MAX_CSV_BYTES
        if path.suffix.lower() not in (".bin", ".csv"):
            raise InputError("Choose a .bin or .csv firmware file.")
        if stat.st_size <= 0:
            raise InputError("The firmware file is empty.")
        if stat.st_size > limit:
            raise InputError(f"The firmware file exceeds the {limit}-byte size limit.")

    def register(self, path):
        """Only call with a path obtained from a trusted native/CLI flow."""
        try:
            resolved = Path(path).resolve(strict=True)
            if not resolved.is_file():
                raise InputError("Choose a regular firmware file.")
            stat = resolved.stat()
            self._check_file(resolved, stat)
        except OSError as error:
            raise InputError("Cannot read the selected firmware. Select it again.") from error
        token = uuid4().hex
        with self._lock:
            self._files[token] = RegisteredFile(resolved, stat.st_size, stat.st_mtime_ns, stat.st_dev, stat.st_ino)
        return {"id": token, "name": resolved.name, "size": stat.st_size, "ext": resolved.suffix.lower()[1:]}

    @staticmethod
    def _unchanged(entry, stat):
        return (entry.size, entry.mtime_ns, entry.device, entry.inode) == (
            stat.st_size, stat.st_mtime_ns, stat.st_dev, stat.st_ino,
        )

    def snapshot(self, token):
        if not isinstance(token, str) or len(token) != 32:
            raise InputError("Select firmware using Browse before starting.")
        with self._lock:
            entry = self._files.get(token)
        if entry is None:
            raise InputError("Firmware selection expired. Select the file again.")
        try:
            with entry.path.open("rb") as source:
                before = os.fstat(source.fileno())
                if not self._unchanged(entry, before):
                    raise InputError("Firmware changed after selection. Select the file again.")
                self._check_file(entry.path, before)
                data = source.read(entry.size + 1)
                after = os.fstat(source.fileno())
            if len(data) != entry.size or not self._unchanged(entry, after) or not self._unchanged(entry, entry.path.stat()):
                raise InputError("Firmware changed while being read. Select the file again.")
        except OSError as error:
            raise InputError("Selected firmware is no longer readable. Select it again.") from error
        return entry.path.suffix.lower()[1:], data


def read_csv_commands(data):
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise InputError("CSV must use UTF-8 encoding.") from error
    commands = []
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        fields = reader.fieldnames or []
        if fields.count("Message") != 1 or len(fields) != len(set(fields)):
            raise InputError("CSV must contain one Message column and no duplicate headers.")
        for row_number, row in enumerate(reader, start=2):
            if None in row or any(value is None for value in row.values()):
                raise InputError(f"CSV row {row_number} does not match its header.")
            command = row["Message"].strip()
            if not command.upper().startswith("74"):
                continue
            try:
                command = validate_hex(command)
            except InputError as error:
                raise InputError(f"CSV row {row_number} contains an invalid HEX command.") from error
            frame = bytes.fromhex(command)
            if len(frame) < 4 or len(frame) not in (3 + frame[2], 5 + frame[2]):
                raise InputError(f"CSV row {row_number} has an invalid command length.")
            commands.append(command)
            if frame[0] == 0x74 and frame[2] == 1 and frame[3] in (0x10, 0x13):
                commands.append("DELAY:3000")
    except csv.Error as error:
        raise InputError("CSV is malformed. Check its columns and quoting.") from error
    if not commands:
        raise InputError("CSV contains no firmware commands starting with 74.")
    return commands
