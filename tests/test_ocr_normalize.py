from app.ocr_service import normalize_ocr_text


def test_normalize_ocr_reflows_warning_and_fixes_abv():
    raw = """OLD TOM DISTILLERY
Kentucky Straight Bourbon Whiskey
45% Alc.NVol: (90 Proof)
750 mL
GOVERNMENT WARNING: (1) According to the Surgeon General, women should
not drink alcoholic beverages during pregnancy because of the risk of
birth defects. (2) Consumption of alcoholic beverages impairs your
ability to drive
car or operate machinery, and
cause health
may
problems_"""
    cleaned = normalize_ocr_text(raw)
    assert "Alc./Vol." in cleaned
    assert "drive a car" in cleaned.lower()
    assert "may cause health problems." in cleaned.lower()
    assert "problems_" not in cleaned
    # Warning should be one line after header block
    warning_lines = [line for line in cleaned.splitlines() if "GOVERNMENT WARNING" in line.upper()]
    assert len(warning_lines) == 1
