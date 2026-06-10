from __future__ import annotations

import gc
import os
import re
from dataclasses import dataclass

import cv2
import numpy as np

from app.ocr.backends.factory import get_backend, get_backend_name, get_rotation_backend_name, warm_backend
from app.ocr.label_region import LabelRegionInfo, extract_label_region
from app.ocr.field_assembly import assemble_label_text, assemble_warning_from_region


@dataclass
class OCRResult:
    text: str
    detected_rotation_deg: int
    skew_correction_deg: int = 0
    was_upright: bool = True
    confidence: float = 0.0
    label_region: LabelRegionInfo | None = None


FINE_SKEW_ANGLES = (-15, -12, -9, -6, -3, 3, 6, 9, 12, 15)
FINE_SKEW_ANGLES_CARDINAL = (-6, -3, 3, 6)


def get_reader():
    """Legacy EasyOCR warmup hook."""
    from app.ocr.backends.factory import get_reader as _legacy_get_reader

    return _legacy_get_reader()


def _decode_image(image_bytes: bytes) -> np.ndarray:
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Unsupported or unreadable image")
    return image


def _resize(image: np.ndarray, max_width: int = 1600) -> np.ndarray:
    height, width = image.shape[:2]
    if width <= max_width:
        return image
    scale = max_width / width
    return cv2.resize(image, (max_width, int(height * scale)), interpolation=cv2.INTER_AREA)


def _preprocess_for_ocr(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)


def _rotate_image(image: np.ndarray, angle: int) -> np.ndarray:
    if angle == 0:
        return image
    if angle == 90:
        return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    if angle == 180:
        return cv2.rotate(image, cv2.ROTATE_180)
    if angle == 270:
        return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
    raise ValueError(f"Unsupported rotation angle: {angle}")


def _rotate_arbitrary(image: np.ndarray, angle_deg: float) -> np.ndarray:
    if abs(angle_deg) < 0.01:
        return image
    height, width = image.shape[:2]
    center = (width / 2, height / 2)
    matrix = cv2.getRotationMatrix2D(center, angle_deg, 1.0)
    cos = abs(matrix[0, 0])
    sin = abs(matrix[0, 1])
    new_width = int(height * sin + width * cos)
    new_height = int(height * cos + width * sin)
    matrix[0, 2] += (new_width / 2) - center[0]
    matrix[1, 2] += (new_height / 2) - center[1]
    fill = (255, 255, 255)
    if len(image.shape) == 2:
        fill = 255
    return cv2.warpAffine(
        image,
        matrix,
        (new_width, new_height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=fill,
    )


def _read_document(image: np.ndarray, *, backend_name: str | None = None, paragraph: bool = False):
    backend = get_backend(backend_name)
    document = backend.read(image, paragraph=paragraph)
    text = assemble_label_text(document)
    return text, document.score(), document


def _run_ocr(image: np.ndarray, *, paragraph: bool = False, backend_name: str | None = None) -> tuple[str, float]:
    text, score, _document = _read_document(image, backend_name=backend_name, paragraph=paragraph)
    return text, score


def _crop_by_y_fraction(image: np.ndarray, y_start: float, y_end: float) -> np.ndarray:
    height = image.shape[0]
    top = int(height * y_start)
    bottom = int(height * y_end)
    crop = image[top:bottom, :]
    return crop if crop.size else image[:0]


def _ocr_brand_candidates(image: np.ndarray) -> list[str]:
    from app.parser import extract_abv_value, is_volume_label_read

    candidates: list[str] = []
    for y_start, y_end in ((0.0, 0.24), (0.30, 0.72)):
        crop = _crop_by_y_fraction(image, y_start, y_end)
        if crop.size == 0:
            continue
        crop = cv2.resize(crop, None, fx=2.5, fy=2.5, interpolation=cv2.INTER_CUBIC)
        crop = _preprocess_for_ocr(crop)
        region_text, _ = _run_ocr(crop)
        for line in region_text.splitlines():
            line = line.strip()
            if not line:
                continue
            if is_volume_label_read(line) or extract_abv_value(line) is not None:
                continue
            if "government warning" in line.lower():
                continue
            candidates.append(line)
    return candidates


def improve_brand_line(text: str, image: np.ndarray, application_brand: str) -> str:
    from app.parser import brand_similarity, label_brand_from_ocr

    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return text

    current = label_brand_from_ocr(text) or lines[0].strip()
    best = current
    best_score = brand_similarity(application_brand, current)

    for candidate in _ocr_brand_candidates(image):
        score = brand_similarity(application_brand, candidate)
        if score > best_score:
            best = candidate
            best_score = score

    if not best or best == current:
        return text

    for index, line in enumerate(lines):
        if brand_similarity(application_brand, line.strip()) >= best_score * 0.85:
            lines[index] = best
            return "\n".join(lines)
    lines[0] = best
    return "\n".join(lines)


def _ocr_warning_region(image: np.ndarray) -> str:
    crop = _crop_by_y_fraction(image, 0.52, 1.0)
    if crop.size == 0:
        return ""
    crop = cv2.resize(crop, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    crop = _preprocess_for_ocr(crop)
    backend = get_backend()
    document = backend.read(crop, paragraph=True)
    return assemble_warning_from_region(document) or assemble_label_text(document)


def _refine_skew(
    image: np.ndarray,
    text: str,
    score: float,
    *,
    cardinal_angle: int,
    backend_name: str,
) -> tuple[str, float, int]:
    angles = FINE_SKEW_ANGLES if cardinal_angle == 0 else FINE_SKEW_ANGLES_CARDINAL
    best_text = text
    best_score = score
    best_skew = 0
    baseline_combined = _rotation_selection_score(text, score)
    best_combined = baseline_combined

    for skew in angles:
        rotated = _rotate_arbitrary(image, skew)
        preprocessed = _preprocess_for_ocr(rotated)
        candidate_text, candidate_score = _run_ocr(preprocessed, backend_name=backend_name)
        combined = _rotation_selection_score(candidate_text, candidate_score)
        if combined > best_combined:
            best_combined = combined
            best_text = candidate_text
            best_score = candidate_score
            best_skew = skew

    if not _skew_correction_worth_apply(best_skew, baseline_combined, best_combined):
        return text, score, 0
    return best_text, best_score, best_skew


def _skew_correction_worth_apply(skew: int, baseline: float, improved: float) -> bool:
    if skew == 0:
        return False
    gain = improved - baseline
    magnitude = abs(skew)
    if magnitude <= 3:
        return False
    if magnitude >= 6:
        return gain >= 0.03
    if magnitude >= 4:
        return gain >= 0.05
    return gain >= 0.08


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def normalize_ocr_text(text: str) -> str:
    if not text:
        return ""

    text = text.replace("Alc.NVol:", "Alc./Vol.").replace("Alc.NVol.", "Alc./Vol.")
    text = re.sub(r"Alc\.?\s*[/\\]?\s*Vol\.?", "Alc./Vol.", text, flags=re.I)
    text = re.sub(r"Alc\s+NVol\.?", "Alc./Vol.", text, flags=re.I)
    text = re.sub(r"AlcNVol:?", "Alc./Vol.", text, flags=re.I)
    text = re.sub(r"problems_+", "problems.", text, flags=re.I)
    text = re.sub(r"\(27\s+Consumption", "(2) Consumption", text, re.I)

    match = re.search(r"GOVERNMENT\s+WARNING\s*:", text, re.I)
    if not match:
        return text.strip()

    header = text[: match.start()].strip()
    warning = normalize_whitespace(text[match.start() :])
    warning = re.sub(r"\bdrive\s+car\b", "drive a car", warning, flags=re.I)
    warning = re.sub(r",\s*and\s+cause\s+health", ", and may cause health", warning, flags=re.I)
    warning = re.sub(r"\bhealth\s+may\s+problems\b", "may cause health problems", warning, flags=re.I)
    warning = re.sub(r"\bmay\s+problems\b", "may cause health problems", warning, flags=re.I)
    if not warning.endswith("."):
        warning = warning.rstrip("_") + "."

    header_lines = [line.strip() for line in header.splitlines() if line.strip()]
    if header_lines:
        return "\n".join(header_lines + [warning])
    return warning


def _warning_looks_complete(text: str) -> bool:
    normalized = normalize_whitespace(text).lower()
    if not re.search(r"government warning:", normalized):
        return False
    required = (
        "surgeon general",
        "pregnancy",
        "birth defects",
        "impairs your ability",
    )
    if not all(part in normalized for part in required):
        return False
    return "health" in normalized and "problem" in normalized


def _label_readability_score(text: str) -> float:
    normalized = normalize_whitespace(text).lower()
    if not normalized:
        return 0.0
    score = 0.0
    keyword_weights = (
        ("government warning", 0.30),
        ("surgeon general", 0.12),
        ("bourbon", 0.08),
        ("whiskey", 0.08),
        ("distillery", 0.08),
        ("straight", 0.05),
        ("kentucky", 0.05),
        ("proof", 0.05),
        ("alc", 0.04),
        ("health problems", 0.08),
    )
    for phrase, weight in keyword_weights:
        if phrase in normalized:
            score += weight
    if re.search(r"\d+\s*%\s*alc", normalized):
        score += 0.10
    elif re.search(r"\d+\s*%", normalized):
        score += 0.05
    if re.search(r"\d+\s*ml", normalized):
        score += 0.08
    letters = sum(1 for char in normalized if char.isalpha())
    score += 0.12 * (letters / max(len(normalized), 1))
    return min(score, 1.0)


def _rotation_selection_score(text: str, ocr_score: float) -> float:
    readability = _label_readability_score(text)
    return ocr_score * (0.25 + 0.75 * readability)


def _looks_upright(text: str, ocr_score: float) -> bool:
    readability = _label_readability_score(text)
    if readability >= 0.55:
        return True
    if readability >= 0.40 and re.search(r"government warning", text, re.I):
        return True
    return readability >= 0.35 and ocr_score >= 200


def _merge_warning_text(full_text: str, warning_text: str) -> str:
    if not warning_text:
        return full_text
    match = re.search(r"GOVERNMENT\s+WARNING\s*:", warning_text, re.I)
    if not match:
        return full_text
    warning_body = warning_text[match.start() :].strip()
    full_match = re.search(r"GOVERNMENT\s+WARNING\s*:", full_text, re.I)
    if full_match:
        prefix = full_text[: full_match.start()].rstrip()
        return f"{prefix}\n{warning_body}".strip() if prefix else warning_body
    return f"{full_text.rstrip()}\n{warning_body}".strip()


def _parse_detection(detection):
    from app.ocr.backends.easyocr_backend import _parse_detection as _easyocr_parse

    return _easyocr_parse(detection)


def _group_detections_into_lines(detections: list):
    from app.ocr.backends.easyocr_backend import _group_detections_into_lines as _group

    lines, confidences = _group(detections)
    return lines, confidences


def extract_text_with_rotation(image_bytes: bytes) -> OCRResult:
    primary_backend = get_backend_name()
    rotation_backend = get_rotation_backend_name()

    image = _resize(_decode_image(image_bytes))
    image, label_region = extract_label_region(image)
    preprocessed = _preprocess_for_ocr(image)

    upright_text, upright_score = _run_ocr(preprocessed, backend_name=rotation_backend)
    best_angle = 0
    best_text = upright_text
    best_raw_score = upright_score
    best_score = _rotation_selection_score(upright_text, upright_score)

    if not _looks_upright(upright_text, upright_score):
        for angle in (90, 180, 270):
            rotated = _rotate_image(preprocessed, angle)
            text, score = _run_ocr(rotated, backend_name=rotation_backend)
            combined = _rotation_selection_score(text, score)
            if combined > best_score:
                best_score = combined
                best_text = text
                best_angle = angle
                best_raw_score = score

    final_image = _rotate_image(image, best_angle)
    final_preprocessed = _preprocess_for_ocr(final_image)

    if primary_backend == rotation_backend:
        best_text, best_raw_score = _run_ocr(final_preprocessed, backend_name=primary_backend)
        best_text, best_raw_score, best_skew = _refine_skew(
            final_preprocessed,
            best_text,
            best_raw_score,
            cardinal_angle=best_angle,
            backend_name=primary_backend,
        )
    else:
        _, _, best_skew = _refine_skew(
            final_preprocessed,
            best_text,
            best_raw_score,
            cardinal_angle=best_angle,
            backend_name=rotation_backend,
        )
        if best_skew:
            final_preprocessed = _preprocess_for_ocr(_rotate_arbitrary(final_preprocessed, best_skew))
        best_text, best_raw_score = _run_ocr(final_preprocessed, backend_name=primary_backend)

    if best_skew:
        final_image = _rotate_arbitrary(final_image, best_skew)

    merged_text = normalize_ocr_text(best_text)
    if not _warning_looks_complete(merged_text):
        warning_text = normalize_ocr_text(_ocr_warning_region(final_image))
        if warning_text and _label_readability_score(warning_text) >= _label_readability_score(merged_text):
            merged_text = normalize_ocr_text(_merge_warning_text(best_text, warning_text))
        else:
            merged_text = normalize_ocr_text(best_text)

    was_upright = best_angle == 0 and best_skew == 0
    avg_conf = best_raw_score / max(len(best_text), 1)
    gc.collect()
    return OCRResult(
        text=merged_text,
        detected_rotation_deg=best_angle,
        skew_correction_deg=best_skew,
        was_upright=was_upright,
        confidence=avg_conf,
        label_region=label_region,
    )
