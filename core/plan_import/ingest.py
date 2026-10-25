"""Stage 0 — uploaded files → `Source`s (one per PDF page, embedded PDF image or image file), and the pictures the
Creator looks at: contact sheets of all sources and a single source with a 0–1 grid for reading boxes and points.

PDFs: pypdfium2 renders pages and reads their text, pypdf lists embedded images (not PyMuPDF: AGPL, D-009). A file
that cannot be read becomes a warning ("<name>: <why>"); the rest go on."""

import io
import logging
from io import BytesIO

import cv2
import numpy as np
import pypdf
import pypdfium2
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

from core.plan_import.model import Source

register_heif_opener()  # iPhone photos (HEIC) open like any image
logging.getLogger("pypdf").setLevel(logging.ERROR)  # "Ignoring wrong pointing object" on real-world PDFs

PROCESS_MAX_SIDE = 2400  # px, long side of every source image
MODEL_MAX_SIDE = 1568  # px, long side of every image sent to the model
PDF_DPI = 200
MIN_EMBEDDED_SIDE = 800  # px, smaller embedded images (logos, icons) are skipped
MAX_SOURCES = 40  # pages + images per import; the rest are reported, not read
SAME_ASPECT = 0.03  # an embedded image with the page's aspect ratio is the page itself (a scan)


def fit(image: np.ndarray, max_side: int) -> np.ndarray:
    scale = max_side / max(image.shape[:2])
    if scale >= 1:
        return image
    size = (round(image.shape[1] * scale), round(image.shape[0] * scale))
    return cv2.resize(image, size, interpolation=cv2.INTER_AREA)


def from_pil(picture: Image.Image) -> np.ndarray:
    picture = ImageOps.exif_transpose(picture).convert("RGB")
    return fit(np.asarray(picture)[:, :, ::-1].copy(), PROCESS_MAX_SIDE)


def pdf_parts(name: str, data: bytes, limit: int = MAX_SOURCES) -> tuple[list[tuple[str, np.ndarray, str]], int]:
    """Each page rendered straight at the working size (≤ PDF_DPI, long side ≤ PROCESS_MAX_SIDE — a plan sheet can be
    metres wide), plus embedded images that are not just the page again (a scanned page holds one full-page image).
    Stops after `limit` parts; returns them and how many the PDF has in all (pages + kept images, as far as counted)."""
    parts = []
    aspects = []
    document = pypdfium2.PdfDocument(data)
    for index in range(min(len(document), limit)):
        page = document[index]
        width, height = page.get_size()  # points
        scale = min(PDF_DPI / 72, PROCESS_MAX_SIDE / max(width, height, 1))
        picture = page.render(scale=scale).to_pil()
        text = page.get_textpage().get_text_range()
        parts.append((f"{name} p{index + 1}", from_pil(picture), text))
        aspects.append(width / max(height, 1))
    try:
        reader = pypdf.PdfReader(BytesIO(data))
        count = 0
        for page_index, page in enumerate(reader.pages):
            for embedded in page.images:
                picture = Image.open(BytesIO(embedded.data))
                if max(picture.size) < MIN_EMBEDDED_SIDE:
                    continue
                aspect = picture.size[0] / max(picture.size[1], 1)
                if page_index < len(aspects) and abs(aspect - aspects[page_index]) <= SAME_ASPECT * aspects[page_index]:
                    continue
                count += 1
                if len(parts) < limit:
                    parts.append((f"{name} img{count}", from_pil(picture), ""))
    except Exception:  # embedded images are a bonus; the rendered pages already show them
        pass
    return parts, len(document) + count


def load_sources(files: list[tuple[str, bytes]], levels: list[int] | None = None) -> tuple[list[Source], list[str]]:
    """`levels`: the floor of each file as the user gave it (same order); a PDF's pages get level, level + 1, …"""
    sources: list[Source] = []
    warnings: list[str] = []
    for index, (name, data) in enumerate(files):
        try:
            if not data:
                raise ValueError("empty file")
            room = MAX_SOURCES - len(sources)
            if data[:5] == b"%PDF-":
                parts, total = pdf_parts(name, data, max(room, 0))
            else:
                parts = [(name, from_pil(Image.open(BytesIO(data))), "")] if room > 0 else []
                total = 1
        except Exception as error:
            warnings.append(f"{name}: could not read it ({type(error).__name__}: {error})"[:200])
            continue
        if total > len(parts):
            warnings.append(f"{name}: only the first {MAX_SOURCES} pages / images of an import are read; "
                            f"{total - len(parts)} skipped")
        for page, (origin, image, text) in enumerate(parts):
            level = levels[index] + page if levels is not None else None
            sources.append(Source(f"s{len(sources) + 1}", origin, image, text, level))
    return sources, warnings


def png(image: np.ndarray, max_side: int = MODEL_MAX_SIDE) -> bytes:
    return cv2.imencode(".png", fit(image, max_side))[1].tobytes()


def contact_sheet(sources: list[Source], per_sheet: int = 9) -> list[bytes]:
    """3×3 tiles per sheet, each captioned with the source id and origin."""
    tile, caption = 500, 36
    sheets = []
    for start in range(0, len(sources), per_sheet):
        group = sources[start:start + per_sheet]
        columns = min(3, len(group))
        rows = (len(group) + columns - 1) // columns
        sheet = np.full((rows * (tile + caption), columns * tile, 3), 255, np.uint8)
        for index, source in enumerate(group):
            row, column = divmod(index, columns)
            image = fit(source.image, tile - 10)
            y = row * (tile + caption) + caption
            x = column * tile + 5
            sheet[y:y + image.shape[0], x:x + image.shape[1]] = image
            cv2.putText(sheet, f"{source.id}  {source.origin}"[:40], (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        (0, 0, 200), 2)
        sheets.append(png(sheet))
    return sheets


def grid_view(image: np.ndarray) -> bytes:
    """The image at model size with a 10×10 grid labelled 0.0…1.0, for normalised boxes and points."""
    view = fit(image, MODEL_MAX_SIDE).copy()
    height, width = view.shape[:2]
    for step in range(11):
        x, y = round(step * (width - 1) / 10), round(step * (height - 1) / 10)
        cv2.line(view, (x, 0), (x, height - 1), (255, 0, 255), 1)
        cv2.line(view, (0, y), (width - 1, y), (255, 0, 255), 1)
        label = f"{step / 10:.1f}"
        cv2.putText(view, label, (min(x + 2, width - 30), 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 0, 255), 1)
        cv2.putText(view, label, (2, max(y - 3, 28)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 0, 255), 1)
    return cv2.imencode(".png", view)[1].tobytes()


GPS_IFD = 0x8825  # EXIF GPSInfo


def photo_gps(data: bytes) -> tuple[float, float] | None:
    """(lat, lon) from a photo's EXIF GPS, None without one (or for a PDF / an image that is not a photo)."""
    try:
        gps = Image.open(io.BytesIO(data)).getexif().get_ifd(GPS_IFD)
        if not gps or 2 not in gps or 4 not in gps:
            return None
        degrees = lambda values: float(values[0]) + float(values[1]) / 60 + float(values[2]) / 3600
        lat, lon = degrees(gps[2]), degrees(gps[4])
        return (-lat if gps.get(1) == "S" else lat, -lon if gps.get(3) == "W" else lon)
    except Exception:  # noqa: BLE001 — not an image Pillow reads, or broken EXIF: no position
        return None


def median_gps(files: list[bytes]) -> tuple[float, float, int] | None:
    """The median position of the photos that carry GPS, and how many did; None if none did."""
    found = [position for position in map(photo_gps, files) if position]
    if not found:
        return None
    middle = lambda values: sorted(values)[len(values) // 2] if len(values) % 2 else sum(sorted(values)[len(values) // 2 - 1:len(values) // 2 + 1]) / 2
    return middle([lat for lat, _ in found]), middle([lon for _, lon in found]), len(found)
