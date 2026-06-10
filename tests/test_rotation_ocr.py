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
    assert result.detected_rotation_deg in {0, 90, 180, 270}


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
