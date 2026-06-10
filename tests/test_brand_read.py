from app.parser import (
    is_garbled_brand_read,
    label_brand_from_ocr,
    label_class_from_ocr,
    word_tokens,
)
from app.compare import compare_brand, compare_text_field


def test_label_brand_strips_clarify_annotation():
    text = "OLD TOM DISTILLERY  [script OCR read: 0LD TOM]"
    assert label_brand_from_ocr(text) == "OLD TOM DISTILLERY"


def test_tum_typo_is_not_garbled():
    assert is_garbled_brand_read("OLD TUM DISTILLERY") is False


def test_script_garble_is_garbled():
    assert is_garbled_brand_read("0LD 70mDJS7LLERI") is True


def test_serif_split_brand_merges_lines():
    ocr = "TOM DISTILLERY\nOLD TOM\nStraight Bourbon Whiskey\nKentucky"
    assert label_brand_from_ocr(ocr) == "TOM DISTILLERY OLD TOM"
    assert word_tokens("OLD TOM DISTILLERY") == word_tokens(label_brand_from_ocr(ocr))


def test_serif_split_class_reorders_kentucky():
    ocr = "OLD TOM DISTILLERY\nStraight Bourbon Whiskey\nKentucky\n45% Alc./Vol. (90 Proof)"
    assert label_class_from_ocr(ocr) == "Kentucky Straight Bourbon Whiskey"


def test_serif_split_brand_compare_passes():
    ocr = "TOM DISTILLERY\nOLD TOM\nKentucky Straight Bourbon Whiskey"
    result = compare_brand("OLD TOM DISTILLERY", "OLD TOM DISTILLERY", ocr_text=ocr)
    assert result.status == "PASS"


def test_brand_extracts_when_class_is_above_brand():
    ocr = (
        "Kentucky Straight Bourbon Whiskey\n"
        "Distilled in Kentucky · Est. 2018\n"
        "OLD TOM DISTILLERY\n"
        "45% Alc./Vol. (90 Proof)\n"
        "750 mL"
    )
    assert label_brand_from_ocr(ocr) == "OLD TOM DISTILLERY"


def test_marketing_between_brand_and_class_is_excluded():
    ocr = (
        "OLD TOM DISTILLERY\n"
        "Batch No. OT-2024-117\n"
        "Kentucky Straight Bourbon Whiskey"
    )
    assert label_brand_from_ocr(ocr) == "OLD TOM DISTILLERY"


def test_warning_fragment_is_not_treated_as_brand():
    ocr = (
        "OLD TOM DISTILLERY\n"
        "Kentucky Straight Bourbon Whiskey\n"
        "45% Alc./Vol. (90 Proof)\n"
        "700 mL\n"
        "not drink alcoholic beverages during pregnancy because of the risk of"
    )
    assert label_brand_from_ocr(ocr) == "OLD TOM DISTILLERY"

    ocr = "TOM DISTILLERY\nOLD TOM\nStraight Bourbon Whiskey\nKentucky"
    result = compare_text_field(
        "Class/Type",
        "Kentucky Straight Bourbon Whiskey",
        label_class_from_ocr(ocr),
    )
    assert result.status == "PASS"
