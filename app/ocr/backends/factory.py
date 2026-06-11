from __future__ import annotations

import os

from app.ocr.backends.base import OcrBackend

_backends: dict[str, OcrBackend] = {}


def get_backend_name() -> str:
    return os.getenv("OCR_BACKEND", "vision").strip().lower() or "vision"


def _running_on_cloud_run() -> bool:
    return bool(os.getenv("K_SERVICE", "").strip())


def skip_rotation_sweeps() -> bool:
    """Single Vision read on Cloud Run; sweeps add cost and false orientation metadata."""
    override = os.getenv("SKIP_ROTATION_SWEEP", "").strip().lower()
    if override in {"1", "true", "yes"}:
        return True
    if override in {"0", "false", "no"}:
        return False
    return _running_on_cloud_run() and get_backend_name() == "vision"


def get_rotation_backend_name() -> str:
    """Backend for rotation/skew sweeps. Local dev defaults to EasyOCR; Cloud Run uses Vision."""
    primary = get_backend_name()
    if primary != "vision":
        return primary
    if _running_on_cloud_run():
        # EasyOCR on Cloud Run CPU can exceed 20s per pass (14+ passes = multi-minute hangs).
        return "vision"
    configured = os.getenv("ROTATION_OCR_BACKEND", "easyocr").strip().lower()
    return configured or "easyocr"


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
    primary_name = get_backend_name()
    get_backend(primary_name).warm()
    rotation_name = get_rotation_backend_name()
    if rotation_name != primary_name and not (_running_on_cloud_run() and rotation_name == "easyocr"):
        get_backend(rotation_name).warm()


def get_reader():
    """Legacy hook for EasyOCR warmup in main.py."""
    from app.ocr.backends.easyocr_backend import _get_reader

    return _get_reader()
