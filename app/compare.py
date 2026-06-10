from __future__ import annotations

import re

from app.parser import (
    extract_abv_value,
    normalize_brand,
    normalize_whitespace,
)
from app.schemas import ApplicationFields, FieldComparison, FieldStatus, RotationInfo, VerificationResult


def _token_overlap(a: str, b: str) -> float:
    ta = set(re.findall(r"[a-z0-9']+", a.lower()))
    tb = set(re.findall(r"[a-z0-9']+", b.lower()))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def compare_brand(app: str, ext: str) -> FieldComparison:
    app_n = normalize_brand(app)
    ext_n = normalize_brand(ext)
    if not ext_n:
        return FieldComparison(
            field_name="Brand Name",
            application_value=app,
            extracted_value=ext,
            status="REVIEW",
            notes="Brand not extracted from label",
        )
    status: FieldStatus = "PASS" if app_n == ext_n else "FAIL"
    notes = "" if status == "PASS" else "Normalized brand strings differ"
    return FieldComparison(
        field_name="Brand Name",
        application_value=app,
        extracted_value=ext,
        status=status,
        notes=notes,
    )


def compare_abv(app: str, ext: str) -> FieldComparison:
    app_v = extract_abv_value(app)
    ext_v = extract_abv_value(ext)
    if app_v is None or ext_v is None:
        return FieldComparison(
            field_name="Alcohol Content",
            application_value=app,
            extracted_value=ext,
            status="REVIEW",
            notes="Could not parse ABV from one or both values",
        )
    status: FieldStatus = "PASS" if abs(app_v - ext_v) < 0.25 else "FAIL"
    notes = "" if status == "PASS" else f"Parsed ABV {app_v}% vs {ext_v}%"
    return FieldComparison(
        field_name="Alcohol Content",
        application_value=app,
        extracted_value=ext,
        status=status,
        notes=notes,
    )


def compare_text_field(name: str, app: str, ext: str, threshold: float = 0.55) -> FieldComparison:
    app_n = normalize_whitespace(app).lower()
    ext_n = normalize_whitespace(ext).lower()
    if not ext_n:
        return FieldComparison(
            field_name=name,
            application_value=app,
            extracted_value=ext,
            status="REVIEW",
            notes=f"{name} not extracted from label",
        )
    if app_n in ext_n or ext_n in app_n:
        return FieldComparison(
            field_name=name,
            application_value=app,
            extracted_value=ext,
            status="PASS",
            notes="",
        )
    overlap = _token_overlap(app, ext)
    status: FieldStatus = "PASS" if overlap >= threshold else "FAIL"
    notes = "" if status == "PASS" else f"Token overlap {overlap:.2f}"
    return FieldComparison(
        field_name=name,
        application_value=app,
        extracted_value=ext,
        status=status,
        notes=notes,
    )


def compare_government_warning(app: str, ext: str) -> FieldComparison:
    app_n = normalize_whitespace(app)
    ext_n = normalize_whitespace(ext)
    if not ext_n:
        return FieldComparison(
            field_name="Government Warning",
            application_value=app,
            extracted_value=ext,
            status="REVIEW",
            notes="Warning not extracted from label",
        )
    if not re.match(r"^GOVERNMENT WARNING:", ext_n):
        return FieldComparison(
            field_name="Government Warning",
            application_value=app,
            extracted_value=ext,
            status="FAIL",
            notes="Extracted warning must begin with GOVERNMENT WARNING: in all caps",
        )
    if app_n == ext_n:
        return FieldComparison(
            field_name="Government Warning",
            application_value=app,
            extracted_value=ext,
            status="PASS",
            notes="",
        )

    overlap = _token_overlap(app, ext)
    if overlap >= 0.88:
        return FieldComparison(
            field_name="Government Warning",
            application_value=app,
            extracted_value=ext,
            status="PASS",
            notes=f"Warning matches after OCR tolerance (token overlap {overlap:.2f})",
        )

    critical_phrases = (
        "surgeon general",
        "pregnancy",
        "birth defects",
        "impairs your ability",
        "health problems",
    )
    ext_lower = ext_n.lower()
    missing = [phrase for phrase in critical_phrases if phrase not in ext_lower]
    if not missing and overlap >= 0.72:
        return FieldComparison(
            field_name="Government Warning",
            application_value=app,
            extracted_value=ext,
            status="REVIEW",
            notes=f"Warning text likely correct but OCR introduced errors (overlap {overlap:.2f})",
        )

    return FieldComparison(
        field_name="Government Warning",
        application_value=app,
        extracted_value=ext,
        status="FAIL",
        notes=f"Warning text mismatch (token overlap {overlap:.2f})",
    )


def compare_all(application: ApplicationFields, extracted: ApplicationFields) -> list[FieldComparison]:
    return [
        compare_brand(application.brand_name, extracted.brand_name),
        compare_text_field("Class/Type", application.class_type, extracted.class_type),
        compare_abv(application.alcohol_content, extracted.alcohol_content),
        compare_text_field("Net Contents", application.net_contents, extracted.net_contents, 0.4),
        compare_government_warning(application.government_warning, extracted.government_warning),
    ]


def overall_status(fields: list[FieldComparison]) -> FieldStatus:
    if any(f.status == "FAIL" for f in fields):
        return "FAIL"
    if any(f.status == "REVIEW" for f in fields):
        return "REVIEW"
    return "PASS"


def build_verification_result(
    *,
    application: ApplicationFields,
    extracted: ApplicationFields,
    filename: str,
    llm_model: str,
    rotation_deg: int,
    was_upright: bool,
    ocr_text: str,
    log_lines: list[str],
) -> VerificationResult:
    fields = compare_all(application, extracted)
    rotation_note = ""
    if not was_upright:
        rotation_note = f"Label appears rotated {rotation_deg} degrees; text extracted after deskew"

    return VerificationResult(
        filename=filename,
        llm_model=llm_model,
        rotation=RotationInfo(
            detected_rotation_deg=rotation_deg,
            was_upright=was_upright,
            note=rotation_note,
        ),
        fields=fields,
        overall_status=overall_status(fields),
        ocr_text=ocr_text,
        ocr_text_preview=(ocr_text[:500] + "...") if len(ocr_text) > 500 else ocr_text,
        log_lines=log_lines,
    )
