from __future__ import annotations

import re

from app.parser import (
    brand_similarity,
    extract_abv_value,
    is_garbled_brand_read,
    is_garbled_prose_read,
    label_brand_from_ocr,
    label_class_from_ocr,
    label_fields_from_ocr,
    normalize_brand,
    normalize_warning_for_match,
    normalize_whitespace,
    ocr_normalize_for_match,
    parse_net_contents_ml,
    word_tokens,
    _looks_like_class_prefix_not_brand,
)
from app.schemas import ApplicationFields, FieldComparison, FieldStatus, RotationInfo, VerificationResult

FIELD_LABEL_TO_KEY = {
    "Brand Name": "brand_name",
    "Class/Type": "class_type",
    "Alcohol Content": "alcohol_content",
    "Net Contents": "net_contents",
    "Government Warning": "government_warning",
}

WARNING_PART_MARKERS = ("(1)", "(2)")
WARNING_CRITICAL_PHRASES = (
    "surgeon general",
    "pregnancy",
    "birth defects",
    "impairs your ability",
    "drive a car",
    "may cause health problems",
)


def _token_overlap(a: str, b: str) -> float:
    ta = set(re.findall(r"[a-z0-9']+", a.lower()))
    tb = set(re.findall(r"[a-z0-9']+", b.lower()))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _field_not_read_note(field_name: str) -> str:
    return f"Could not read {field_name.lower()} clearly from the label."


def _text_mismatch_note(field_name: str, application_value: str, label_value: str) -> str:
    app = normalize_whitespace(application_value)
    label = normalize_whitespace(label_value) or "—"
    if field_name == "Net Contents":
        return f"Application lists {app}; label shows {label}."
    if field_name == "Class/Type":
        return f"Product type on the label ({label}) does not match the application ({app})."
    if field_name == "Brand Name":
        return f"Application lists “{app}”; label shows “{label}”."
    if app and label and label != "—":
        return f"Application lists “{app}”; label shows “{label}”."
    return f"{field_name} on the label does not match the application."


def _label_read_from_ocr(ocr_text: str, attr: str) -> str:
    if not ocr_text:
        return ""
    parsed = label_fields_from_ocr(ocr_text)
    return getattr(parsed, attr, "") or ""


def _warning_phrase_present(normalized: str, phrase: str) -> bool:
    if phrase in normalized:
        return True
    ocr_aliases = {
        "drive a car": ("drive car", "drive a car or"),
        "may cause health problems": ("cause health problems", "may cause health problem"),
    }
    for alias in ocr_aliases.get(phrase, ()):
        if alias in normalized:
            return True
    return False


def _warning_missing_parts(text: str) -> list[str]:
    normalized = normalize_warning_for_match(text)
    missing: list[str] = []
    for marker in WARNING_PART_MARKERS:
        if marker not in normalized:
            missing.append(marker)
    for phrase in WARNING_CRITICAL_PHRASES:
        if not _warning_phrase_present(normalized, phrase):
            missing.append(phrase)
    return missing


def compare_brand(app: str, ext: str, *, ocr_text: str = "", label_read: str | None = None) -> FieldComparison:
    """Compare application brand to what OCR read on the label (not LLM corrections)."""
    if label_read is None:
        label_read = label_brand_from_ocr(ocr_text) if ocr_text else ""
    if label_read and _looks_like_class_prefix_not_brand(label_read):
        label_read = ""
    if not label_read and ext and not _looks_like_class_prefix_not_brand(ext):
        label_read = ext

    app_n = normalize_brand(app)
    label_n = normalize_brand(label_read)
    score = brand_similarity(app, label_read)

    if not label_n:
        return FieldComparison(
            field_name="Brand Name",
            application_value=app,
            extracted_value=ext or label_read,
            status="REVIEW",
            notes=_field_not_read_note("brand name"),
        )

    if app_n == label_n:
        return FieldComparison(
            field_name="Brand Name",
            application_value=app,
            extracted_value=label_read,
            status="PASS",
            notes="",
        )

    if word_tokens(app) == word_tokens(label_read) and word_tokens(app):
        return FieldComparison(
            field_name="Brand Name",
            application_value=app,
            extracted_value=app,
            status="PASS",
            notes="Brand matches; name was split across multiple lines in OCR.",
        )

    if ocr_normalize_for_match(app) == ocr_normalize_for_match(label_read):
        return FieldComparison(
            field_name="Brand Name",
            application_value=app,
            extracted_value=app,
            status="PASS",
            notes="Brand matches; label uses a decorative or script font that was hard to read automatically.",
        )

    if not is_garbled_brand_read(label_read):
        return FieldComparison(
            field_name="Brand Name",
            application_value=app,
            extracted_value=label_read,
            status="FAIL",
            notes=_text_mismatch_note("Brand Name", app, label_read),
        )

    if score >= 0.82:
        return FieldComparison(
            field_name="Brand Name",
            application_value=app,
            extracted_value=app,
            status="PASS",
            notes="Brand matches; label uses a decorative or script font that was hard to read automatically.",
        )

    if score >= 0.68:
        return FieldComparison(
            field_name="Brand Name",
            application_value=app,
            extracted_value=label_read,
            status="REVIEW",
            notes="Brand may match, but the name on the label was unclear — please confirm manually.",
        )

    return FieldComparison(
        field_name="Brand Name",
        application_value=app,
        extracted_value=label_read,
        status="FAIL",
        notes=_text_mismatch_note("Brand Name", app, label_read),
    )


def compare_text_field(name: str, app: str, ext: str) -> FieldComparison:
    app_n = normalize_whitespace(app).lower()
    ext_n = normalize_whitespace(ext).lower()
    if not ext_n:
        return FieldComparison(
            field_name=name,
            application_value=app,
            extracted_value=ext,
            status="REVIEW",
            notes=_field_not_read_note(name.lower()),
        )
    if app_n == ext_n:
        return FieldComparison(
            field_name=name,
            application_value=app,
            extracted_value=ext,
            status="PASS",
            notes="",
        )

    if word_tokens(app) == word_tokens(ext) and word_tokens(app):
        return FieldComparison(
            field_name=name,
            application_value=app,
            extracted_value=app,
            status="PASS",
            notes=f"{name} matches; wording was split or reordered in OCR.",
        )

    if not is_garbled_prose_read(app) and not is_garbled_prose_read(ext):
        return FieldComparison(
            field_name=name,
            application_value=app,
            extracted_value=ext,
            status="FAIL",
            notes=_text_mismatch_note(name, app, ext),
        )

    overlap = _token_overlap(app, ext)
    if overlap >= 0.88:
        return FieldComparison(
            field_name=name,
            application_value=app,
            extracted_value=ext,
            status="REVIEW",
            notes=f"{name} is likely correct, but wording on the label was hard to read — please confirm manually.",
        )

    return FieldComparison(
        field_name=name,
        application_value=app,
        extracted_value=ext,
        status="FAIL",
        notes=_text_mismatch_note(name, app, ext),
    )


def compare_abv(app: str, ext: str, *, ocr_text: str = "", label_read: str | None = None) -> FieldComparison:
    if label_read is None:
        label_read = _label_read_from_ocr(ocr_text, "alcohol_content") or (ext if not ocr_text else "")
    app_v = extract_abv_value(app)
    label_v = extract_abv_value(label_read)

    if app_v is None or label_v is None:
        return FieldComparison(
            field_name="Alcohol Content",
            application_value=app,
            extracted_value=label_read,
            status="REVIEW",
            notes=_field_not_read_note("alcohol content"),
        )

    if abs(app_v - label_v) < 0.25:
        return FieldComparison(
            field_name="Alcohol Content",
            application_value=app,
            extracted_value=label_read,
            status="PASS",
            notes="",
        )

    return FieldComparison(
        field_name="Alcohol Content",
        application_value=app,
        extracted_value=label_read,
        status="FAIL",
        notes=f"Application lists {app_v:g}% alcohol; label shows {label_v:g}%.",
    )


def compare_net_contents(app: str, ext: str, *, ocr_text: str = "", label_read: str | None = None) -> FieldComparison:
    if label_read is None:
        label_read = _label_read_from_ocr(ocr_text, "net_contents") or (ext if not ocr_text else "")
    app_ml = parse_net_contents_ml(app)
    label_ml = parse_net_contents_ml(label_read)

    if app_ml is None or label_ml is None:
        return FieldComparison(
            field_name="Net Contents",
            application_value=app,
            extracted_value=label_read,
            status="REVIEW",
            notes=_field_not_read_note("net contents"),
        )

    if abs(app_ml - label_ml) < 0.01:
        return FieldComparison(
            field_name="Net Contents",
            application_value=app,
            extracted_value=label_read,
            status="PASS",
            notes="",
        )

    return FieldComparison(
        field_name="Net Contents",
        application_value=app,
        extracted_value=label_read,
        status="FAIL",
        notes=_text_mismatch_note("Net Contents", app, label_read),
    )


def compare_government_warning(app: str, ext: str, *, ocr_text: str = "", label_read: str | None = None) -> FieldComparison:
    if label_read is None:
        label_read = _label_read_from_ocr(ocr_text, "government_warning") or (ext if not ocr_text else "")
    app_n = normalize_whitespace(app)
    label_n = normalize_whitespace(label_read)

    if not label_n:
        return FieldComparison(
            field_name="Government Warning",
            application_value=app,
            extracted_value=label_read,
            status="REVIEW",
            notes=_field_not_read_note("government warning"),
        )

    if not re.match(r"^GOVERNMENT\s+WARNING\s*:", label_n):
        return FieldComparison(
            field_name="Government Warning",
            application_value=app,
            extracted_value=label_read,
            status="FAIL",
            notes='Warning on the label must begin with "GOVERNMENT WARNING:" in all capital letters.',
        )

    if app_n == label_n:
        return FieldComparison(
            field_name="Government Warning",
            application_value=app,
            extracted_value=label_read,
            status="PASS",
            notes="",
        )

    if normalize_warning_for_match(app) == normalize_warning_for_match(label_read):
        return FieldComparison(
            field_name="Government Warning",
            application_value=app,
            extracted_value=label_read,
            status="PASS",
            notes="",
        )

    missing = _warning_missing_parts(label_read)
    if "(2)" in missing or "may cause health problems" in missing:
        return FieldComparison(
            field_name="Government Warning",
            application_value=app,
            extracted_value=label_read,
            status="FAIL",
            notes="Government warning on the label is missing required wording from the application.",
        )

    if missing:
        return FieldComparison(
            field_name="Government Warning",
            application_value=app,
            extracted_value=label_read,
            status="FAIL",
            notes="Government warning on the label does not include all required phrases.",
        )

    overlap = _token_overlap(app, label_read)
    if overlap >= 0.85:
        return FieldComparison(
            field_name="Government Warning",
            application_value=app,
            extracted_value=label_read,
            status="REVIEW",
            notes="Warning wording is likely correct, but some words were hard to read on the label.",
        )

    return FieldComparison(
        field_name="Government Warning",
        application_value=app,
        extracted_value=label_read,
        status="FAIL",
        notes="Government warning on the label does not match the required application wording.",
    )


def _optional_label_read(label_fields: ApplicationFields | None, key: str) -> str | None:
    if label_fields is None:
        return None
    value = getattr(label_fields, key, "").strip()
    return value if value else None


def failed_field_keys(fields: list[FieldComparison]) -> list[str]:
    return [FIELD_LABEL_TO_KEY[field.field_name] for field in fields if field.status == "FAIL"]


def rescue_field_keys(fields: list[FieldComparison]) -> list[str]:
    """Field keys eligible for LLM rescue (compare FAIL or REVIEW)."""
    return [
        FIELD_LABEL_TO_KEY[field.field_name]
        for field in fields
        if field.status in ("FAIL", "REVIEW")
    ]


RESCUE_PASS_NOTE = "Parser could not read this field clearly; LLM located matching text in OCR."


def apply_rescue_notes(
    fields: list[FieldComparison],
    rescued_keys: list[str],
) -> list[FieldComparison]:
    rescued = set(rescued_keys)
    updated: list[FieldComparison] = []
    for field in fields:
        key = FIELD_LABEL_TO_KEY.get(field.field_name)
        if key in rescued and field.status == "PASS":
            note = RESCUE_PASS_NOTE if not field.notes else f"{field.notes} {RESCUE_PASS_NOTE}"
            updated.append(field.model_copy(update={"notes": note}))
        else:
            updated.append(field)
    return updated


def compare_all(
    application: ApplicationFields,
    extracted: ApplicationFields,
    *,
    ocr_text: str = "",
    label_fields: ApplicationFields | None = None,
) -> list[FieldComparison]:
    if label_fields is not None:
        class_read = label_fields.class_type or label_class_from_ocr(ocr_text)
        return [
            compare_brand(
                application.brand_name,
                extracted.brand_name,
                ocr_text=ocr_text,
                label_read=_optional_label_read(label_fields, "brand_name"),
            ),
            compare_text_field("Class/Type", application.class_type, class_read),
            compare_abv(
                application.alcohol_content,
                extracted.alcohol_content,
                ocr_text=ocr_text,
                label_read=_optional_label_read(label_fields, "alcohol_content"),
            ),
            compare_net_contents(
                application.net_contents,
                extracted.net_contents,
                ocr_text=ocr_text,
                label_read=_optional_label_read(label_fields, "net_contents"),
            ),
            compare_government_warning(
                application.government_warning,
                extracted.government_warning,
                ocr_text=ocr_text,
                label_read=_optional_label_read(label_fields, "government_warning"),
            ),
        ]

    class_read = label_class_from_ocr(ocr_text) if ocr_text else ""
    return [
        compare_brand(application.brand_name, extracted.brand_name, ocr_text=ocr_text),
        compare_text_field("Class/Type", application.class_type, class_read),
        compare_abv(application.alcohol_content, extracted.alcohol_content, ocr_text=ocr_text),
        compare_net_contents(application.net_contents, extracted.net_contents, ocr_text=ocr_text),
        compare_government_warning(application.government_warning, extracted.government_warning, ocr_text=ocr_text),
    ]


def overall_status(fields: list[FieldComparison]) -> FieldStatus:
    if any(f.status == "FAIL" for f in fields):
        return "FAIL"
    if any(f.status == "REVIEW" for f in fields):
        return "REVIEW"
    return "PASS"


def _rotation_note(
    rotation_deg: int,
    skew_correction_deg: int,
    was_upright: bool,
    *,
    brand_inverted: bool = False,
    per_sticker: bool = False,
    brand_rotation_deg: int = 0,
    warning_rotation_deg: int = 0,
) -> str:
    if per_sticker:
        brand_part = "upright" if brand_rotation_deg == 0 else f"rotated {brand_rotation_deg}°"
        warning_part = "upright" if warning_rotation_deg == 0 else f"rotated {warning_rotation_deg}°"
        return (
            f"Brand sticker {brand_part}; government warning strip {warning_part}. "
            "Each sticker was read with its own orientation correction."
        )
    if brand_inverted and rotation_deg == 0 and skew_correction_deg == 0:
        return (
            "Brand sticker is upside down while the government warning strip is upright. "
            "Each sticker was corrected independently before reading."
        )
    if was_upright:
        return ""
    if rotation_deg in (90, 180, 270) and skew_correction_deg:
        return (
            f"Label was turned {rotation_deg}° and tilted slightly; "
            "text was straightened before reading."
        )
    if rotation_deg in (90, 180, 270):
        return f"Label was turned {rotation_deg}°; text was adjusted before reading."
    if skew_correction_deg:
        return "Label was photographed at a slight angle; text was straightened before reading."
    return "Label orientation was adjusted before reading."


def build_verification_result(
    *,
    application: ApplicationFields,
    extracted: ApplicationFields,
    filename: str,
    llm_model: str,
    rotation_deg: int,
    skew_correction_deg: int = 0,
    was_upright: bool,
    brand_inverted: bool = False,
    per_sticker: bool = False,
    brand_rotation_deg: int = 0,
    warning_rotation_deg: int = 0,
    ocr_text: str,
    ocr_text_display: str | None = None,
    log_lines: list[str],
    label_fields: ApplicationFields | None = None,
) -> VerificationResult:
    fields = compare_all(
        application,
        extracted,
        ocr_text=ocr_text,
        label_fields=label_fields,
    )
    rotation_note = _rotation_note(
        rotation_deg,
        skew_correction_deg,
        was_upright,
        brand_inverted=brand_inverted,
        per_sticker=per_sticker,
        brand_rotation_deg=brand_rotation_deg,
        warning_rotation_deg=warning_rotation_deg,
    )
    display_text = ocr_text_display if ocr_text_display is not None else ocr_text

    return VerificationResult(
        filename=filename,
        llm_model=llm_model,
        rotation=RotationInfo(
            detected_rotation_deg=rotation_deg,
            skew_correction_deg=skew_correction_deg,
            was_upright=was_upright,
            brand_inverted=brand_inverted,
            per_sticker=per_sticker,
            brand_rotation_deg=brand_rotation_deg,
            warning_rotation_deg=warning_rotation_deg,
            note=rotation_note,
        ),
        fields=fields,
        overall_status=overall_status(fields),
        ocr_text=display_text,
        ocr_text_preview=(display_text[:500] + "...") if len(display_text) > 500 else display_text,
        log_lines=log_lines,
    )
