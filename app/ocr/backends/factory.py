from __future__ import annotations

import os

from app.ocr.backends.base import OcrBackend

_backends: dict[str, OcrBackend] = {}


def get_backend_name() -> str:
    return os.getenv("OCR_BACKEND", "vision").strip().lower() or "vision"


def get_rotation_backend_name() -> str:
    """Cheap local backend for rotation/skew sweeps when primary is cloud OCR."""
    primary = get_backend_name()
    if primary == "vision":
        return os.getenv("ROTATION_OCR_BACKEND", "easyocr").strip().lower() or "easyocr"
    return primary


def clear_backend_cache() -> None:
    _backends.clear()


def get_backend(name: str | None = None) -> OcrBackend:
    backend_name = (name or get_backend_name()).strip().lower()
    if backend_name not in _backends:
        if backend_name == "vision":
            from app.ocr.backends.vision import GoogleVisionBackend

            _backends[backend_name] = GoogleVisionBackend()
        elif backend_name == "paddle":
            from app.ocr.backends.paddle_backend import PaddleOcrBackend

            _backends[backend_name] = PaddleOcrBackend()
        elif backend_name == "easyocr":
            from app.ocr.backends.easyocr_backend import EasyOcrBackend

            _backends[backend_name] = EasyOcrBackend()
        else:
            raise ValueError(f"Unknown OCR_BACKEND: {backend_name!r} (use vision, easyocr, or paddle)")
    return _backends[backend_name]


def warm_backend() -> None:
    get_backend().warm()
    rotation_name = get_rotation_backend_name()
    if rotation_name != get_backend_name():
        get_backend(rotation_name).warm()


def get_reader():
    """Legacy hook for EasyOCR warmup in main.py."""
    from app.ocr.backends.easyocr_backend import _get_reader

    return _get_reader()
