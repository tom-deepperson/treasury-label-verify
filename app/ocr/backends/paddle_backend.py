from __future__ import annotations

import numpy as np

from app.ocr.backends.base import OcrBackend, OcrDocument, OcrLine

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        from paddleocr import PaddleOCR

        _engine = PaddleOCR(use_angle_cls=True, lang="en", show_log=False, use_gpu=False)
    return _engine


class PaddleOcrBackend:
    name = "paddle"

    def warm(self) -> None:
        _get_engine()

    def read(self, image: np.ndarray, *, paragraph: bool = False) -> OcrDocument:
        engine = _get_engine()
        result = engine.ocr(image, cls=True)
        if not result or not result[0]:
            return OcrDocument(lines=[], full_text="", avg_confidence=0.0)

        lines: list[OcrLine] = []
        confidences: list[float] = []
        for box, (text, conf) in result[0]:
            cleaned = str(text).strip()
            if not cleaned:
                continue
            xs = [point[0] for point in box]
            ys = [point[1] for point in box]
            x_min, x_max = min(xs), max(xs)
            y_min, y_max = min(ys), max(ys)
            lines.append(
                OcrLine(
                    text=cleaned,
                    confidence=float(conf),
                    y_center=(y_min + y_max) / 2,
                    x_min=x_min,
                    y_min=y_min,
                    y_max=y_max,
                    x_max=x_max,
                )
            )
            confidences.append(float(conf))

        lines.sort(key=lambda line: (line.y_center, line.x_min))
        full_text = "\n".join(line.text for line in lines)
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
        return OcrDocument(lines=lines, full_text=full_text, avg_confidence=avg_conf)
