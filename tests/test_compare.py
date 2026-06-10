from app.parser import extract_abv_value, normalize_brand, parse_fields_from_text, parse_net_contents_ml
from app.compare import (
    compare_abv,
    compare_all,
    compare_brand,
    compare_government_warning,
    compare_net_contents,
    compare_text_field,
    overall_status,
)
from app.schemas import ApplicationFields

SAMPLE_OCR_TAIL = (
    "Kentucky Straight Bourbon Whiskey\n"
    "45% Alc./Vol. (90 Proof)\n"
    "750 mL\n"
    "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
    "alcoholic beverages during pregnancy because of the risk of birth defects. "
    "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
    "operate machinery, and may cause health problems."
)


def test_script_brand_ocr_tolerance():
    app = "OLD TOM DISTILLERY"
    garbled = "0LD 70mDJS7LLERI"
    result = compare_brand(app, garbled, ocr_text=f"{garbled}\nKentucky Straight Bourbon Whiskey")
    assert result.status == "PASS"
    assert result.extracted_value == app
    assert "decorative" in result.notes.lower() or result.notes == ""


def test_brand_typo_on_label_fails():
    app = "OLD TOM DISTILLERY"
    label = "OLD TUM DISTILLERY"
    result = compare_brand(app, app, ocr_text=f"{label}\nKentucky Straight Bourbon Whiskey")
    assert result.status == "FAIL"
    assert result.extracted_value == label
    assert "OLD TUM" in result.notes


def test_class_type_typo_fails():
    app = "Kentucky Straight Bourbon Whiskey"
    label = "Kentucky Staight Bourbon Whiskey"
    result = compare_text_field("Class/Type", app, label)
    assert result.status == "FAIL"
    assert "Staight" in result.notes or "Straight" in result.notes


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


def test_abv_uses_ocr_not_llm_correction():
    ocr = f"OLD TOM DISTILLERY\nKentucky Straight Bourbon Whiskey\n40% Alc./Vol. (80 Proof)\n750 mL"
    result = compare_abv(
        "45% Alc./Vol. (90 Proof)",
        "45% Alc./Vol. (90 Proof)",
        ocr_text=ocr,
    )
    assert result.status == "FAIL"
    assert "40" in result.extracted_value


def test_net_contents_uses_ocr_not_llm_correction():
    ocr = f"OLD TOM DISTILLERY\nKentucky Straight Bourbon Whiskey\n45% Alc./Vol. (90 Proof)\n700 mL"
    result = compare_net_contents("750 mL", "750 mL", ocr_text=ocr)
    assert result.status == "FAIL"
    assert parse_net_contents_ml(result.extracted_value) == 700.0


def test_parse_net_contents_ml_accepts_uppercase_ml():
    assert parse_net_contents_ml("750 ML") == 750.0
    assert parse_net_contents_ml("OLD TOM DISTILLERY 750 ML") == 750.0


def test_compare_net_contents_passes_for_rescued_uppercase_ml():
    result = compare_net_contents("750 mL", "750 mL", label_read="750 ML")
    assert result.status == "PASS"


def test_apply_rescue_notes_on_pass():
    from app.compare import RESCUE_PASS_NOTE, apply_rescue_notes
    from app.schemas import FieldComparison

    fields = [
        FieldComparison(
            field_name="Net Contents",
            application_value="750 mL",
            extracted_value="750 ML",
            status="PASS",
            notes="",
        )
    ]
    updated = apply_rescue_notes(fields, ["net_contents"])
    assert RESCUE_PASS_NOTE in updated[0].notes


def test_parser_finds_net_on_handwritten_brand_line():
    ocr = "OLD TOM DISTILLERY 750 ML\nKentucky Straight Bourbon Whiskey\n45 % Alc./Vol. . ( 90 Proof )"
    parsed = parse_fields_from_text(ocr)
    assert parsed.net_contents == "750 ML"
    assert parse_net_contents_ml(parsed.net_contents) == 750.0


def test_bad_warning_title_case_from_ocr_fails():
    gov = (
        "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
        "alcoholic beverages during pregnancy because of the risk of birth defects. "
        "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
        "operate machinery, and may cause health problems."
    )
    ocr = (
        "OLD TOM DISTILLERY\nKentucky Straight Bourbon Whiskey\n"
        "45 % Alc./Vol. . ( 90 Proof )\n750 mL\n"
        "Government Warning: ( 1 ) According to the Surgeon General , women should not drink "
        "alcoholic beverages during pregnancy because of the risk of birth defects . "
        "( 2 ) Consumption of alcoholic beverages impairs your ability to drive a car or "
        "operate machinery , and may cause health problems"
    )
    app = ApplicationFields(
        brand_name="OLD TOM DISTILLERY",
        class_type="Kentucky Straight Bourbon Whiskey",
        alcohol_content="45% Alc./Vol. (90 Proof)",
        net_contents="750 mL",
        government_warning=gov,
    )
    fields = compare_all(app, app, ocr_text=ocr)
    by_name = {field.field_name: field for field in fields}
    assert by_name["Government Warning"].status == "FAIL"
    assert "capital" in by_name["Government Warning"].notes.lower()
    assert overall_status(fields) == "FAIL"


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


def test_warning_ocr_spacing_passes():
    gov = (
        "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
        "alcoholic beverages during pregnancy because of the risk of birth defects. "
        "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
        "operate machinery, and may cause health problems."
    )
    spaced = (
        "GOVERNMENT WARNING : ( 1 ) According to the Surgeon General , women should not drink "
        "alcoholic beverages during pregnancy because of the risk of birth defects . "
        "( 2 ) Consumption of alcoholic beverages impairs your ability to drive a car or "
        "operate machinery , and may cause health problems"
    )
    result = compare_government_warning(gov, spaced)
    assert result.status == "PASS"


def test_warning_missing_part_two_fails():
    gov = (
        "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
        "alcoholic beverages during pregnancy because of the risk of birth defects. "
        "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
        "operate machinery, and may cause health problems."
    )
    partial = gov.split("(2)")[0].strip()
    result = compare_government_warning(gov, partial)
    assert result.status == "FAIL"


def test_parser_finds_warning():
    text = f"OLD TOM DISTILLERY\n{SAMPLE_OCR_TAIL}"
    parsed = parse_fields_from_text(text)
    assert "GOVERNMENT WARNING" in parsed.government_warning.upper()


def test_warning_near_match_is_review_not_pass():
    gov = (
        "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
        "alcoholic beverages during pregnancy because of the risk of birth defects. "
        "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
        "operate machinery, and may cause health problems."
    )
    noisy = (
        "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
        "alcoholic beverages during pregnancy because of the risk of birth defects. "
        "(2) Consumption of alcoholic beverages impairs your ability to drive car or "
        "operate machinery, and may cause health problems."
    )
    result = compare_government_warning(gov, noisy)
    assert result.status == "REVIEW"


def test_net_contents_fail_note_is_plain_language():
    result = compare_net_contents("750 mL", "700 mL")
    assert result.status == "FAIL"
    assert "750 mL" in result.notes
    assert "700 mL" in result.notes


def test_compare_all_uses_label_fields_when_mapped():
    gov = (
        "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
        "alcoholic beverages during pregnancy because of the risk of birth defects. "
        "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
        "operate machinery, and may cause health problems."
    )
    mapped = ApplicationFields(
        brand_name="OLD TUM DISTILLERY",
        class_type="Kentucky Straight Bourbon Whiskey",
        alcohol_content="45% Alc./Vol. (90 Proof)",
        net_contents="750 mL",
        government_warning=gov,
    )
    app = ApplicationFields(
        brand_name="OLD TOM DISTILLERY",
        class_type="Kentucky Straight Bourbon Whiskey",
        alcohol_content="45% Alc./Vol. (90 Proof)",
        net_contents="750 mL",
        government_warning=gov,
    )
    fields = compare_all(app, app, ocr_text="ignored", label_fields=mapped)
    by_name = {field.field_name: field for field in fields}
    assert by_name["Brand Name"].status == "FAIL"
    assert by_name["Brand Name"].extracted_value == "OLD TUM DISTILLERY"


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


def test_serif_split_ocr_brand_and_class_pass():
    """Serif layout splits brand/class across lines; compare uses token-set equality."""
    gov = (
        "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
        "alcoholic beverages during pregnancy because of the risk of birth defects. "
        "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
        "operate machinery, and may cause health problems."
    )
    ocr = (
        "TOM DISTILLERY\n"
        "OLD TOM\n"
        "Straight Bourbon Whiskey\n"
        "Kentucky\n"
        "45% AlcNVol: (90 Proof)\n"
        "750 mL\n"
        f"{gov}"
    )
    app = ApplicationFields(
        brand_name="OLD TOM DISTILLERY",
        class_type="Kentucky Straight Bourbon Whiskey",
        alcohol_content="45% Alc./Vol. (90 Proof)",
        net_contents="750 mL",
        government_warning=gov,
    )
    fields = compare_all(app, app, ocr_text=ocr)
    by_name = {field.field_name: field for field in fields}
    assert by_name["Brand Name"].status == "PASS"
    assert by_name["Class/Type"].status == "PASS"
    assert by_name["Alcohol Content"].status == "PASS"
    assert by_name["Net Contents"].status == "PASS"
    assert overall_status(fields) == "PASS"
