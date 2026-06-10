from app.parser import label_brand_from_ocr, label_class_from_ocr


def test_warehouse_lines_not_brand():
    ocr = "\n".join(
        [
            "OLD TOM DISTILLERY",
            "Kentucky Straight Bourbon Whiskey",
            "Warehouse H",
            "DSP-IN-12345",
            "45% Alc./Vol. (90 Proof)",
            "750 mL",
        ]
    )
    assert label_brand_from_ocr(ocr) == "OLD TOM DISTILLERY"
    assert "warehouse" not in label_brand_from_ocr(ocr).lower()


def test_registry_noise_not_class():
    ocr = "\n".join(
        [
            "OLD TOM DISTILLERY",
            "Kentucky Straight Bourbon Whiskey",
            "Bottled at 456 Bond St, Lawrenceburg, IN 47025",
            "Lot OT-2026-042",
            "45% Alc./Vol. (90 Proof)",
            "750 mL",
        ]
    )
    assert label_class_from_ocr(ocr) == "Kentucky Straight Bourbon Whiskey"


def test_form_bleed_filtered_from_brand():
    ocr = "\n".join(
        [
            "DEPARTMENT OF THE TREASURY",
            "OLD TOM DISTILLERY",
            "Kentucky Straight Bourbon Whiskey",
            "SERIAL NUMBER 26-1",
            "45% Alc./Vol. (90 Proof)",
            "750 mL",
        ]
    )
    brand = label_brand_from_ocr(ocr)
    assert brand == "OLD TOM DISTILLERY"
    assert "treasury" not in brand.lower()
    assert "serial" not in brand.lower()
