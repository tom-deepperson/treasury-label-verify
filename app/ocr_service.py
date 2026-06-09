from __future__ import annotations

import os
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


def _resize(image: np.ndarray, max_width: int = 1200) -> np.ndarray:
    height, width = image.shape[:2]
    if width <= max_width:
        return image
    scale = max_width / width
    return cv2.resize(image, (max_width, int(height * scale)), interpolation=cv2.INTER_AREA)


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


def _run_ocr(image: np.ndarray) -> tuple[str, float]:
    reader = get_reader()
    detections = reader.readtext(image)
    if not detections:
        return "", 0.0
    lines = []
    confidences = []
    for _box, text, conf in detections:
        lines.append(text)
        confidences.append(float(conf))
    text = "\n".join(lines)
    avg_conf = sum(confidences) / len(confidences)
    score = avg_conf * max(len(text), 1)
    return text, score


def extract_text_with_rotation(image_bytes: bytes) -> OCRResult:
    image = _resize(_decode_image(image_bytes))
    angles = [0, 90, 180, 270]
    best_text = ""
    best_angle = 0
    best_score = -1.0

    baseline_text = ""
    baseline_score = -1.0
    for angle in angles:
        rotated = _rotate_image(image, angle)
        text, score = _run_ocr(rotated)
        if angle == 0:
            baseline_text = text
            baseline_score = score
        if score > best_score:
            best_score = score
            best_text = text
            best_angle = angle

    early_exit_threshold = float(os.getenv("OCR_EARLY_EXIT_SCORE", "80"))
    if baseline_score >= early_exit_threshold:
        best_angle = 0
        best_text = baseline_text
        best_score = baseline_score

    was_upright = best_angle == 0
    avg_conf = best_score / max(len(best_text), 1)
    return OCRResult(
        text=best_text,
        detected_rotation_deg=best_angle,
        was_upright=was_upright,
        confidence=avg_conf,
    )
