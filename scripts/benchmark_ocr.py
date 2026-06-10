"""Compare OCR backends on synthetic label samples."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.compare import compare_all, overall_status
from app.ocr.backends.factory import get_backend
from app.ocr.field_assembly import assemble_label_text
from app.ocr.label_region import extract_label_region
from app.parser import (
    extract_abv_value,
    label_brand_from_ocr,
    label_class_from_ocr,
    parse_net_contents_ml,
    word_tokens,
)
from app.schemas import ApplicationFields

SAMPLES = ROOT / "samples" / "labels"
APPLICATIONS = ROOT / "samples" / "applications.json"
REPORT_DIR = ROOT / "data" / "ocr_benchmark"

PASS_SAMPLES = {
    "old_tom_pass.png",
    "stones_throw_brand_case.png",
    "rotated_pass.png",
    "rotated_180_pass.png",
    "script_brand_pass.png",
    "script_class_pass.png",
    "handwritten_style_pass.png",
    "impact_display_pass.png",
    "low_contrast_pass.png",
    "color_navy_gold_pass.png",
    "color_burgundy_cream_pass.png",
    "serif_mixed_pass.png",
    "tiny_warning_pass.png",
    "condensed_pass.png",
    "slight_skew_pass.png",
    "slight_skew_ccw_pass.png",
    "strip_wide_pass.png",
    "photocopy_pass.png",
    "warehouse_noise_pass.png",
    "noisy_marketing_pass.png",
    "noisy_reordered_pass.png",
    "noisy_serif_pass.png",
    "layout_center_brand_pass.png",
    "layout_scattered_pass.png",
    "layout_footer_strip_pass.png",
    "ironwood_chaos_pass.png",
}

FAIL_SAMPLES = {
    "wrong_abv_fail.png",
    "bad_warning_fail.png",
    "wrong_net_fail.png",
    "brand_typo_fail.png",
    "class_typo_fail.png",
    "layout_scattered_net_fail.png",
}


def _load_applications() -> dict[str, dict]:
    apps = json.loads(APPLICATIONS.read_text(encoding="utf-8"))
    return {entry["sample_file"]: entry for entry in apps}


def _warning_ok(text: str) -> bool:
    lower = text.lower()
    return "government warning" in lower and "surgeon general" in lower and "health problem" in lower


def _evaluate(app: dict, ocr_text: str) -> dict:
    application = ApplicationFields(
        brand_name=app["brand_name"],
        class_type=app["class_type"],
        alcohol_content=app["alcohol_content"],
        net_contents=app["net_contents"],
        government_warning=app["government_warning"],
    )
    fields = compare_all(application, application, ocr_text=ocr_text)
    expected_pass = app["sample_file"] in PASS_SAMPLES
    overall = overall_status(fields)
    brand_read = label_brand_from_ocr(ocr_text)
    class_read = label_class_from_ocr(ocr_text)
    return {
        "expected_pass": expected_pass,
        "overall_status": overall,
        "correct_verdict": (overall == "PASS") if expected_pass else (overall == "FAIL"),
        "brand_tokens_match": word_tokens(application.brand_name) == word_tokens(brand_read),
        "class_tokens_match": word_tokens(application.class_type) == word_tokens(class_read),
        "abv_match": extract_abv_value(application.alcohol_content) == extract_abv_value(ocr_text),
        "net_match": parse_net_contents_ml(application.net_contents) == parse_net_contents_ml(ocr_text),
        "warning_ok": _warning_ok(ocr_text),
        "fields": {field.field_name: field.status for field in fields},
    }


def run_backend(backend_name: str, sample_files: list[str]) -> dict:
    os.environ["OCR_BACKEND"] = backend_name
    from app.ocr.backends.factory import clear_backend_cache

    clear_backend_cache()
    backend = get_backend(backend_name)
    apps = _load_applications()
    results: dict[str, dict] = {}
    latencies: list[float] = []

    for filename in sample_files:
        path = SAMPLES / filename
        if not path.exists():
            continue
        image = cv2.imread(str(path))
        image, _region = extract_label_region(image)
        started = time.perf_counter()
        document = backend.read(image)
        assembled = assemble_label_text(document)
        elapsed = time.perf_counter() - started
        latencies.append(elapsed)
        results[filename] = {
            "latency_s": round(elapsed, 3),
            "metrics": _evaluate(apps[filename], assembled),
            "ocr_preview": assembled[:400],
        }

    pass_correct = sum(1 for name, row in results.items() if name in PASS_SAMPLES and row["metrics"]["correct_verdict"])
    fail_correct = sum(1 for name, row in results.items() if name in FAIL_SAMPLES and row["metrics"]["correct_verdict"])
    return {
        "backend": backend_name,
        "samples": len(results),
        "pass_correct": pass_correct,
        "pass_total": len(PASS_SAMPLES & set(results)),
        "fail_correct": fail_correct,
        "fail_total": len(FAIL_SAMPLES & set(results)),
        "median_latency_s": round(sorted(latencies)[len(latencies) // 2], 3) if latencies else 0.0,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark OCR backends on label samples")
    parser.add_argument(
        "--backends",
        default="easyocr,vision",
        help="Comma-separated backends to test (easyocr, vision, paddle)",
    )
    parser.add_argument("--samples", default="", help="Optional comma-separated sample filenames")
    args = parser.parse_args()

    if not APPLICATIONS.exists():
        print("Run python scripts/generate_samples.py first.")
        return 1

    sample_files = [name.strip() for name in args.samples.split(",") if name.strip()] or sorted(
        PASS_SAMPLES | FAIL_SAMPLES
    )
    backends = [name.strip() for name in args.backends.split(",") if name.strip()]

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "backends": [],
    }

    for backend_name in backends:
        print(f"Running {backend_name}...")
        try:
            summary = run_backend(backend_name, sample_files)
            report["backends"].append(summary)
            print(
                f"  pass {summary['pass_correct']}/{summary['pass_total']}  "
                f"fail {summary['fail_correct']}/{summary['fail_total']}  "
                f"median {summary['median_latency_s']}s"
            )
        except Exception as exc:
            print(f"  skipped: {exc}")
            report["backends"].append({"backend": backend_name, "error": str(exc)})

    out_path = REPORT_DIR / f"benchmark_{int(time.time())}.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
