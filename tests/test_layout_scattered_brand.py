from pathlib import Path

from app.ocr.backends.factory import get_backend
from app.ocr.field_assembly import assemble_label_text
from app.ocr_service import _decode_image, _preprocess_for_ocr, _resize, improve_brand_line
from app.parser import label_brand_from_ocr, parse_net_contents_ml

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "labels" / "layout_scattered_net_fail.png"


def test_layout_scattered_net_fail_reads_brand_and_net():
    image = _resize(_decode_image(SAMPLE.read_bytes()))
    document = get_backend().read(_preprocess_for_ocr(image))
    assembled = assemble_label_text(document)
    upper = assembled.upper()
    assert "OLD TOM" in upper
    assert "700" in assembled
    assert "ML" in upper
    assert "750" not in assembled


def test_layout_scattered_net_fail_brand_is_not_volume():
    image_bytes = SAMPLE.read_bytes()
    image = _resize(_decode_image(image_bytes))
    document = get_backend().read(_preprocess_for_ocr(image))
    assembled = assemble_label_text(document)
    improved = improve_brand_line(assembled, image, "OLD TOM DISTILLERY")
    brand = label_brand_from_ocr(improved)
    # Corner net contents must not become the sole brand read (scattered layout).
    net_in_brand = parse_net_contents_ml(brand)
    assert net_in_brand is None or "OLD TOM" in brand.upper()
    assert "750" not in brand


def test_layout_scattered_net_fail_has_warning_on_neck_sticker():
    image = _resize(_decode_image(SAMPLE.read_bytes()))
    document = get_backend().read(_preprocess_for_ocr(image))
    assembled = assemble_label_text(document)
    upper = assembled.upper()
    assert any(token in upper for token in ("GOVERNMENT", "SURGEON", "WARNING", "WOMEN", "PREGNANCY"))
