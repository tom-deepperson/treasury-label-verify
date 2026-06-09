from __future__ import annotations

from app.compare import build_verification_result
from app.llm_service import extract_fields
from app.ocr_service import extract_text_with_rotation
from app.schemas import ApplicationFields, VerificationResult


def run_verification(
    *,
    image_bytes: bytes,
    application: ApplicationFields,
    filename: str,
    llm_model: str,
) -> VerificationResult:
    log_lines: list[str] = []
    log_lines.append("> OCR phase starting...")
    ocr = extract_text_with_rotation(image_bytes)
    log_lines.append(f"> OCR complete [rotation: {ocr.detected_rotation_deg} deg]")
    if not ocr.was_upright:
        log_lines.append("> REVIEW: label not upright; deskewed before extraction")

    log_lines.append(f"> LLM phase [{llm_model}]...")
    extracted, mode = extract_fields(ocr.text, llm_model)
    if mode == "regex_fallback":
        log_lines.append("> LLM unavailable or failed; regex parser fallback engaged")

    log_lines.append("> COMPARE phase...")
    result = build_verification_result(
        application=application,
        extracted=extracted,
        filename=filename,
        llm_model=llm_model,
        rotation_deg=ocr.detected_rotation_deg,
        was_upright=ocr.was_upright,
        ocr_text=ocr.text,
        log_lines=log_lines,
    )
    log_lines.append(f"> DONE [{result.overall_status}]")
    result.log_lines = log_lines
    return result
