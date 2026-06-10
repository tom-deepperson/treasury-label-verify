from __future__ import annotations

import time

from app.compare import build_verification_result, compare_all, overall_status, apply_rescue_notes, rescue_field_keys
from app.llm_service import OCR_PARSER_MODEL, extract_fields, rescue_failed_fields, use_llm
from app.ocr_service import (
    extract_text_with_rotation,
    improve_brand_line,
    _decode_image,
    _resize,
    _rotate_arbitrary,
    _rotate_image,
)
from app.ocr.label_region import extract_label_region
from app.parser import clarify_brand_in_ocr_text
from app.schemas import ApplicationFields, VerificationResult


def run_verification(
    *,
    image_bytes: bytes,
    application: ApplicationFields,
    filename: str,
    llm_model: str,
) -> VerificationResult:
    started = time.perf_counter()
    log_lines: list[str] = []
    log_lines.append("> OCR phase starting...")
    ocr_started = time.perf_counter()
    ocr = extract_text_with_rotation(image_bytes)
    final_image = _rotate_image(_resize(_decode_image(image_bytes)), ocr.detected_rotation_deg)
    if ocr.label_region and ocr.label_region.label_region_used:
        final_image, _ = extract_label_region(final_image)
    if ocr.skew_correction_deg:
        final_image = _rotate_arbitrary(final_image, ocr.skew_correction_deg)
    brand_image = ocr.brand_crop if ocr.brand_crop is not None else final_image
    ocr_text_raw = improve_brand_line(ocr.text, brand_image, application.brand_name)
    raw_lines = ocr.raw_lines or [line for line in ocr_text_raw.splitlines() if line.strip()]
    if ocr.per_sticker:
        rotation_bits = [
            f"brand {ocr.brand_rotation_deg}°",
            f"warning {ocr.warning_rotation_deg}°",
        ]
    else:
        rotation_bits = [f"{ocr.detected_rotation_deg}°"]
        if ocr.skew_correction_deg:
            rotation_bits.append(f"skew {ocr.skew_correction_deg:+d}°")
    log_lines.append(
        f"> OCR complete [rotation: {', '.join(rotation_bits)}, {time.perf_counter() - ocr_started:.1f}s]"
    )
    if ocr.per_sticker:
        log_lines.append(
            f"> Per-sticker correction: brand {ocr.brand_rotation_deg}°, "
            f"warning strip {ocr.warning_rotation_deg}°"
        )
    elif not ocr.was_upright:
        if ocr.brand_inverted and not ocr.detected_rotation_deg and not ocr.skew_correction_deg:
            log_lines.append(
                "> Brand sticker appears inverted (warning strip upright); corrected per sticker"
            )
        elif ocr.detected_rotation_deg:
            log_lines.append(f"> Label was turned {ocr.detected_rotation_deg}° before reading")
        elif ocr.skew_correction_deg:
            log_lines.append(
                f"> Label had slight tilt; straightened {abs(ocr.skew_correction_deg)}° before reading"
            )

    parse_started = time.perf_counter()
    log_lines.append("> Field parse [ocr_parser]...")
    extracted, _mode, _parse_error = extract_fields(ocr_text_raw, llm_model, application=application)
    log_lines.append(f"> Field parse complete [{time.perf_counter() - parse_started:.1f}s]")

    result_model = OCR_PARSER_MODEL
    ocr_text_display = clarify_brand_in_ocr_text(ocr_text_raw, application.brand_name)

    log_lines.append("> COMPARE phase...")
    result = build_verification_result(
        application=application,
        extracted=extracted,
        filename=filename,
        llm_model=result_model,
        rotation_deg=ocr.detected_rotation_deg,
        skew_correction_deg=ocr.skew_correction_deg,
        was_upright=ocr.was_upright,
        brand_inverted=ocr.brand_inverted,
        per_sticker=ocr.per_sticker,
        brand_rotation_deg=ocr.brand_rotation_deg,
        warning_rotation_deg=ocr.warning_rotation_deg,
        ocr_text=ocr_text_raw,
        ocr_text_display=ocr_text_display,
        log_lines=log_lines,
        label_fields=None,
    )

    rescue_keys = rescue_field_keys(result.fields)
    if use_llm() and rescue_keys:
        rescue_started = time.perf_counter()
        log_lines.append(f"> LLM rescue phase [{llm_model}] for {', '.join(rescue_keys)}...")
        rescued, rescue_error = rescue_failed_fields(raw_lines, application, rescue_keys, llm_model)
        if rescue_error:
            log_lines.append(f"> LLM rescue failed: {rescue_error}")
        elif rescued:
            log_lines.append(f"> LLM rescue complete [{time.perf_counter() - rescue_started:.1f}s]")
            result_model = llm_model
            rescued_keys_applied = [key for key in rescue_keys if getattr(rescued, key, "").strip()]
            fields = compare_all(
                application,
                extracted,
                ocr_text=ocr_text_raw,
                label_fields=rescued,
            )
            fields = apply_rescue_notes(fields, rescued_keys_applied)
            result.fields = fields
            result.overall_status = overall_status(fields)
            result.llm_model = result_model
        else:
            log_lines.append("> LLM rescue found no valid reads")

    log_lines.append(f"> DONE [{result.overall_status}, total {time.perf_counter() - started:.1f}s]")
    result.log_lines = log_lines
    return result
