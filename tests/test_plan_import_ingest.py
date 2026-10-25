"""Plan import, stage 0: files → sources (core/plan_import/ingest.py)."""

from io import BytesIO

import numpy as np
from PIL import Image

from core.plan_import.ingest import contact_sheet, grid_view, load_sources
from tests.plan_fixtures import TWO_ROOMS_AND_CORRIDOR, draw_plan, to_png


def pdf_of(*images: np.ndarray) -> bytes:
    pages = [Image.fromarray(image[:, :, ::-1]) for image in images]
    out = BytesIO()
    pages[0].save(out, format="PDF", save_all=True, append_images=pages[1:], resolution=100)
    return out.getvalue()


def test_pdf_pages_become_sources():
    plan = draw_plan(*TWO_ROOMS_AND_CORRIDOR)
    sources, warnings = load_sources([("plan.pdf", pdf_of(plan, plan))])
    assert [source.origin for source in sources][:2] == ["plan.pdf p1", "plan.pdf p2"]
    assert warnings == []
    assert [source.id for source in sources][:2] == ["s1", "s2"]


def test_big_photo_is_downscaled_and_exif_rotated():
    photo = Image.new("RGB", (4000, 3000), "white")
    exif = photo.getexif()
    exif[0x0112] = 6  # orientation: rotate 90° on display → portrait
    out = BytesIO()
    photo.save(out, format="JPEG", exif=exif)
    (source,), _ = load_sources([("IMG.jpeg", out.getvalue())])
    assert max(source.image.shape[:2]) == 2400
    assert source.image.shape[0] > source.image.shape[1]


def test_bad_files_are_warnings_not_errors():
    good = to_png(draw_plan(*TWO_ROOMS_AND_CORRIDOR))
    sources, warnings = load_sources([("a.heic", b"xx"), ("empty.pdf", b""), ("ok.png", good)])
    assert len(sources) == 1 and sources[0].origin == "ok.png"
    assert any(w.startswith("a.heic:") for w in warnings)
    assert any(w.startswith("empty.pdf:") for w in warnings)


def test_contact_sheet_and_grid_are_small_pngs():
    plan = draw_plan(*TWO_ROOMS_AND_CORRIDOR)
    sources, _ = load_sources([(f"p{i}.png", to_png(plan)) for i in range(11)])
    sheets = contact_sheet(sources)
    assert len(sheets) == 2
    assert all(max(Image.open(BytesIO(sheet)).size) <= 1568 for sheet in sheets)
    assert Image.open(BytesIO(grid_view(np.zeros((3000, 1000, 3), np.uint8)))).size[1] <= 1568
