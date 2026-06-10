import os
from pathlib import Path

import pytest

from app.ocr_service import extract_text_with_rotation


SAMPLES = Path(__file__).resolve().parents[1] / "samples" / "labels"


@pytest.fixture(autouse=True)
def use_easyocr_backend(monkeypatch):
    if os.getenv("OCR_INTEGRATION") != "1":
        monkeypatch.setenv("OCR_BACKEND", "easyocr")
        monkeypatch.setenv("ROTATION_OCR_BACKEND", "easyocr")


@pytest.mark.skipif(not (SAMPLES / "old_tom_pass.png").exists(), reason="samples not generated")
def test_affix_baseline_reads_label():
    image_bytes = (SAMPLES / "old_tom_pass.png").read_bytes()
    result = extract_text_with_rotation(image_bytes)
    assert result.label_region is not None
    assert result.label_region.label_region_used is False
    assert result.text
    assert "OLD TOM" in result.text.upper()


@pytest.mark.skipif(not (SAMPLES / "old_tom_pass.png").exists(), reason="samples not generated")
def test_affix_baseline_reads_mandatory_fields():
    image_bytes = (SAMPLES / "old_tom_pass.png").read_bytes()
    result = extract_text_with_rotation(image_bytes)
    upper = result.text.upper()
    assert "OLD TOM" in upper
    assert "750" in result.text or "ML" in upper
    assert "45" in result.text or "ALC" in upper or "PROOF" in upper


@pytest.mark.skipif(not (SAMPLES / "warehouse_noise_pass.png").exists(), reason="samples not generated")
def test_affix_warehouse_noise_reads_brand():
    image_bytes = (SAMPLES / "warehouse_noise_pass.png").read_bytes()
    result = extract_text_with_rotation(image_bytes)
    assert "OLD TOM" in result.text.upper()
    brand_line = result.text.splitlines()[0].upper() if result.text else ""
    assert "WAREHOUSE" not in brand_line
