"""Tests for LLM rescue-on-fail (parser-first pipeline)."""

import json

from app.compare import compare_all, failed_field_keys, rescue_field_keys
from app.llm_service import (
    DEFAULT_GEMINI_MODEL,
    FIELD_KEY_LABELS,
    _rescue_prompt,
    extract_fields,
    fields_from_line_bins,
    rescue_failed_fields,
)
from app.parser import parse_fields_from_text
from tests.test_ironwood_chaos import IRONWOOD_MESSY_OCR, _application as ironwood_application
from tests.test_llm_service import APP, SAMPLE_OCR


def test_extract_fields_is_parser_only(monkeypatch):
    monkeypatch.setenv("USE_LLM", "1")
    fields, mode, error = extract_fields(SAMPLE_OCR, DEFAULT_GEMINI_MODEL, application=APP)
    assert mode == "ocr_parser"
    assert error is None
    assert fields.brand_name == "OLD TOM DISTILLERY"


def test_failed_field_keys_maps_display_names():
    fields = compare_all(
        APP,
        parse_fields_from_text(SAMPLE_OCR),
        ocr_text=SAMPLE_OCR.replace("OLD TOM", "WRONG TOM"),
    )
    assert "brand_name" in failed_field_keys(fields)


def test_rescue_field_keys_includes_review():
    from tests.test_ironwood_chaos import IRONWOOD_MISSING_BRAND_OCR

    app = ironwood_application()
    fields = compare_all(app, parse_fields_from_text(IRONWOOD_MISSING_BRAND_OCR), ocr_text=IRONWOOD_MISSING_BRAND_OCR)
    brand = next(field for field in fields if field.field_name == "Brand Name")
    assert brand.status == "REVIEW"
    assert "brand_name" in rescue_field_keys(fields)
    assert "brand_name" not in failed_field_keys(fields)


def test_rescue_prompt_lists_only_failed_fields():
    prompt = _rescue_prompt(
        ["IRONWOOD CANYON DISTILLING CO.", "Small Batch Straight Rye Whiskey"],
        ironwood_application(),
        ["brand_name"],
    )
    assert "brand_name" in prompt
    assert "class_type" not in prompt.split("Return JSON")[0]
    assert "IRONWOOD CANYON DISTILLING CO." in prompt


def test_rescue_ironwood_messy_ocr_finds_brand(monkeypatch):
    raw_lines = [line for line in IRONWOOD_MESSY_OCR.splitlines() if line.strip()]

    def _fake_llm(_prompt, _model):
        return json.dumps({"brand_name": [5], "ignore": [1, 2, 3, 4]})

    monkeypatch.setattr("app.llm_service._call_llm", _fake_llm)
    rescued, error = rescue_failed_fields(
        raw_lines,
        ironwood_application(),
        ["brand_name"],
        DEFAULT_GEMINI_MODEL,
    )

    assert error is None
    assert rescued is not None
    assert "IRONWOOD CANYON" in rescued.brand_name.upper()


def test_rescue_recompare_passes_when_brand_rescued():
    raw_lines = [line for line in IRONWOOD_MESSY_OCR.splitlines() if line.strip()]
    app = ironwood_application()
    extracted = parse_fields_from_text(IRONWOOD_MESSY_OCR)

    bins = {"brand_name": [5], "ignore": [1, 2, 3, 4]}
    rescued = fields_from_line_bins(bins, "\n".join(raw_lines), application=app)
    after = compare_all(app, extracted, ocr_text=IRONWOOD_MESSY_OCR, label_fields=rescued)
    brand = next(field for field in after if field.field_name == "Brand Name")
    assert brand.status == "PASS"
    assert "IRONWOOD CANYON" in brand.extracted_value.upper()


def test_rescue_rejects_invalid_brand_line(monkeypatch):
    raw_lines = SAMPLE_OCR.splitlines()

    def _fake_llm(_prompt, _model):
        return json.dumps({"brand_name": [4]})

    monkeypatch.setattr("app.llm_service._call_llm", _fake_llm)
    rescued, error = rescue_failed_fields(raw_lines, APP, ["brand_name"], DEFAULT_GEMINI_MODEL)

    assert rescued is None
    assert error is not None


def test_rescue_skipped_when_no_failed_fields():
    rescued, error = rescue_failed_fields(SAMPLE_OCR.splitlines(), APP, [], DEFAULT_GEMINI_MODEL)
    assert rescued is None
    assert error is not None


def test_rescue_recompare_passes_for_uppercase_ml():
    from app.compare import apply_rescue_notes, overall_status
    from app.schemas import ApplicationFields

    app = ApplicationFields(
        brand_name="OLD TOM DISTILLERY",
        class_type="Kentucky Straight Bourbon Whiskey",
        alcohol_content="45% Alc./Vol. (90 Proof)",
        net_contents="750 mL",
        government_warning=APP.government_warning,
    )
    ocr = (
        "OLD TOM DISTILLERY 750 ML\nKentucky Straight Bourbon Whiskey\n"
        "45 % Alc./Vol. . ( 90 Proof )\nGOVERNMENT WARNING: (1) test"
    )
    extracted = parse_fields_from_text(ocr)
    rescued = ApplicationFields(
        brand_name="",
        class_type="",
        alcohol_content="",
        net_contents="750 ML",
        government_warning="",
    )
    fields = compare_all(app, extracted, ocr_text=ocr, label_fields=rescued)
    fields = apply_rescue_notes(fields, ["net_contents"])
    net = next(field for field in fields if field.field_name == "Net Contents")
    assert net.status == "PASS"
    assert "LLM located" in net.notes


def test_rescue_prompt_includes_field_labels():
    prompt = _rescue_prompt(["line"], APP, ["brand_name", "class_type"])
    assert FIELD_KEY_LABELS["brand_name"] in prompt
    assert FIELD_KEY_LABELS["class_type"] in prompt
