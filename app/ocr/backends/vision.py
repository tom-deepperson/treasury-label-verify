from __future__ import annotations

import io

import cv2
import numpy as np

from app.ocr.backends.base import OcrBackend, OcrDocument, OcrLine

_client = None


def _get_client():
    global _client
    if _client is None:
        from google.cloud import vision

        _client = vision.ImageAnnotatorClient()
    return _client


def _vertices_to_box(vertices) -> tuple[float, float, float, float]:
    xs = [vertex.x for vertex in vertices]
    ys = [vertex.y for vertex in vertices]
    return min(xs), min(ys), max(xs), max(ys)


def document_from_full_text_annotation(full_text_annotation) -> OcrDocument:
    """Build OcrDocument from Vision API full_text_annotation (paragraph-level lines)."""
    lines: list[OcrLine] = []
    confidences: list[float] = []

    if not full_text_annotation or not full_text_annotation.pages:
        return OcrDocument(lines=[], full_text="", avg_confidence=0.0)

    for page in full_text_annotation.pages:
        for block in page.blocks:
            for paragraph in block.paragraphs:
                words = []
                word_confs: list[float] = []
                x_min = y_min = float("inf")
                x_max = y_max = float("-inf")
                for word in paragraph.words:
                    word_text = "".join(symbol.text for symbol in word.symbols)
                    if word_text:
                        words.append(word_text)
                    if word.confidence:
                        word_confs.append(word.confidence)
                    wx0, wy0, wx1, wy1 = _vertices_to_box(word.bounding_box.vertices)
                    x_min = min(x_min, wx0)
                    y_min = min(y_min, wy0)
                    x_max = max(x_max, wx1)
                    y_max = max(y_max, wy1)
                text = " ".join(words).strip()
                if not text or x_min == float("inf"):
                    continue
                conf = sum(word_confs) / len(word_confs) if word_confs else 0.9
                lines.append(
                    OcrLine(
                        text=text,
                        confidence=conf,
                        y_center=(y_min + y_max) / 2,
                        x_min=x_min,
                        y_min=y_min,
                        y_max=y_max,
                        x_max=x_max,
                    )
                )
                confidences.append(conf)

    lines.sort(key=lambda line: (line.y_center, line.x_min))
    full_text = full_text_annotation.text.strip() if full_text_annotation.text else "\n".join(
        line.text for line in lines
    )
    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
    return OcrDocument(lines=lines, full_text=full_text, avg_confidence=avg_conf)


class GoogleVisionBackend:
    name = "vision"

    def __init__(self, client=None):
        self._client_override = client

    def warm(self) -> None:
        if self._client_override is not None:
            return
        _get_client()

    def read(self, image: np.ndarray, *, paragraph: bool = False) -> OcrDocument:
        from google.cloud import vision

        success, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        if not success:
            raise ValueError("Failed to encode image for Vision API")

        client = self._client_override or _get_client()
        vision_image = vision.Image(content=encoded.tobytes())
        response = client.document_text_detection(image=vision_image)
        if response.error.message:
            raise RuntimeError(response.error.message)

        return document_from_full_text_annotation(response.full_text_annotation)
