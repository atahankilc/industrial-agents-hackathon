"""Plan import, stage 0: files → sources (backend/core/plan_import/ingest.py)."""

from io import BytesIO

import numpy as np
from PIL import Image

from backend.core.plan_import.ingest import contact_sheet, grid_view, load_sources
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


def test_iphone_heic_photo_is_read():
    import pillow_heif

    picture = Image.fromarray(draw_plan(*TWO_ROOMS_AND_CORRIDOR)[:, :, ::-1])
    out = BytesIO()
    pillow_heif.from_pillow(picture).save(out, quality=90)
    sources, warnings = load_sources([("IMG_6543.HEIC", out.getvalue()), ("IMG_6543.mov", b"\x00\x00\x00\x14ftypqt  ")])
    assert [source.origin for source in sources] == ["IMG_6543.HEIC"] and sources[0].image.shape[:2] == (240, 280)
    assert len(warnings) == 1 and warnings[0].startswith("IMG_6543.mov:")


def test_a_huge_pdf_page_renders_straight_to_the_working_size():
    page = Image.new("RGB", (2000, 1400), "white")
    out = BytesIO()
    page.save(out, format="PDF", resolution=12)  # a ~4.2 × 3 m sheet (A0 is 1.19 m)
    (source,), warnings = load_sources([("sheet.pdf", out.getvalue())])
    assert max(source.image.shape[:2]) <= 2400 and warnings == []


def test_too_many_pages_are_capped_with_a_warning():
    plan = draw_plan(*TWO_ROOMS_AND_CORRIDOR)
    sources, warnings = load_sources([("long.pdf", pdf_of(*[plan] * 45))])
    assert len(sources) == 40
    assert any(w.startswith("long.pdf:") and "40" in w for w in warnings)


def test_a_scanned_pdf_page_is_not_added_twice():
    scan = np.full((900, 1200, 3), 255, np.uint8)
    sources, _ = load_sources([("scan.pdf", pdf_of(scan, scan))])
    assert [source.origin for source in sources] == ["scan.pdf p1", "scan.pdf p2"]
