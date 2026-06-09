from app.parser import extract_abv_value, normalize_brand, parse_fields_from_text
from app.compare import compare_brand, compare_government_warning, overall_status, compare_all
from app.schemas import ApplicationFields


def test_brand_normalization_pass():
    app = ApplicationFields(
        brand_name="Stone's Throw",
        class_type="",
        alcohol_content="",
        net_contents="",
        government_warning="",
    )
    result = compare_brand(app.brand_name, "STONE'S THROW")
    assert result.status == "PASS"


def test_abv_extract():
    assert extract_abv_value("45% Alc./Vol. (90 Proof)") == 45.0


def test_warning_exact_fail_on_title_case():
    gov = (
        "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
        "alcoholic beverages during pregnancy because of the risk of birth defects. "
        "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
        "operate machinery, and may cause health problems."
    )
    bad = gov.replace("GOVERNMENT WARNING:", "Government Warning:")
    result = compare_government_warning(gov, bad)
    assert result.status == "FAIL"


def test_parser_finds_warning():
    text = """OLD TOM DISTILLERY
Kentucky Straight Bourbon Whiskey
45% Alc./Vol. (90 Proof)
750 mL
GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects. (2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems."""
    parsed = parse_fields_from_text(text)
    assert "GOVERNMENT WARNING" in parsed.government_warning.upper()


def test_overall_status_fail_if_any_fail():
    app = ApplicationFields(
        brand_name="A",
        class_type="B",
        alcohol_content="45%",
        net_contents="750 mL",
        government_warning="GOVERNMENT WARNING: x",
    )
    extracted = ApplicationFields(
        brand_name="A",
        class_type="B",
        alcohol_content="40%",
        net_contents="750 mL",
        government_warning="GOVERNMENT WARNING: x",
    )
    fields = compare_all(app, extracted)
    assert overall_status(fields) == "FAIL"
