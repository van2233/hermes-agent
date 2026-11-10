"""Draw a bar chart from already-bounded numbers. Not a Feishu screenshot."""

from __future__ import annotations

import io
import struct
import zlib
from pathlib import Path

from .chart_data import ChartTable
from .disclaimer_rgb import HEIGHT as MARK_H
from .disclaimer_rgb import WIDTH as MARK_W
from .disclaimer_rgb import disclaimer_rgb

_WIDTH = 640
_HEIGHT = 360
_ORIGIN = (8, 8)
_INK = (160, 0, 0)
CHART_CAPTION = "据聚合数据重绘，非飞书原图。样式与飞书原图不同。"
FONT_CANDIDATES = (
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyh.ttf",
    r"C:\Windows\Fonts\simhei.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)


def render_pixels(table: ChartTable) -> tuple[int, int, bytes]:
    canvas = bytearray(b"\xff" * (_WIDTH * _HEIGHT * 3))
    _blit(canvas, disclaimer_rgb(), *_ORIGIN)
    _bars(canvas, table.values)
    return _WIDTH, _HEIGHT, bytes(canvas)


def render_chart(table: ChartTable, fmt: str) -> bytes:
    if fmt not in {"png", "pdf"}:
        raise ValueError("format")
    width, height, raw = render_pixels(table)
    labeled = _label_image(width, height, raw, table)
    if labeled is not None:
        buffer = io.BytesIO()
        labeled.save(buffer, format="PNG" if fmt == "png" else "PDF")
        return buffer.getvalue()
    if fmt == "png":
        return _png(width, height, raw)
    if fmt == "pdf":
        return _pdf(width, height, raw)
    raise ValueError("format")


def first_font(candidates: tuple[str, ...] = FONT_CANDIDATES) -> str:
    for item in candidates:
        if Path(item).is_file():
            return item
    return ""


def _blit(canvas: bytearray, bitmap: bytes, left: int, top: int) -> None:
    if left < 0 or top < 0 or left + MARK_W > _WIDTH or top + MARK_H > _HEIGHT:
        raise RuntimeError("disclaimer does not fit")
    for y in range(MARK_H):
        src = y * MARK_W * 3
        dst = ((top + y) * _WIDTH + left) * 3
        canvas[dst:dst + MARK_W * 3] = bitmap[src:src + MARK_W * 3]


def _bars(canvas: bytearray, values: tuple[float, ...]) -> None:
    peak = max(values) if values else 0
    if peak <= 0:
        return
    top = _ORIGIN[1] + MARK_H + 16
    usable = _HEIGHT - top - 16
    gap = 8
    width = max(4, (_WIDTH - 32 - gap * len(values)) // max(len(values), 1))
    x = 16
    for value in values:
        height = int(usable * (value / peak))
        _rect(canvas, x, top + usable - height, width, height, _INK)
        x += width + gap


def _rect(canvas: bytearray, left: int, top: int, width: int, height: int, color: tuple[int, int, int]) -> None:
    if width <= 0 or height <= 0:
        return
    pixel = bytes(color)
    for y in range(max(top, 0), min(top + height, _HEIGHT)):
        start = (y * _WIDTH + max(left, 0)) * 3
        end = (y * _WIDTH + min(left + width, _WIDTH)) * 3
        canvas[start:end] = pixel * ((end - start) // 3)


def _label_image(width: int, height: int, rgb: bytes, table: ChartTable):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return None
    image = Image.frombytes("RGB", (width, height), rgb)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    chosen = first_font()
    if chosen:
        try:
            font = ImageFont.truetype(chosen, size=14)
        except OSError:
            font = ImageFont.load_default()
    draw.text((8, _ORIGIN[1] + MARK_H + 2), CHART_CAPTION, fill=(0, 0, 0), font=font)
    return image


def _png(width: int, height: int, rgb: bytes) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    rows = b"".join(b"\x00" + rgb[y * width * 3:(y + 1) * width * 3] for y in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b"")


def _pdf(width: int, height: int, rgb: bytes) -> bytes:
    image = zlib.compress(rgb)
    content = f"q {width} 0 0 {height} 0 0 cm /Im Do Q".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
        (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] "
            f"/Resources << /XObject << /Im 4 0 R >> >> /Contents 5 0 R >> >>"
        ).encode("ascii"),
        (
            f"<< /Type /XObject /Subtype /Image /Width {width} /Height {height} "
            f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode /Length {len(image)} >>\nstream\n"
        ).encode("ascii") + image + b"\nendstream",
        f"<< /Length {len(content)} >>\nstream\n".encode("ascii") + content + b"\nendstream",
    ]
    return _pdf_doc(objects)


def _pdf_doc(objects: list[bytes]) -> bytes:
    chunks = [b"%PDF-1.4\n"]
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(sum(len(part) for part in chunks))
        chunks.append(f"{number} 0 obj\n".encode("ascii") + body + b"\nendobj\n")
    xref_at = sum(len(part) for part in chunks)
    xref = [f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"]
    xref.extend(f"{offset:010d} 00000 n \n" for offset in offsets[1:])
    trailer = (
        f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n"
    )
    return b"".join(chunks) + "".join(xref).encode("ascii") + trailer.encode("ascii")
