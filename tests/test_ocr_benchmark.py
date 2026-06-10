import json
import os
import time
from pathlib import Path

import pytest

from app.compare import compare_all, overall_status
from app.ocr.backends.factory import get_backend
from app.ocr.field_assembly import assemble_label_text
from app.parser import (
    extract_abv_value,
    label_brand_from_ocr,
    label_class_from_ocr,
    parse_net_contents_ml,
    word_tokens,
)
from app.schemas import ApplicationFields


ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples" / "labels"
APPLICATIONS = ROOT / "samples" / "applications.json"
REPORT_DIR = ROOT / "data" / "ocr_benchmark"


def _load_applications() -> dict[str, dict]:
    if not APPLICATIONS.exists():
        return {}
    apps = json.loads(APPLICATIONS.read_text(encoding="utf-8"))
    return {entry["sample_file"]: entry for entry in apps}


def _warning_ok(text: str) -> bool:
    lower = text.lower()
    return "government warning" in lower and "surgeon general" in lower and "health problem" in lower


def _evaluate_sample(app: dict, ocr_text: str) -> dict:
    application = ApplicationFields(
        brand_name=app["brand_name"],
        class_type=app["class_type"],
        alcohol_content=app["alcohol_content"],
        net_contents=app["net_contents"],
        government_warning=app["government_warning"],
    )
    fields = compare_all(application, application, ocr_text=ocr_text)
    status = overall_status(fields)
    brand_read = label_brand_from_ocr(ocr_text)
    class_read = label_class_from_ocr(ocr_text)
    return {
        "overall_status": status,
        "brand_tokens_match": word_tokens(application.brand_name) == word_tokens(brand_read),
        "class_tokens_match": word_tokens(application.class_type) == word_tokens(class_read),
        "abv_match": extract_abv_value(application.alcohol_content) == extract_abv_value(ocr_text),
        "net_match": parse_net_contents_ml(application.net_contents) == parse_net_contents_ml(ocr_text),
        "warning_ok": _warning_ok(ocr_text),
        "field_statuses": {field.field_name: field.status for field in fields},
    }


@pytest.mark.parametrize("backend_name", ["easyocr"])
def test_benchmark_report_runs_for_local_backend(backend_name, monkeypatch):
    monkeypatch.setenv("OCR_BACKEND", backend_name)
    if not SAMPLES.exists() or not (SAMPLES / "old_tom_pass.png").exists():
        pytest.skip("samples not generated")

    import cv2

    backend = get_backend(backend_name)
    app_map = _load_applications()
    sample_name = "old_tom_pass.png"
    image = cv2.imread(str(SAMPLES / sample_name))
    document = backend.read(image)
    assembled = assemble_label_text(document)
    metrics = _evaluate_sample(app_map[sample_name], assembled)
    assert metrics["brand_tokens_match"] is True


def test_benchmark_script_importable():
    import scripts.benchmark_ocr as benchmark

    assert callable(benchmark.main)
