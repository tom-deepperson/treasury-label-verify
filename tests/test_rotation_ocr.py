from pathlib import Path

import os

import pytest

from app.ocr_service import extract_text_with_rotation


SAMPLES = Path(__file__).resolve().parents[1] / "samples" / "labels"


@pytest.fixture(autouse=True)
def use_easyocr_backend(monkeypatch):
    """Rotation OCR tests use local EasyOCR unless integration credentials are provided."""
    if os.getenv("OCR_INTEGRATION") != "1":
        monkeypatch.setenv("OCR_BACKEND", "easyocr")
        monkeypatch.setenv("ROTATION_OCR_BACKEND", "easyocr")


@pytest.mark.skipif(not (SAMPLES / "old_tom_pass.png").exists(), reason="samples not generated")
def test_rotation_detection_on_rotated_sample():
    image_bytes = (SAMPLES / "rotated_pass.png").read_bytes()
    result = extract_text_with_rotation(image_bytes)
    assert result.text
    if result.per_sticker:
        assert result.brand_rotation_deg in {90, 270}
        assert result.warning_rotation_deg == 0
    else:
        assert result.detected_rotation_deg in {90, 270}
    assert "OLD TOM" in result.text.upper() or "GOVERNMENT WARNING" in result.text.upper()


@pytest.mark.skipif(not (SAMPLES / "slight_skew_pass.png").exists(), reason="samples not generated")
def test_slight_skew_sample_reads_text():
    image_bytes = (SAMPLES / "slight_skew_pass.png").read_bytes()
    result = extract_text_with_rotation(image_bytes)
    assert result.text
    assert "GOVERNMENT WARNING" in result.text.upper() or "OLD TOM" in result.text.upper()


@pytest.mark.skipif(not (SAMPLES / "old_tom_pass.png").exists(), reason="samples not generated")
def test_upright_sample_prefers_zero_rotation():
    image_bytes = (SAMPLES / "old_tom_pass.png").read_bytes()
    result = extract_text_with_rotation(image_bytes)
    assert result.was_upright is True
    assert result.brand_inverted is False
    assert result.per_sticker is False


@pytest.mark.skipif(not (SAMPLES / "rotated_180_pass.png").exists(), reason="samples not generated")
def test_inverted_brand_sticker_uses_per_sticker_mode():
    image_bytes = (SAMPLES / "rotated_180_pass.png").read_bytes()
    result = extract_text_with_rotation(image_bytes)
    assert result.detected_rotation_deg == 0
    assert result.per_sticker is True
    assert result.brand_rotation_deg == 180
    assert result.warning_rotation_deg == 0
    assert result.was_upright is False
    assert result.brand_inverted is True
    assert "OLD TOM" in result.text.upper()
    assert "GOVERNMENT WARNING" in result.text.upper()
