from app.ocr_service import _parse_detection


def test_parse_detection_with_confidence():
    box, text, conf = _parse_detection([[[0, 0]], "OLD TOM", 0.91])
    assert text == "OLD TOM"
    assert conf == 0.91


def test_parse_detection_paragraph_mode():
    box, text, conf = _parse_detection([[[0, 0]], "GOVERNMENT WARNING: test"])
    assert text == "GOVERNMENT WARNING: test"
    assert conf == 0.85
