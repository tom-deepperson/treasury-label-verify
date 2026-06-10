"""Ironwood chaos sample: parser stress test with noise and scattered mandatory fields."""

import json
from pathlib import Path

import pytest

from app.compare import compare_all, overall_status
from app.parser import label_brand_from_ocr, label_class_from_ocr, parse_fields_from_text
from app.schemas import ApplicationFields

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "samples" / "labels" / "ironwood_chaos_pass.png"
APPLICATIONS = ROOT / "samples" / "applications.json"


def _application() -> ApplicationFields:
    apps = json.loads(APPLICATIONS.read_text(encoding="utf-8"))
    entry = next(item for item in apps if item["sample_file"] == "ironwood_chaos_pass.png")
    return ApplicationFields(
        brand_name=entry["brand_name"],
        class_type=entry["class_type"],
        alcohol_content=entry["alcohol_content"],
        net_contents=entry["net_contents"],
        government_warning=entry["government_warning"],
    )


# Synthetic OCR shaped like field assembly output on a clean read (unit-level parser test).
IRONWOOD_ASSEMBLED_OCR = "\n".join(
    [
        "IRONWOOD CANYON DISTILLING CO.",
        "Small Batch Straight Rye Whiskey",
        "46% Alc./Vol. (92 Proof)",
        "750 mL",
        (
            "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
            "alcoholic beverages during pregnancy because of the risk of birth defects. "
            "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
            "operate machinery, and may cause health problems."
        ),
    ]
)

# Messy OCR order observed on ironwood_chaos_pass.png (Vision/EasyOCR).
IRONWOOD_MESSY_OCR = "\n".join(
    [
        "Batch RYE - 2028-009- Lot 18C Small Batch",
        "Straight Rye Whiskey",
        "46 % Alc./Vol. . ( 92 Proof ) BW - 4421 - A",
        "750 ml",
        (
            "GOVERNMENT WARNING : ( 1 ) According to the Surgeon General , women should not drink "
            "alcoholic beverages during pregnancy because of the risk of birth defects . "
            "( 2 ) Consumption of alcoholic beverages impairs your ability to drive a car or "
            "operate machinery , and may cause health problems . IRONWOOD CANYON DISTILLING CO ."
        ),
    ]
)

# Brand missing from primary OCR; class prefix duplicated in assembly.
IRONWOOD_MISSING_BRAND_OCR = "\n".join(
    [
        "Small Batch",
        "Small Batch Straight Rye Whiskey",
        "46 % Alc./Vol. . ( 92 Proof ) BW - 4421 - A",
        "750 ml",
        (
            "GOVERNMENT WARNING : ( 1 ) According to the Surgeon General , women should not drink "
            "alcoholic beverages during pregnancy because of the risk of birth defects . "
            "( 2 ) Consumption of alcoholic beverages impairs your ability to drive a car or "
            "operate machinery , and may cause health problems."
        ),
    ]
)


@pytest.mark.skipif(not SAMPLE.exists(), reason="samples not generated")
def test_ironwood_chaos_sample_registered_in_applications():
    apps = json.loads(APPLICATIONS.read_text(encoding="utf-8"))
    entry = next(item for item in apps if item["sample_file"] == "ironwood_chaos_pass.png")
    assert entry["brand_name"] == "IRONWOOD CANYON DISTILLING CO."
    assert entry["class_type"] == "Small Batch Straight Rye Whiskey"


def test_ironwood_assembled_ocr_parser_finds_mandatory_fields():
    parsed = parse_fields_from_text(IRONWOOD_ASSEMBLED_OCR)
    assert "IRONWOOD CANYON" in parsed.brand_name.upper()
    assert "RYE WHISKEY" in parsed.class_type.upper()
    assert "46" in parsed.alcohol_content
    assert "750" in parsed.net_contents
    assert "GOVERNMENT WARNING" in parsed.government_warning.upper()


def test_ironwood_assembled_ocr_compare_passes():
    app = _application()
    parsed = parse_fields_from_text(IRONWOOD_ASSEMBLED_OCR)
    fields = compare_all(app, parsed, ocr_text=IRONWOOD_ASSEMBLED_OCR)
    assert overall_status(fields) == "PASS"


def test_ironwood_missing_brand_ocr_does_not_use_class_prefix_as_brand():
    assert label_brand_from_ocr(IRONWOOD_MISSING_BRAND_OCR) == ""
    assert label_class_from_ocr(IRONWOOD_MISSING_BRAND_OCR) == "Small Batch Straight Rye Whiskey"


def test_ironwood_missing_brand_compare_reviews_not_fails():
    app = _application()
    parsed = parse_fields_from_text(IRONWOOD_MISSING_BRAND_OCR)
    fields = compare_all(app, parsed, ocr_text=IRONWOOD_MISSING_BRAND_OCR)
    brand = next(field for field in fields if field.field_name == "Brand Name")
    assert brand.status == "REVIEW"
    assert overall_status(fields) == "REVIEW"


def test_ironwood_messy_ocr_compare_passes():
    app = _application()
    parsed = parse_fields_from_text(IRONWOOD_MESSY_OCR)
    assert "IRONWOOD CANYON" in label_brand_from_ocr(IRONWOOD_MESSY_OCR).upper()
    assert label_class_from_ocr(IRONWOOD_MESSY_OCR) == "Small Batch Straight Rye Whiskey"
    assert "IRONWOOD CANYON" not in parsed.government_warning.upper()
    fields = compare_all(app, parsed, ocr_text=IRONWOOD_MESSY_OCR)
    assert overall_status(fields) == "PASS"


def test_ironwood_noise_lines_not_treated_as_brand():
    noisy = "\n".join(
        [
            "DEPARTMENT OF THE TREASURY · FORM BLEED",
            "Warehouse 7 · DSP-TX-88421",
            "IRONWOOD CANYON DISTILLING CO.",
            "Small Batch Straight Rye Whiskey",
            "46% Alc./Vol. (92 Proof)",
            "750 mL",
            "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects. (2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems.",
        ]
    )
    brand = label_brand_from_ocr(noisy)
    assert "IRONWOOD CANYON" in brand.upper()
    assert "treasury" not in brand.lower()
    assert "warehouse" not in brand.lower()
    assert label_class_from_ocr(noisy) == "Small Batch Straight Rye Whiskey"
