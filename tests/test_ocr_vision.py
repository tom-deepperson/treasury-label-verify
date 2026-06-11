from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.ocr.backends.vision import GoogleVisionBackend, document_from_full_text_annotation
from app.ocr.field_assembly import assemble_label_text


def _vertex(x, y):
    return SimpleNamespace(x=x, y=y)


def _word(text: str, x0: int, y0: int, x1: int, y1: int):
    return SimpleNamespace(
        symbols=[SimpleNamespace(text=char) for char in text.replace(" ", "")],
        confidence=0.96,
        bounding_box=SimpleNamespace(vertices=[_vertex(x0, y0), _vertex(x1, y0), _vertex(x1, y1), _vertex(x0, y1)]),
    )


def _make_annotation():
    return SimpleNamespace(
        text=(
            "OLD TOM DISTILLERY\n"
            "Kentucky Straight Bourbon Whiskey\n"
            "45% Alc./Vol. (90 Proof)\n"
            "750 mL\n"
            "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink alcoholic beverages "
            "during pregnancy because of the risk of birth defects. (2) Consumption of alcoholic beverages impairs "
            "your ability to drive a car or operate machinery, and may cause health problems."
        ),
        pages=[
            SimpleNamespace(
                blocks=[
                    SimpleNamespace(paragraphs=[SimpleNamespace(words=[_word("OLD", 10, 10, 50, 50), _word("TOM", 60, 10, 100, 50), _word("DISTILLERY", 110, 10, 220, 50)])]),
                    SimpleNamespace(
                        paragraphs=[
                            SimpleNamespace(
                                words=[
                                    _word("Kentucky", 10, 70, 100, 100),
                                    _word("Straight", 110, 70, 200, 100),
                                    _word("Bourbon", 210, 70, 290, 100),
                                    _word("Whiskey", 300, 70, 390, 100),
                                ]
                            )
                        ]
                    ),
                    SimpleNamespace(paragraphs=[SimpleNamespace(words=[_word("45%", 10, 130, 60, 160)])]),
                    SimpleNamespace(paragraphs=[SimpleNamespace(words=[_word("750", 10, 190, 60, 220)])]),
                    SimpleNamespace(
                        paragraphs=[
                            SimpleNamespace(
                                words=[_word("GOVERNMENT", 10, 260, 140, 290), _word("WARNING:", 150, 260, 250, 290)]
                            )
                        ]
                    ),
                ]
            )
        ],
    )


def test_google_vision_backend_uses_document_text_detection():
    annotation = _make_annotation()
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.error.message = ""
    mock_response.full_text_annotation = annotation
    mock_client.document_text_detection.return_value = mock_response

    backend = GoogleVisionBackend(client=mock_client)
    image = np.zeros((200, 200, 3), dtype=np.uint8)
    document = backend.read(image)
    assert document.full_text
    mock_client.document_text_detection.assert_called_once()
    assembled = assemble_label_text(document)
    assert "OLD TOM DISTILLERY" in assembled


def test_document_from_full_text_annotation_handles_empty():
    empty = SimpleNamespace(text="", pages=[])
    document = document_from_full_text_annotation(empty)
    assert document.lines == []
    assert document.full_text == ""


def test_rotation_backend_uses_vision_on_cloud_run(monkeypatch):
    from app.ocr.backends.factory import clear_backend_cache, get_rotation_backend_name

    monkeypatch.setenv("K_SERVICE", "treasury-label-verify")
    monkeypatch.setenv("OCR_BACKEND", "vision")
    monkeypatch.setenv("ROTATION_OCR_BACKEND", "easyocr")
    clear_backend_cache()
    assert get_rotation_backend_name() == "vision"


def test_rotation_backend_respects_easyocr_locally(monkeypatch):
    from app.ocr.backends.factory import clear_backend_cache, get_rotation_backend_name

    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.setenv("OCR_BACKEND", "vision")
    monkeypatch.setenv("ROTATION_OCR_BACKEND", "easyocr")
    clear_backend_cache()
    assert get_rotation_backend_name() == "easyocr"


def test_skip_rotation_sweeps_on_cloud_run(monkeypatch):
    from app.ocr.backends.factory import clear_backend_cache, skip_rotation_sweeps

    monkeypatch.setenv("K_SERVICE", "treasury-label-verify")
    monkeypatch.setenv("OCR_BACKEND", "vision")
    monkeypatch.delenv("SKIP_ROTATION_SWEEP", raising=False)
    clear_backend_cache()
    assert skip_rotation_sweeps() is True


def test_skip_rotation_sweeps_off_locally(monkeypatch):
    from app.ocr.backends.factory import clear_backend_cache, skip_rotation_sweeps

    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.setenv("OCR_BACKEND", "vision")
    monkeypatch.delenv("SKIP_ROTATION_SWEEP", raising=False)
    clear_backend_cache()
    assert skip_rotation_sweeps() is False


def test_vision_direct_path_avoids_rotation_sweeps(monkeypatch):
    from pathlib import Path
    from unittest.mock import patch

    from app.ocr.backends.factory import clear_backend_cache
    from app.ocr_service import extract_text_with_rotation

    sample = Path(__file__).resolve().parents[1] / "samples" / "labels" / "old_tom_pass.png"
    if not sample.exists():
        pytest.skip("samples not generated")

    monkeypatch.setenv("K_SERVICE", "treasury-label-verify")
    monkeypatch.setenv("OCR_BACKEND", "vision")
    clear_backend_cache()

    fake_document = document_from_full_text_annotation(_make_annotation())
    with patch("app.ocr_service._best_cardinal_rotation") as mock_cardinal:
        with patch("app.ocr_service._run_ocr_with_document") as mock_read:
            mock_read.return_value = (fake_document.full_text, fake_document.avg_confidence, fake_document)
            result = extract_text_with_rotation(sample.read_bytes())

    mock_cardinal.assert_not_called()
    assert result.detected_rotation_deg == 0
    assert result.skew_correction_deg == 0
    assert result.was_upright is True
    assert result.per_sticker is False
    assert "OLD TOM" in result.text
