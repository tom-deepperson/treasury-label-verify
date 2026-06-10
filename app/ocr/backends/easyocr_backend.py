from __future__ import annotations

import numpy as np

from app.ocr.backends.base import OcrBackend, OcrDocument, OcrLine

_reader = None


def _get_reader():
    global _reader
    if _reader is None:
        import warnings

        warnings.filterwarnings(
            "ignore",
            message=".*pin_memory.*",
            category=UserWarning,
            module=r"torch\.utils\.data\.dataloader",
        )
        import easyocr

        _reader = easyocr.Reader(["en"], gpu=False, verbose=False)
    return _reader


def _parse_detection(detection) -> tuple[object, str, float]:
    if len(detection) == 3:
        box, text, conf = detection
        return box, str(text), float(conf)
    if len(detection) == 2:
        box, text = detection
        return box, str(text), 0.85
    raise ValueError(f"Unexpected EasyOCR detection format (len={len(detection)})")


def _median_box_height(detections: list) -> float:
    heights = []
    for detection in detections:
        box = detection[0]
        ys = [point[1] for point in box]
        heights.append(max(ys) - min(ys))
    if not heights:
        return 20.0
    heights.sort()
    return heights[len(heights) // 2]


def _group_detections_into_lines(detections: list) -> tuple[list[OcrLine], list[float]]:
    items: list[tuple[float, float, float, float, float, str, float]] = []
    for detection in detections:
        box, text, conf = _parse_detection(detection)
        ys = [point[1] for point in box]
        xs = [point[0] for point in box]
        y_min, y_max = min(ys), max(ys)
        x_min, x_max = min(xs), max(xs)
        cy = sum(ys) / len(ys)
        cx = sum(xs) / len(xs)
        cleaned = text.strip()
        if cleaned:
            items.append((cy, cx, y_min, y_max, x_min, x_max, cleaned, conf))

    if not items:
        return [], []

    items.sort(key=lambda item: (item[0], item[1]))
    y_tolerance = max(_median_box_height(detections) * 0.65, 8.0)

    grouped: list[list[tuple]] = []
    current: list[tuple] = []
    current_y: float | None = None

    for item in items:
        cy = item[0]
        if current_y is None or abs(cy - current_y) <= y_tolerance:
            current.append(item)
            current_y = cy if current_y is None else (current_y + cy) / 2
        else:
            grouped.append(current)
            current = [item]
            current_y = cy
    if current:
        grouped.append(current)

    lines: list[OcrLine] = []
    confidences: list[float] = []
    for row in grouped:
        row.sort(key=lambda item: item[1])
        text = " ".join(item[6] for item in row)
        avg_conf = sum(item[7] for item in row) / len(row)
        y_min = min(item[2] for item in row)
        y_max = max(item[3] for item in row)
        x_min = min(item[4] for item in row)
        x_max = max(item[5] for item in row)
        y_center = (y_min + y_max) / 2
        lines.append(
            OcrLine(
                text=text,
                confidence=avg_conf,
                y_center=y_center,
                x_min=x_min,
                y_min=y_min,
                y_max=y_max,
                x_max=x_max,
            )
        )
        confidences.extend(item[7] for item in row)
    return lines, confidences


class EasyOcrBackend:
    name = "easyocr"

    def warm(self) -> None:
        _get_reader()

    def read(self, image: np.ndarray, *, paragraph: bool = False) -> OcrDocument:
        reader = _get_reader()
        detections = reader.readtext(image, paragraph=paragraph)
        if not detections:
            return OcrDocument(lines=[], full_text="", avg_confidence=0.0)

        if paragraph:
            lines: list[OcrLine] = []
            confidences: list[float] = []
            for detection in detections:
                box, text, conf = _parse_detection(detection)
                cleaned = text.strip()
                if not cleaned:
                    continue
                ys = [point[1] for point in box]
                xs = [point[0] for point in box]
                lines.append(
                    OcrLine(
                        text=cleaned,
                        confidence=conf,
                        y_center=sum(ys) / len(ys),
                        x_min=min(xs),
                        y_min=min(ys),
                        y_max=max(ys),
                        x_max=max(xs),
                    )
                )
                confidences.append(conf)
        else:
            lines, confidences = _group_detections_into_lines(detections)

        if not lines:
            return OcrDocument(lines=[], full_text="", avg_confidence=0.0)

        full_text = "\n".join(line.text for line in lines)
        avg_conf = sum(confidences) / len(confidences)
        return OcrDocument(lines=lines, full_text=full_text, avg_confidence=avg_conf)
