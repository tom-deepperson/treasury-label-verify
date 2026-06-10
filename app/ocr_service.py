from __future__ import annotations

import gc
import os
import re
from dataclasses import dataclass
from typing import Literal

import cv2
import numpy as np

from app.ocr.backends.factory import get_backend, get_backend_name, get_rotation_backend_name, warm_backend
from app.ocr.label_region import LabelRegionInfo, extract_label_region
from app.ocr.field_assembly import assemble_label_text, assemble_warning_from_region, raw_lines_from_document
from app.ocr.sticker_regions import StickerRegion, discover_sticker_regions


@dataclass
class StickerOCRResult:
    role: Literal["brand", "warning"]
    text: str
    raw_lines: list[str]
    rotation_deg: int
    skew_deg: int
    corrected_crop: np.ndarray | None = None


@dataclass
class OCRResult:
    text: str
    detected_rotation_deg: int
    skew_correction_deg: int = 0
    was_upright: bool = True
    brand_inverted: bool = False
    per_sticker: bool = False
    brand_rotation_deg: int = 0
    warning_rotation_deg: int = 0
    confidence: float = 0.0
    label_region: LabelRegionInfo | None = None
    raw_lines: list[str] | None = None
    brand_crop: np.ndarray | None = None


_BRAND_REGION_X_END = 0.48
_BRAND_REGION_Y_END = 0.72


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


def _prepare_for_backend(image: np.ndarray, backend_name: str | None) -> np.ndarray:
    """Vision reads color labels better; local EasyOCR uses grayscale CLAHE."""
    if (backend_name or get_backend_name()) == "vision":
        return image
    return _preprocess_for_ocr(image)


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


def _run_ocr(
    image: np.ndarray,
    *,
    paragraph: bool = False,
    backend_name: str | None = None,
) -> tuple[str, float]:
    text, score, _document = _read_document(image, backend_name=backend_name, paragraph=paragraph)
    return text, score


def _run_ocr_with_document(
    image: np.ndarray,
    *,
    paragraph: bool = False,
    backend_name: str | None = None,
):
    return _read_document(image, backend_name=backend_name, paragraph=paragraph)


def _extend_raw_lines(raw_lines: list[str], extra_text: str) -> list[str]:
    seen = {line.lower() for line in raw_lines}
    for line in extra_text.splitlines():
        cleaned = normalize_whitespace(line)
        if cleaned and cleaned.lower() not in seen:
            raw_lines.append(cleaned)
            seen.add(cleaned.lower())
    return raw_lines


def _crop_by_y_fraction(image: np.ndarray, y_start: float, y_end: float) -> np.ndarray:
    height = image.shape[0]
    top = int(height * y_start)
    bottom = int(height * y_end)
    crop = image[top:bottom, :]
    return crop if crop.size else image[:0]


def _crop_by_x_fraction(image: np.ndarray, x_start: float, x_end: float) -> np.ndarray:
    width = image.shape[1]
    left = int(width * x_start)
    right = int(width * x_end)
    crop = image[:, left:right]
    return crop if crop.size else image[:, :0]


def _ocr_brand_candidates(image: np.ndarray) -> list[str]:
    from app.parser import (
        _extract_distillery_brand,
        _looks_like_class_prefix_not_brand,
        extract_abv_value,
        is_volume_label_read,
    )
    from app.ocr.noise import is_batch_lot_line

    candidates: list[str] = []
    seen: set[str] = set()
    for y_start, y_end in ((0.0, 0.24), (0.30, 0.72), (0.38, 0.58)):
        crop = _crop_by_y_fraction(image, y_start, y_end)
        if crop.size == 0:
            continue
        crop = cv2.resize(crop, None, fx=2.5, fy=2.5, interpolation=cv2.INTER_CUBIC)
        crop = _prepare_for_backend(crop, get_backend_name())
        region_text, _ = _run_ocr(crop)
        for line in region_text.splitlines():
            line = line.strip()
            if not line:
                continue
            key = line.lower()
            if key in seen:
                continue
            seen.add(key)
            if is_volume_label_read(line) or extract_abv_value(line) is not None:
                continue
            if "government warning" in line.lower():
                continue
            if is_batch_lot_line(line) or _looks_like_class_prefix_not_brand(line):
                continue
            distillery = _extract_distillery_brand(line)
            if distillery:
                candidates.append(distillery)
                continue
            candidates.append(line)
    return candidates


def improve_brand_line(text: str, image: np.ndarray, application_brand: str) -> str:
    from app.parser import (
        _BRAND_DISTILLERY_HINTS,
        brand_similarity,
        label_brand_from_ocr,
        _looks_like_class_prefix_not_brand,
    )

    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return text

    current = label_brand_from_ocr(text) or lines[0].strip()
    if _looks_like_class_prefix_not_brand(current):
        current = ""
    best = current
    best_score = brand_similarity(application_brand, current) if current else 0.0

    for candidate in _ocr_brand_candidates(image):
        score = brand_similarity(application_brand, candidate)
        if any(hint in candidate.lower() for hint in _BRAND_DISTILLERY_HINTS):
            score = min(1.0, score + 0.08)
        if score > best_score:
            best = candidate
            best_score = score

    if not best or best_score < 0.45:
        return text
    if best == current and current:
        return text

    for index, line in enumerate(lines):
        if brand_similarity(application_brand, line.strip()) >= best_score * 0.85:
            lines[index] = best
            return "\n".join(lines)

    if current and _looks_like_class_prefix_not_brand(lines[0]):
        lines[0] = best
    else:
        lines.insert(0, best)
    return "\n".join(lines)


def _ocr_warning_region(image: np.ndarray) -> tuple[str, list[str]]:
    crop = _crop_by_y_fraction(image, 0.52, 1.0)
    if crop.size == 0:
        return "", []
    crop = cv2.resize(crop, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    backend_name = get_backend_name()
    crop = _prepare_for_backend(crop, backend_name)
    backend = get_backend(backend_name)
    document = backend.read(crop, paragraph=True)
    warning = assemble_warning_from_region(document) or assemble_label_text(document)
    return warning, raw_lines_from_document(document)


def _refine_skew(
    image: np.ndarray,
    text: str,
    score: float,
    *,
    cardinal_angle: int,
    backend_name: str,
) -> tuple[str, float, int]:
    if backend_name == "vision" and _label_readability_score(text) >= 0.45:
        return text, score, 0
    angles = FINE_SKEW_ANGLES if cardinal_angle == 0 else FINE_SKEW_ANGLES_CARDINAL
    if backend_name == "vision":
        angles = FINE_SKEW_ANGLES_CARDINAL
    best_text = text
    best_score = score
    best_skew = 0
    baseline_combined = _rotation_selection_score(text, score)
    best_combined = baseline_combined

    for skew in angles:
        rotated = _rotate_arbitrary(image, skew)
        prepared = _prepare_for_backend(rotated, backend_name)
        candidate_text, candidate_score = _run_ocr(prepared, backend_name=backend_name)
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


def _best_cardinal_rotation(
    crop: np.ndarray,
    *,
    rotation_backend: str,
) -> tuple[int, float, str]:
    """Return best 0/90/180/270 angle and score for a sticker crop."""
    enlarged = cv2.resize(crop, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    prepared = _prepare_for_backend(enlarged, rotation_backend)
    upright_text, upright_score = _run_ocr(prepared, backend_name=rotation_backend)
    best_angle = 0
    best_text = upright_text
    best_score = _rotation_selection_score(upright_text, upright_score)

    for angle in (90, 180, 270):
        rotated = _rotate_image(prepared, angle)
        text, score = _run_ocr(rotated, backend_name=rotation_backend)
        combined = _rotation_selection_score(text, score)
        if combined > best_score:
            best_score = combined
            best_text = text
            best_angle = angle

    return best_angle, best_score, best_text


def _sticker_regions_for_image(image: np.ndarray) -> list[StickerRegion]:
    regions = discover_sticker_regions(image)
    if len(regions) >= 2:
        return regions
    brand_crop = _crop_by_x_fraction(image, 0.0, _BRAND_REGION_X_END)
    warning_crop = _crop_by_x_fraction(image, _BRAND_REGION_X_END, 1.0)
    height, width = image.shape[:2]
    fallback: list[StickerRegion] = []
    if brand_crop.size:
        fallback.append(
            StickerRegion(role="brand", bbox=(0, 0, int(width * _BRAND_REGION_X_END), height), crop=brand_crop)
        )
    if warning_crop.size:
        fallback.append(
            StickerRegion(
                role="warning",
                bbox=(int(width * _BRAND_REGION_X_END), 0, width, height),
                crop=warning_crop,
            )
        )
    return fallback or regions


def _ocr_sticker_crop(
    region: StickerRegion,
    *,
    primary_backend: str,
    rotation_backend: str,
) -> StickerOCRResult:
    best_angle, _, _ = _best_cardinal_rotation(region.crop, rotation_backend=rotation_backend)
    corrected = _rotate_image(region.crop, best_angle)
    enlarged = cv2.resize(corrected, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    rotation_input = _prepare_for_backend(enlarged, rotation_backend)
    primary_input = _prepare_for_backend(enlarged, primary_backend)

    if primary_backend == rotation_backend:
        text, score, document = _run_ocr_with_document(primary_input, backend_name=primary_backend)
        text, score, skew = _refine_skew(
            rotation_input,
            text,
            score,
            cardinal_angle=best_angle,
            backend_name=primary_backend,
        )
    else:
        text, score = _run_ocr(rotation_input, backend_name=rotation_backend)
        text, score, skew = _refine_skew(
            rotation_input,
            text,
            score,
            cardinal_angle=best_angle,
            backend_name=rotation_backend,
        )
        if skew:
            corrected = _rotate_arbitrary(corrected, skew)
            enlarged = cv2.resize(corrected, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
            primary_input = _prepare_for_backend(enlarged, primary_backend)
        text, score, document = _run_ocr_with_document(primary_input, backend_name=primary_backend)

    if skew:
        corrected = _rotate_arbitrary(corrected, skew)

    if region.role == "warning":
        warning = assemble_warning_from_region(document) or text
        raw_lines = raw_lines_from_document(document)
        return StickerOCRResult(
            role="warning",
            text=warning,
            raw_lines=raw_lines,
            rotation_deg=best_angle,
            skew_deg=skew,
            corrected_crop=corrected,
        )

    raw_lines = raw_lines_from_document(document)
    return StickerOCRResult(
        role="brand",
        text=text,
        raw_lines=raw_lines,
        rotation_deg=best_angle,
        skew_deg=skew,
        corrected_crop=corrected,
    )


def _merge_sticker_results(brand: StickerOCRResult, warning: StickerOCRResult) -> tuple[str, list[str]]:
    brand_text = normalize_ocr_text(brand.text)
    warning_text = normalize_ocr_text(warning.text)
    if warning_text:
        merged = normalize_ocr_text(_merge_warning_text(brand_text, warning_text))
    else:
        merged = brand_text
    raw_lines = list(brand.raw_lines)
    seen = {line.lower() for line in raw_lines}
    for line in warning.raw_lines:
        if line.lower() not in seen:
            raw_lines.append(line)
            seen.add(line.lower())
    return merged, raw_lines


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
        header = prefix or full_text.split("GOVERNMENT WARNING")[0].strip()
        header_lines = [line.strip() for line in header.splitlines() if line.strip()]
        if header_lines:
            return "\n".join(header_lines + [warning_body]).strip()
        return warning_body
    header_lines = [line.strip() for line in full_text.splitlines() if line.strip()]
    if header_lines:
        return "\n".join(header_lines + [warning_body]).strip()
    return warning_body


def _sticker_orientation_conflict(
    image: np.ndarray,
    *,
    rotation_backend: str,
) -> tuple[bool, int, int]:
    """True when brand and warning stickers prefer incompatible orientations."""
    regions = _sticker_regions_for_image(image)
    brand_region = next((region for region in regions if region.role == "brand"), None)
    warning_region = next((region for region in regions if region.role == "warning"), None)
    if not brand_region or not warning_region:
        return False, 0, 0

    brand_angle, brand_score, _ = _best_cardinal_rotation(brand_region.crop, rotation_backend=rotation_backend)
    warning_angle, warning_score, _ = _best_cardinal_rotation(
        warning_region.crop,
        rotation_backend=rotation_backend,
    )
    if brand_angle == warning_angle:
        return False, brand_angle, warning_angle

    # Primary case: warning strip upright while brand sticker reads best rotated.
    if warning_angle == 0 and brand_angle in (90, 180, 270):
        upright_only = cv2.resize(brand_region.crop, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        upright_only = _prepare_for_backend(upright_only, rotation_backend)
        upright_text, upright_raw = _run_ocr(upright_only, backend_name=rotation_backend)
        upright_score = _rotation_selection_score(upright_text, upright_raw)
        if brand_score > upright_score + 0.05:
            return True, brand_angle, warning_angle

    return False, brand_angle, warning_angle


def _run_per_sticker_ocr(
    image: np.ndarray,
    *,
    primary_backend: str,
    rotation_backend: str,
) -> tuple[StickerOCRResult, StickerOCRResult, str, list[str]]:
    regions = _sticker_regions_for_image(image)
    brand_region = next(region for region in regions if region.role == "brand")
    warning_region = next(region for region in regions if region.role == "warning")

    brand = _ocr_sticker_crop(brand_region, primary_backend=primary_backend, rotation_backend=rotation_backend)
    warning = _ocr_sticker_crop(warning_region, primary_backend=primary_backend, rotation_backend=rotation_backend)
    merged_text, raw_lines = _merge_sticker_results(brand, warning)
    return brand, warning, merged_text, raw_lines


def _looks_upright(text: str, ocr_score: float) -> bool:
    readability = _label_readability_score(text)
    if readability >= 0.55:
        return True
    if readability >= 0.40 and re.search(r"government warning", text, re.I):
        return True
    text_len = max(len(normalize_whitespace(text)), 1)
    avg_conf = ocr_score / text_len
    return readability >= 0.35 and (avg_conf >= 0.55 or ocr_score >= 180)


def _parse_detection(detection):
    from app.ocr.backends.easyocr_backend import _parse_detection as _easyocr_parse

    return _easyocr_parse(detection)


def _group_detections_into_lines(detections: list):
    from app.ocr.backends.easyocr_backend import _group_detections_into_lines as _group

    lines, confidences = _group(detections)
    return lines, confidences


def extract_text_with_rotation(image_bytes: bytes) -> OCRResult:
    return extract_text_per_sticker(image_bytes)


def extract_text_per_sticker(image_bytes: bytes) -> OCRResult:
    primary_backend = get_backend_name()
    rotation_backend = get_rotation_backend_name()

    image = _resize(_decode_image(image_bytes))
    image, label_region = extract_label_region(image)
    rotation_input = _prepare_for_backend(image, rotation_backend)

    upright_text, upright_score = _run_ocr(rotation_input, backend_name=rotation_backend)
    best_angle = 0
    best_text = upright_text
    best_raw_score = upright_score
    best_score = _rotation_selection_score(upright_text, upright_score)

    if not _looks_upright(upright_text, upright_score):
        for angle in (90, 180, 270):
            rotated = _rotate_image(rotation_input, angle)
            text, score = _run_ocr(rotated, backend_name=rotation_backend)
            combined = _rotation_selection_score(text, score)
            if combined > best_score:
                best_score = combined
                best_text = text
                best_angle = angle
                best_raw_score = score

    conflict = False
    uniform_sticker_angle = 0
    if best_angle == 0:
        conflict, brand_angle_hint, warning_angle_hint = _sticker_orientation_conflict(
            image,
            rotation_backend=rotation_backend,
        )
        if not conflict and brand_angle_hint == warning_angle_hint and brand_angle_hint != 0:
            uniform_sticker_angle = brand_angle_hint

    if uniform_sticker_angle:
        best_angle = uniform_sticker_angle
        best_skew = 0
        final_image = _rotate_image(image, best_angle)
        final_rotation_input = _prepare_for_backend(final_image, rotation_backend)
        final_primary_input = _prepare_for_backend(final_image, primary_backend)
        if primary_backend == rotation_backend:
            best_text, best_raw_score, primary_document = _run_ocr_with_document(
                final_primary_input,
                backend_name=primary_backend,
            )
            best_text, best_raw_score, best_skew = _refine_skew(
                final_rotation_input,
                best_text,
                best_raw_score,
                cardinal_angle=best_angle,
                backend_name=primary_backend,
            )
        else:
            _, _, best_skew = _refine_skew(
                final_rotation_input,
                best_text,
                best_raw_score,
                cardinal_angle=best_angle,
                backend_name=rotation_backend,
            )
            if best_skew:
                skewed = _rotate_arbitrary(final_image, best_skew)
                final_primary_input = _prepare_for_backend(skewed, primary_backend)
            best_text, best_raw_score, primary_document = _run_ocr_with_document(
                final_primary_input,
                backend_name=primary_backend,
            )
        if best_skew:
            final_image = _rotate_arbitrary(final_image, best_skew)
        raw_lines = raw_lines_from_document(primary_document)
        merged_text = normalize_ocr_text(best_text)
        if not _warning_looks_complete(merged_text):
            warning_text, warning_lines = _ocr_warning_region(final_image)
            warning_text = normalize_ocr_text(warning_text)
            if warning_text and _label_readability_score(warning_text) >= _label_readability_score(merged_text):
                merged_text = normalize_ocr_text(_merge_warning_text(best_text, warning_text))
                raw_lines = _extend_raw_lines(raw_lines, warning_text)
            if warning_lines:
                raw_lines = _extend_raw_lines(raw_lines, "\n".join(warning_lines))
        was_upright = best_angle == 0 and best_skew == 0
        avg_conf = best_raw_score / max(len(best_text), 1)
        gc.collect()
        return OCRResult(
            text=merged_text,
            detected_rotation_deg=best_angle,
            skew_correction_deg=best_skew,
            was_upright=was_upright,
            brand_inverted=False,
            per_sticker=False,
            brand_rotation_deg=best_angle,
            warning_rotation_deg=best_angle,
            confidence=avg_conf,
            label_region=label_region,
            raw_lines=raw_lines,
            brand_crop=None,
        )

    if conflict:
        brand_result, warning_result, merged_text, raw_lines = _run_per_sticker_ocr(
            image,
            primary_backend=primary_backend,
            rotation_backend=rotation_backend,
        )
        brand_inverted = brand_result.rotation_deg == 180 and warning_result.rotation_deg == 0
        avg_conf = _label_readability_score(merged_text)
        gc.collect()
        return OCRResult(
            text=merged_text,
            detected_rotation_deg=0,
            skew_correction_deg=0,
            was_upright=False,
            brand_inverted=brand_inverted,
            per_sticker=True,
            brand_rotation_deg=brand_result.rotation_deg,
            warning_rotation_deg=warning_result.rotation_deg,
            confidence=avg_conf,
            label_region=label_region,
            raw_lines=raw_lines,
            brand_crop=brand_result.corrected_crop,
        )

    final_image = _rotate_image(image, best_angle)
    final_rotation_input = _prepare_for_backend(final_image, rotation_backend)
    final_primary_input = _prepare_for_backend(final_image, primary_backend)

    if primary_backend == rotation_backend:
        best_text, best_raw_score, primary_document = _run_ocr_with_document(
            final_primary_input,
            backend_name=primary_backend,
        )
        best_text, best_raw_score, best_skew = _refine_skew(
            final_rotation_input,
            best_text,
            best_raw_score,
            cardinal_angle=best_angle,
            backend_name=primary_backend,
        )
    else:
        _, _, best_skew = _refine_skew(
            final_rotation_input,
            best_text,
            best_raw_score,
            cardinal_angle=best_angle,
            backend_name=rotation_backend,
        )
        if best_skew:
            skewed = _rotate_arbitrary(final_image, best_skew)
            final_primary_input = _prepare_for_backend(skewed, primary_backend)
        best_text, best_raw_score, primary_document = _run_ocr_with_document(
            final_primary_input,
            backend_name=primary_backend,
        )

    if best_skew:
        final_image = _rotate_arbitrary(final_image, best_skew)

    raw_lines = raw_lines_from_document(primary_document)
    merged_text = normalize_ocr_text(best_text)
    if not _warning_looks_complete(merged_text):
        warning_text, warning_lines = _ocr_warning_region(final_image)
        warning_text = normalize_ocr_text(warning_text)
        if warning_text and _label_readability_score(warning_text) >= _label_readability_score(merged_text):
            merged_text = normalize_ocr_text(_merge_warning_text(best_text, warning_text))
            raw_lines = _extend_raw_lines(raw_lines, warning_text)
        else:
            merged_text = normalize_ocr_text(best_text)
        if warning_lines:
            raw_lines = _extend_raw_lines(raw_lines, "\n".join(warning_lines))

    was_upright = best_angle == 0 and best_skew == 0
    avg_conf = best_raw_score / max(len(best_text), 1)
    gc.collect()
    return OCRResult(
        text=merged_text,
        detected_rotation_deg=best_angle,
        skew_correction_deg=best_skew,
        was_upright=was_upright,
        brand_inverted=False,
        per_sticker=False,
        brand_rotation_deg=best_angle,
        warning_rotation_deg=best_angle,
        confidence=avg_conf,
        label_region=label_region,
        raw_lines=raw_lines,
        brand_crop=None,
    )
