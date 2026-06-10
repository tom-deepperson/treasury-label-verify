from __future__ import annotations

import time

from app.compare import build_verification_result
from app.llm_service import OCR_PARSER_MODEL, extract_fields, use_llm
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
    ocr_text_raw = improve_brand_line(ocr.text, final_image, application.brand_name)
    rotation_bits = [f"{ocr.detected_rotation_deg}°"]
    if ocr.skew_correction_deg:
        rotation_bits.append(f"skew {ocr.skew_correction_deg:+d}°")
    log_lines.append(
        f"> OCR complete [rotation: {', '.join(rotation_bits)}, {time.perf_counter() - ocr_started:.1f}s]"
    )
    if not ocr.was_upright:
        if ocr.detected_rotation_deg:
            log_lines.append(f"> Label was turned {ocr.detected_rotation_deg}° before reading")
        elif ocr.skew_correction_deg:
            log_lines.append(
                f"> Label had slight tilt; straightened {abs(ocr.skew_correction_deg)}° before reading"
            )

    parse_started = time.perf_counter()
    if use_llm():
        log_lines.append(f"> LLM map phase [{llm_model}]...")
    else:
        log_lines.append("> Field parse [ocr_parser]...")
    extracted, mode = extract_fields(ocr_text_raw, llm_model, application=application)
    label_fields = extracted if mode == "llm_map" else None
    if mode == "regex_fallback":
        log_lines.append("> LLM map failed validation or unavailable; OCR parser fallback engaged")
    if use_llm():
        log_lines.append(f"> LLM map complete [{time.perf_counter() - parse_started:.1f}s]")
    else:
        log_lines.append(f"> Field parse complete [{time.perf_counter() - parse_started:.1f}s]")

    result_model = llm_model if mode == "llm_map" else OCR_PARSER_MODEL

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
        ocr_text=ocr_text_raw,
        ocr_text_display=ocr_text_display,
        log_lines=log_lines,
        label_fields=label_fields,
    )
    log_lines.append(f"> DONE [{result.overall_status}, total {time.perf_counter() - started:.1f}s]")
    result.log_lines = log_lines
    return result
