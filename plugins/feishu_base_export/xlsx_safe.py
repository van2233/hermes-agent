"""Reject non-OOXML payloads, path tricks, and highly compressible zip bombs."""

from __future__ import annotations

import io
import zipfile

MAX_BYTES = 32 * 1024 * 1024
MAX_ENTRIES = 200
MAX_UNCOMPRESSED = 64 * 1024 * 1024
_RATIO_FLOOR = 1_000_000
_MAX_RATIO = 100


class UnsafeFile(ValueError):
    pass


def assert_safe_xlsx(data: bytes) -> None:
    if not data.startswith(b"PK") or len(data) > MAX_BYTES:
        raise UnsafeFile("magic-or-size")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise UnsafeFile("zip") from exc
    infos = archive.infolist()
    if len(infos) > MAX_ENTRIES:
        raise UnsafeFile("entries")
    names = []
    uncompressed = 0
    for info in infos:
        _reject_name(info.filename)
        names.append(info.filename)
        uncompressed += info.file_size
        if uncompressed > MAX_UNCOMPRESSED:
            raise UnsafeFile("uncompressed")
        if info.file_size > _RATIO_FLOOR and info.file_size / max(info.compress_size, 1) > _MAX_RATIO:
            raise UnsafeFile("ratio")
    if "[Content_Types].xml" not in names:
        raise UnsafeFile("ooxml")


def _reject_name(name: str) -> None:
    parts = name.replace("\\", "/").split("/")
    if name.startswith("/") or name.startswith("\\") or any(part == ".." for part in parts):
        raise UnsafeFile("path")
