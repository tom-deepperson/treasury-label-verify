from app.llm_service import (
    DEFAULT_GEMINI_MODEL,
    _complete_binned_fields,
    available_models,
    default_model,
    extract_fields,
    fields_from_line_bins,
    gemini_model_name,
    use_llm,
    validate_binned_fields,
)
from app.schemas import ApplicationFields

SAMPLE_OCR = (
    "OLD TOM DISTILLERY\n"
    "Kentucky Straight Bourbon Whiskey\n"
    "45% Alc./Vol. (90 Proof)\n"
    "750 mL\n"
    "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
    "alcoholic beverages during pregnancy because of the risk of birth defects. "
    "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
    "operate machinery, and may cause health problems."
)

SPACED_OCR = (
    "OLD TOM DISTILLERY\n"
    "Kentucky Straight Bourbon Whiskey\n"
    "45 % Alc./Vol. . ( 90 Proof )\n"
    "750 mL\n"
    "GOVERNMENT WARNING : ( 1 ) According to the Surgeon General , women should not drink "
    "alcoholic beverages during pregnancy because of the risk of birth defects . "
    "( 2 ) Consumption of alcoholic beverages impairs your ability to drive a car or "
    "operate machinery , and may cause health problems ."
)

APP = ApplicationFields(
    brand_name="OLD TOM DISTILLERY",
    class_type="Kentucky Straight Bourbon Whiskey",
    alcohol_content="45% Alc./Vol. (90 Proof)",
    net_contents="750 mL",
    government_warning=(
        "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
        "alcoholic beverages during pregnancy because of the risk of birth defects. "
        "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
        "operate machinery, and may cause health problems."
    ),
)


def test_use_llm_defaults_on(monkeypatch):
    monkeypatch.delenv("USE_LLM", raising=False)
    assert use_llm() is True


def test_use_llm_disabled(monkeypatch):
    monkeypatch.setenv("USE_LLM", "0")
    assert use_llm() is False


def test_extract_fields_uses_ocr_parser_when_llm_disabled(monkeypatch):
    monkeypatch.setenv("USE_LLM", "0")

    fields, mode, error = extract_fields(SAMPLE_OCR, DEFAULT_GEMINI_MODEL, application=APP)

    assert mode == "ocr_parser"
    assert error is None
    assert fields.brand_name == "OLD TOM DISTILLERY"
    assert fields.net_contents == "750 mL"


def test_available_models_prefers_gemini_when_configured(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("GEMINI_API_KEY=test-key\n", encoding="utf-8")
    monkeypatch.setenv("USE_LLM", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("app.llm_service._dotenv_path", lambda: env_file)
    assert available_models()[0] == DEFAULT_GEMINI_MODEL
    assert default_model() == DEFAULT_GEMINI_MODEL


def test_gemini_model_name_uses_dotenv_override(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("GEMINI_MODEL=gemini-2.0-flash\n", encoding="utf-8")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-pro")
    monkeypatch.setattr("app.llm_service._dotenv_path", lambda: env_file)
    assert gemini_model_name() == "gemini-2.0-flash"


def test_gemini_model_name_defaults_when_dotenv_omits_key(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("GEMINI_API_KEY=test-key\n", encoding="utf-8")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-pro")
    monkeypatch.setattr("app.llm_service._dotenv_path", lambda: env_file)
    assert gemini_model_name() == DEFAULT_GEMINI_MODEL


def test_fields_from_line_bins_preserves_ocr_spacing():
    bins = {
        "brand_name": [1],
        "class_type": [2],
        "alcohol_content": [3],
        "net_contents": [4],
        "government_warning": [5],
    }
    fields = fields_from_line_bins(bins, SPACED_OCR, application=APP)
    assert fields.brand_name == "OLD TOM DISTILLERY"
    assert fields.alcohol_content == "45 % Alc./Vol. . ( 90 Proof )"
    assert "GOVERNMENT WARNING :" in fields.government_warning
    assert validate_binned_fields(fields, SPACED_OCR) is True


def test_fields_from_line_bins_accepts_text_labels_from_llm():
    """Gemini often returns OCR text in arrays instead of line numbers."""
    warning_line = SPACED_OCR.splitlines()[-1]
    bins = {
        "brand_name": ["OLD TOM DISTILLERY"],
        "class_type": ["Kentucky Straight Bourbon Whiskey"],
        "alcohol_content": ["45 % Alc./Vol. . ( 90 Proof )"],
        "net_contents": ["750 mL"],
        "government_warning": [warning_line],
    }
    fields = fields_from_line_bins(bins, SPACED_OCR, application=APP)
    assert fields.brand_name == "OLD TOM DISTILLERY"
    assert fields.alcohol_content == "45 % Alc./Vol. . ( 90 Proof )"
    assert validate_binned_fields(fields, SPACED_OCR) is True


def test_validate_binned_fields_rejects_volume_as_brand():
    bins = {
        "brand_name": [4],
        "class_type": [],
        "alcohol_content": [],
        "net_contents": [],
        "government_warning": [],
    }
    fields = fields_from_line_bins(bins, SAMPLE_OCR, application=APP)
    assert validate_binned_fields(fields, SAMPLE_OCR) is False


def test_extract_fields_uses_ocr_parser_when_llm_enabled(monkeypatch):
    monkeypatch.setenv("USE_LLM", "1")

    fields, mode, error = extract_fields(SPACED_OCR, DEFAULT_GEMINI_MODEL, application=APP)

    assert mode == "ocr_parser"
    assert error is None
    assert fields.brand_name == "OLD TOM DISTILLERY"
    assert fields.alcohol_content == "45 % Alc./Vol. . ( 90 Proof )"



NOISY_OCR = (
    "OLD TOM DISTILLERY\n"
    "Kentucky Straight Bourbon Whiskey\n"
    "Warehouse H\n"
    "DSP-IN-12345\n"
    "45% Alc./Vol. (90 Proof)\n"
    "750 mL\n"
    "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
    "alcoholic beverages during pregnancy because of the risk of birth defects. "
    "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
    "operate machinery, and may cause health problems."
)


def test_fields_from_line_bins_skips_marketing_lines_even_when_assigned():
    bins = {
        "brand_name": [1, 3],
        "class_type": [2],
        "alcohol_content": [5],
        "net_contents": [6],
        "government_warning": [7],
        "ignore": [4],
    }
    fields = fields_from_line_bins(bins, NOISY_OCR, application=APP)
    assert fields.brand_name == "OLD TOM DISTILLERY"
    assert "warehouse" not in fields.brand_name.lower()
    assert fields.class_type == "Kentucky Straight Bourbon Whiskey"
    assert validate_binned_fields(fields, NOISY_OCR) is True


def test_fields_from_line_bins_honors_explicit_ignore_list():
    bins = {
        "brand_name": [1],
        "class_type": [2, 3],
        "alcohol_content": [5],
        "net_contents": [6],
        "government_warning": [7],
        "ignore": [3, 4],
    }
    fields = fields_from_line_bins(bins, NOISY_OCR, application=APP)
    assert fields.class_type == "Kentucky Straight Bourbon Whiskey"
    assert "warehouse" not in fields.class_type.lower()


def test_fields_from_line_bins_unassigned_garbage_lines_are_fine():
    bins = {
        "brand_name": [1],
        "class_type": [2],
        "alcohol_content": [5],
        "net_contents": [6],
        "government_warning": [7],
        "ignore": [3, 4],
    }
    fields = fields_from_line_bins(bins, NOISY_OCR, application=APP)
    assert validate_binned_fields(fields, NOISY_OCR) is True


def test_complete_binned_fields_fills_missing_reads_from_parser():
    bins = {
        "brand_name": [1],
        "class_type": [2],
        "alcohol_content": [3],
        "net_contents": [],
        "government_warning": [5],
        "ignore": [4],
    }
    partial = fields_from_line_bins(bins, SPACED_OCR, application=APP)
    assert partial.net_contents == ""
    completed = _complete_binned_fields(partial, SPACED_OCR)
    assert completed.net_contents == "750 mL"
    assert validate_binned_fields(completed, SPACED_OCR) is True


def test_map_fields_with_llm_backfills_missing_from_parser(monkeypatch):
    def _fake_gemini(_prompt, _model):
        return (
            '{"brand_name":[1],"class_type":[2],"alcohol_content":[3],'
            '"net_contents":[],"government_warning":[5],"ignore":[]}'
        )

    monkeypatch.setattr("app.llm_service._call_gemini", _fake_gemini)
    from app.llm_service import map_fields_with_llm

    fields = map_fields_with_llm(SPACED_OCR, DEFAULT_GEMINI_MODEL, APP)
    assert fields.net_contents == "750 mL"
    assert fields.brand_name == "OLD TOM DISTILLERY"
