from app.llm_service import (
    GEMINI_MODEL,
    available_models,
    default_model,
    extract_fields,
    use_llm,
    validate_mapped_fields,
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

    fields, mode = extract_fields(SAMPLE_OCR, GEMINI_MODEL, application=APP)

    assert mode == "ocr_parser"
    assert fields.brand_name == "OLD TOM DISTILLERY"
    assert fields.net_contents == "750 mL"


def test_available_models_prefers_gemini_when_configured(monkeypatch):
    monkeypatch.setenv("USE_LLM", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert available_models()[0] == GEMINI_MODEL
    assert default_model() == GEMINI_MODEL


def test_validate_mapped_fields_accepts_verbatim_substrings():
    mapped = ApplicationFields(
        brand_name="OLD TOM DISTILLERY",
        class_type="Kentucky Straight Bourbon Whiskey",
        alcohol_content="45% Alc./Vol. (90 Proof)",
        net_contents="750 mL",
        government_warning=SAMPLE_OCR.split("\n", 4)[4],
    )
    assert validate_mapped_fields(mapped, SAMPLE_OCR) is True


def test_validate_mapped_fields_rejects_hallucinated_text():
    mapped = ApplicationFields(
        brand_name="WRONG BRAND",
        class_type="",
        alcohol_content="",
        net_contents="",
        government_warning="",
    )
    assert validate_mapped_fields(mapped, SAMPLE_OCR) is False


def test_extract_fields_uses_llm_map_when_valid(monkeypatch):
    monkeypatch.setenv("USE_LLM", "1")

    def _mock_map(_ocr_text, _model, _application):
        return ApplicationFields(
            brand_name="OLD TOM DISTILLERY",
            class_type="Kentucky Straight Bourbon Whiskey",
            alcohol_content="45% Alc./Vol. (90 Proof)",
            net_contents="750 mL",
            government_warning=SAMPLE_OCR.split("\n", 4)[4],
        )

    monkeypatch.setattr("app.llm_service.map_fields_with_llm", _mock_map)

    fields, mode = extract_fields(SAMPLE_OCR, GEMINI_MODEL, application=APP)

    assert mode == "llm_map"
    assert fields.brand_name == "OLD TOM DISTILLERY"


def test_extract_fields_falls_back_when_map_invalid(monkeypatch):
    monkeypatch.setenv("USE_LLM", "1")

    def _bad_map(_ocr_text, _model, _application):
        raise ValueError("LLM map failed verbatim validation")

    monkeypatch.setattr("app.llm_service.map_fields_with_llm", _bad_map)

    fields, mode = extract_fields(SAMPLE_OCR, GEMINI_MODEL, application=APP)

    assert mode == "regex_fallback"
    assert fields.brand_name == "OLD TOM DISTILLERY"


def test_extract_fields_falls_back_when_llm_call_fails(monkeypatch):
    monkeypatch.setenv("USE_LLM", "1")

    def _boom(_ocr_text, _model, _application):
        raise RuntimeError("no api key")

    monkeypatch.setattr("app.llm_service.map_fields_with_llm", _boom)

    fields, mode = extract_fields(SAMPLE_OCR, GEMINI_MODEL, application=APP)

    assert mode == "regex_fallback"
    assert fields.brand_name == "OLD TOM DISTILLERY"
