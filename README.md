# Treasury Label Verify

Automated verification of alcohol label artwork for the **AFFIX COMPLETE SET OF LABELS BELOW** section on [TTB Form F 5100.31](https://www.ttb.gov/forms/form-f510031-application-for-and-certification-exemption-of-label-bottle-approval). Uploads are cropped photos of that affix area (brand and neck stickers on the white rectangle); the tool compares OCR reads against application field data using **Google Cloud Vision OCR** (with field-aware assembly), a deterministic **OCR parser**, optional **LLM rescue on compare FAIL**, and **rule-based comparison**.

## Features

- Retro dark terminal UI with rotation/skew metadata in results
- Pluggable OCR backends (`vision`, `easyocr`, `paddle`) via `app/ocr/backends/`
- **Google Cloud Vision** document OCR on Cloud Run; **EasyOCR** for local dev and rotation/skew sweeps
- Field-aware text assembly (brand, class, ABV, net, warning) from OCR line geometry
- Marketing/warehouse/form-noise filtering so batch numbers and DSP lines do not pollute reads
- Rotation detection (0/90/180/270) and fine skew correction before the final Vision read
- **32 synthetic affix-space samples** — dual stickers (brand + neck warning) on white canvas
- Sequential batch processing (one label at a time)
- OCR parser always runs first; optional **LLM rescue on compare FAIL or REVIEW** when `USE_LLM=1` (assigns OCR line numbers to unclear/failed fields only; text still comes from OCR, not the model)
- Password-protected reviewer access; developer login with unlimited quota
- Hosted demo quota: **10 total verifications** (configurable)
- Dev scripts (`scripts/dev.bat`, `dev.ps1`, `dev.sh`) for one-command local setup
- OCR benchmark script to compare backends on the sample set

## Architecture

```
Upload (affix rectangle PNG/JPG)
  → preprocess + resize
  → rotation/skew sweep (EasyOCR by default)
  → final OCR read (Vision on Cloud Run)
  → field assembly + noise filter
  → OCR parser  →  compare rules  →  PASS / FAIL / REVIEW
                                    ↳ LLM rescue on FAIL or REVIEW (USE_LLM=1)
```

See [APPROACH.md](APPROACH.md) for the EasyOCR → Vision evolution, sample-generation rationale, and trade-offs.

## Quick start (local)

**Recommended:** develop and test locally, then deploy to Cloud Run only when ready (~12 min per deploy).

```cmd
cd treasury-label-verify
scripts\dev.bat
```

PowerShell: `.\scripts\dev.ps1`  
macOS/Linux: `./scripts/dev.sh`

The dev script creates `.venv` and `.env` if missing, generates samples if needed, and starts the server with hot reload.

Manual setup:

```bash
git clone <repository-url>
cd treasury-label-verify
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
# Windows:  copy .env.example .env
# macOS/Linux:  cp .env.example .env
python scripts/generate_samples.py
uvicorn app.main:app --reload --port 8080
```

Open `http://127.0.0.1:8080/login`

Local credentials (from `.env`):

- **Developer** (`DEVELOPER_USERNAME` / `DEVELOPER_PASSWORD`) — unlimited tests when `MAX_TESTS=0`
- **Reviewer** (`REVIEWER_USERNAME` / `REVIEWER_PASSWORD`) — same as hosted demo

First label verify may take 30–60s while OCR backends initialize. On Cloud Run, Vision API calls use the runtime service account (~$0.0015 per label).

### Google Cloud Vision (local dev)

Vision is the default backend (`OCR_BACKEND=vision`). Authenticate once:

```bash
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
```

Ensure the Cloud Vision API is enabled and your account can call it. For offline/local-only dev without GCP credentials, set `OCR_BACKEND=easyocr` in `.env`.

### Local workflow

1. `scripts\dev.bat` — start server
2. Load a sample → **VERIFY LABEL** — iterate on UI/OCR/compare changes (auto-reload on save)
3. `pytest tests/ -q` — unit tests (no API keys needed for compare/parser tests)
4. When satisfied: `scripts\deploy.bat` — push to Cloud Run

## Sample tests

**32** synthetic affix-space PNGs and paired application JSON:

- `samples/labels/` — rendered by `scripts/generate_samples.py`
- `samples/applications.json` — expected field values per sample

Each image is a **white application affix rectangle** (1800×950, no TTB form header) with **visible stickers** pasted inside: a brand label (mandatory fields) plus a separate **neck strip** for the government warning. Stickers can be rotated, skewed, colored, or noisy.

Suggested manual checks:

| File | Expected |
|------|----------|
| `old_tom_pass.png` | PASS (brand sticker + neck warning sticker) |
| `stones_throw_brand_case.png` | PASS (brand casing) |
| `wrong_abv_fail.png` | FAIL (ABV) |
| `bad_warning_fail.png` | FAIL (warning) |
| `rotated_pass.png` | PASS (brand sticker at 90°, neck strip upright; per-sticker correction) |
| `rotated_180_pass.png` | PASS (brand at 180°, neck strip upright; per-sticker correction) |
| `slight_skew_pass.png` | PASS (8° tilted sticker) |
| `slight_skew_ccw_pass.png` | PASS (−12° tilted sticker) |
| `wrong_net_fail.png` | FAIL (net contents) |
| `brand_typo_fail.png` | FAIL (brand name typo) |
| `class_typo_fail.png` | FAIL (class/type typo: Staight) |
| `script_brand_pass.png` | PASS (script/cursive brand) |
| `script_class_pass.png` | PASS or REVIEW (script class/type) |
| `handwritten_style_pass.png` | PASS or REVIEW (handwritten-style font) |
| `color_navy_gold_pass.png` | PASS or REVIEW (gold on navy sticker) |
| `color_burgundy_cream_pass.png` | PASS or REVIEW (cream on burgundy sticker) |
| `strip_wide_pass.png` | PASS (short/wide strip sticker) |
| `photocopy_pass.png` | PASS or REVIEW (photocopied proof look) |
| `warehouse_noise_pass.png` | PASS (warehouse/DSP/lot noise ignored) |
| `noisy_marketing_pass.png` | PASS (extra marketing lines) |
| `noisy_reordered_pass.png` | PASS (marketing + reordered lines) |
| `noisy_serif_pass.png` | PASS (serif + marketing noise) |
| `layout_center_brand_pass.png` | PASS (centered brand, scattered fields) |
| `layout_scattered_pass.png` | PASS (ABV/net corners, brand center) |
| `layout_footer_strip_pass.png` | PASS (mandatory strip above warning) |
| `layout_scattered_net_fail.png` | FAIL (net contents in corner) |
| `ironwood_chaos_pass.png` | PASS (teal/coral sticker, heavy warehouse/form/marketing noise) |

Regenerate synthetic samples anytime:

```bash
python scripts/generate_samples.py
```

## API

- `POST /api/verify` (multipart: image + application fields + `llm_model`)
- `POST /api/batch/stream` (SSE; multipart: `images[]`, `applications_json`, `llm_model`)
- `GET /api/usage`

## Deploy (GCP Cloud Run)

**Important:** set `GOOGLE_CLOUD_PROJECT`, `SESSION_SECRET`, reviewer/developer passwords, and at least one LLM API key in `.env`. Ensure `gcloud` is authenticated with an account that can deploy to that project. If you use multiple Google accounts, see [DEPLOY_AUTH.md](DEPLOY_AUTH.md).

The deploy script enables Cloud Vision, grants the Cloud Run runtime service account Vision access, and sets:

| Cloud Run env | Value |
|---------------|-------|
| `OCR_BACKEND` | `vision` |
| Rotation sweeps | off (single Vision read; `K_SERVICE` auto) |
| `USE_LLM` | `1` |
| `MAX_TESTS` | `50` |
| `WARM_OCR` | `1` |
| `USAGE_STORE` | `file` |

**Windows:**

```powershell
.\scripts\deploy.ps1
```

```cmd
scripts\deploy.bat
```

**macOS/Linux:** configure env vars from `.env`, then run `./scripts/deploy_cloud_run.sh` (see [DEPLOY_AUTH.md](DEPLOY_AUTH.md)).

## Reviewer access

For the hosted demo, provide:

1. Deployed URL
2. Username (`REVIEWER_USERNAME`)
3. Password (`REVIEWER_PASSWORD`)

The **50-test quota** applies to reviewer logins.

## Configuration

Copy `.env.example` to `.env` and set API keys, session secret, and login credentials. See `.env.example` for all options.

OCR-related settings:

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_LLM` | `1` | `0` = OCR parser only; `1` = LLM rescue on compare FAIL or REVIEW |
| `OCR_BACKEND` | `vision` | Primary OCR engine: `vision`, `easyocr`, or `paddle` |
| `ROTATION_OCR_BACKEND` | `easyocr` | Local backend for rotation/skew sweeps when primary is `vision` |
| `SKIP_ROTATION_SWEEP` | auto on Cloud Run | `1` = single Vision read, no orientation metadata; `0` = force sweeps |
| `WARM_OCR` | `1` on deploy | Pre-load OCR backends at startup |

Benchmark OCR backends against samples:

```bash
python scripts/generate_samples.py
python scripts/benchmark_ocr.py --backends easyocr,vision
```

Reports are written to `data/ocr_benchmark/`.

## Tests

```bash
pytest tests/ -q
```

Key suites:

| Test file | Covers |
|-----------|--------|
| `test_compare.py` | Brand/class/ABV/net/warning rules, REVIEW paths |
| `test_field_assembly.py` | Vision line grouping → structured fields |
| `test_ocr_vision.py` | Vision backend document parsing (mocked) |
| `test_rotation_ocr.py` | Rotation/skew on affix samples |
| `test_form_samples.py` | Affix baseline samples |
| `test_layout_scattered_brand.py` | Scattered layout brand extraction |
| `test_ocr_benchmark.py` | Benchmark script smoke test |

Rotation OCR tests use `OCR_BACKEND=easyocr` by default. Set `OCR_INTEGRATION=1` to run them against your configured primary backend.

## Submission form

- Instructions URL: `https://github.com/treasurytakehome-rgb/instructions.git`
- Repo URL: this repository
- Deployed URL: Cloud Run service URL

## Known limitations

- Vision OCR requires GCP credentials locally (`gcloud auth application-default login`) or the Cloud Run service account on deploy
- Cloud Run uses a single Vision read (rotation sweeps off). Local dev uses EasyOCR sweeps unless `SKIP_ROTATION_SWEEP=1`
- Color stickers and script fonts may REVIEW on EasyOCR-only local runs; Vision on Cloud Run is the intended production path
- Uploads must be pre-cropped affix rectangles (not full F 5100.31 form scans)
- LLM rescue runs when compare FAILs or flags REVIEW (`USE_LLM=1`); set `USE_LLM=0` for parser-only offline dev
- Prototype does not integrate with COLA
- Label images are not persisted after processing
- Hosted quota counter resets on redeploy when `USAGE_STORE=file`

See [APPROACH.md](APPROACH.md) for design rationale and the EasyOCR → Vision learning path.

## License

All rights reserved. Source is published for evaluation and portfolio review only; no license to use, copy, modify, or distribute. See [LICENSE](LICENSE).
