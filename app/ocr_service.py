from __future__ import annotations

import gc
import os
import re
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class OCRResult:
    text: str
    detected_rotation_deg: int
    was_upright: bool
    confidence: float


_reader = None


def get_reader():
    global _reader
    if _reader is None:
        import easyocr

        _reader = easyocr.Reader(["en"], gpu=False, verbose=False)
    return _reader


def _decode_image(image_bytes: bytes) -> np.ndarray:
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Unsupported or unreadable image")
    return image


def _resize(image: np.ndarray, max_width: int = 960) -> np.ndarray:
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


def _sort_detections(detections: list) -> list:
    def sort_key(item):
        box = item[0]
        ys = [point[1] for point in box]
        xs = [point[0] for point in box]
        return (min(ys), min(xs))

    return sorted(detections, key=sort_key)


def _run_ocr(image: np.ndarray, *, paragraph: bool = False) -> tuple[str, float]:
    reader = get_reader()
    detections = _sort_detections(reader.readtext(image, paragraph=paragraph))
    if not detections:
        return "", 0.0
    lines = []
    confidences = []
    for _box, text, conf in detections:
        cleaned = text.strip()
        if cleaned:
            lines.append(cleaned)
            confidences.append(float(conf))
    text = "\n".join(lines)
    avg_conf = sum(confidences) / len(confidences)
    score = avg_conf * max(len(text), 1)
    return text, score


def _ocr_warning_region(image: np.ndarray) -> str:
    height = image.shape[0]
    crop = image[int(height * 0.52) :, :]
    if crop.size == 0:
        return ""
    crop = cv2.resize(crop, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    crop = _preprocess_for_ocr(crop)
    text, _ = _run_ocr(crop, paragraph=True)
    return text.strip()


def _warning_looks_complete(text: str) -> bool:
    normalized = normalize_whitespace(text)
    if not re.search(r"GOVERNMENT WARNING:", normalized, re.I):
        return False
    lower = normalized.lower()
    required = (
        "surgeon general",
        "pregnancy",
        "birth defects",
        "impairs your ability",
        "health problems",
    )
    return all(part in lower for part in required)


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


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


def extract_text_with_rotation(image_bytes: bytes) -> OCRResult:
    image = _resize(_decode_image(image_bytes))
    preprocessed = _preprocess_for_ocr(image)
    early_exit_threshold = float(os.getenv("OCR_EARLY_EXIT_SCORE", "80"))

    upright_text, upright_score = _run_ocr(preprocessed)
    best_angle = 0
    best_text = upright_text
    best_score = upright_score

    if upright_score < early_exit_threshold:
        for angle in (90, 180, 270):
            rotated = _rotate_image(preprocessed, angle)
            text, score = _run_ocr(rotated)
            if score > best_score:
                best_score = score
                best_text = text
                best_angle = angle

    final_image = _rotate_image(image, best_angle)
    merged_text = best_text
    if not _warning_looks_complete(best_text):
        warning_text = _ocr_warning_region(final_image)
        merged_text = _merge_warning_text(best_text, warning_text)

    was_upright = best_angle == 0
    avg_conf = best_score / max(len(best_text), 1)
    gc.collect()
    return OCRResult(
        text=merged_text,
        detected_rotation_deg=best_angle,
        was_upright=was_upright,
        confidence=avg_conf,
    )
