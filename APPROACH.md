# Approach

## Problem

TTB compliance agents compare alcohol label artwork to application data. Much of the work is repetitive field matching. This prototype automates OCR extraction, deterministic field parsing, and rule-based comparison for a standalone proof-of-concept.

## Tools

- Python 3.11, FastAPI, Uvicorn
- **Google Cloud Vision** (`DOCUMENT_TEXT_DETECTION`) as the primary OCR backend on Cloud Run
- **EasyOCR** for local dev, rotation/skew sweeps, and offline testing
- Optional **PaddleOCR** backend (pluggable via `OCR_BACKEND`)
- OpenCV for preprocessing, rotation, and skew refinement
- OpenAI, Anthropic, Google Gemini for optional LLM field mapping when `USE_LLM=1`
- Session cookie auth and file/Firestore usage counter
- Docker + GCP Cloud Run deployment

## OCR evolution: EasyOCR to Google Vision

The first iteration used **EasyOCR only**. That was enough to prove the pipeline (rotation sweep → parse → compare) but exposed clear limits on realistic label photos:

| Limitation (EasyOCR-only) | What we observed |
|---------------------------|------------------|
| Paragraph vs word grouping | EasyOCR returns word boxes; grouping into lines was fragile on multi-column and scattered layouts |
| Color and contrast | Gold-on-navy, cream-on-burgundy, and low-contrast stickers often garbled brand or class/type |
| Script and display fonts | Cursive brands and Impact-style display type frequently misread or split across lines |
| Latency on Cloud Run | CPU-bound model load and inference pushed cold starts past acceptable demo limits |
| Cost of rotation sweeps | Running EasyOCR at 0/90/180/270 plus fine skew added 4–8× work per label |

**Google Cloud Vision** addressed the accuracy and latency gaps for the final read:

- Document OCR returns structured blocks/paragraphs with bounding boxes — a better fit for **field-aware assembly** (`app/ocr/field_assembly.py`) that groups brand, class, ABV, net contents, and warning by geometry and content hints
- Higher recall on colored stickers, serif/script fonts, and photocopied proofs in our sample set
- Managed API on Cloud Run: no multi-GB model in memory for the primary pass (~$0.0015 per label at document pricing)

**Hybrid strategy** (current default):

1. **Rotation/skew detection** — EasyOCR (`ROTATION_OCR_BACKEND=easyocr`) sweeps 0/90/180/270° and small skew corrections locally. This avoids billing Vision four times per upload while keeping orientation logic deterministic.
2. **Final OCR read** — Vision runs once on the deskewed image (`OCR_BACKEND=vision`).
3. **Fallback path** — Set `OCR_BACKEND=easyocr` (or `paddle`) for fully offline dev without GCP credentials.

`scripts/benchmark_ocr.py` compares backends against the 31 affix-space samples and writes reports to `data/ocr_benchmark/`.

## Pipeline

1. **Label region (passthrough):** uploads are already cropped to the white application affix rectangle; no TTB form header is present (`app/ocr/label_region.py`).
2. **OCR phase:** preprocess (resize max 1600px, grayscale/contrast), evaluate orientation with the rotation backend, apply cardinal rotation and optional skew, then run the primary backend for the final text layer. Record `detected_rotation_deg`, `skew_correction_deg`, and `was_upright`.
3. **Field assembly:** map OCR lines to structured regions (brand, class/type, ABV, net, warning) using spatial ordering and content heuristics; filter marketing/warehouse/form bleed via shared hints (`app/ocr/noise.py`).
4. **Field map phase (default):** LLM maps OCR lines to structured fields using verbatim label text only (`USE_LLM=1`). Regex parser fallback when `USE_LLM=0` or map validation fails.
5. **Compare phase (fixed rules):** deterministic pass/fail/review against application values using mapped or parsed label reads.

Pass/fail comes from explicit compare rules on label text, not from LLM corrections.

## Realistic sample generation

Early samples were standalone 900×1200 portrait labels (black on white). Reviewers actually upload a **scanned white affix rectangle** from TTB Form F 5100.31 with stickers pasted inside — not the full form with header fields.

`scripts/generate_samples.py` now renders **31 paired samples**:

- **Canvas:** 1800×950 white affix space (no form header)
- **Dual stickers:** brand label (720×520) + separate neck strip (780×220) for the government warning
- **Visible artwork:** cream/white sticker fill, dark border; text rendered on sticker surfaces
- **Rotation:** stickers rotated as a unit (transparent canvas) so border, fill, and text stay aligned
- **Categories:** baseline pass/fail, rotation/skew, script/handwritten fonts, color stickers, wide strip layout, photocopy look, warehouse/DSP/lot noise, marketing clutter, scattered field layouts

Regenerate anytime: `python scripts/generate_samples.py`

## Field rules and assumptions

- **Brand:** normalized case/punctuation comparison (`Stone's Throw` vs `STONE'S THROW` passes); token overlap and garbled-read detection for REVIEW.
- **ABV:** numeric parse with small tolerance.
- **Class/type and net contents:** normalized overlap matching to tolerate OCR noise.
- **Government warning:** exact match after whitespace normalization; `GOVERNMENT WARNING:` must appear in extracted warning text. Incomplete warnings trigger a focused re-read of the neck-strip region.

Primary TTB context: [ttb.gov](https://www.ttb.gov)

## Rotation and skew handling

Labels photographed off-angle are deskewed by:

1. Scoring OCR at 0/90/180/270 with the rotation backend
2. Applying the best cardinal angle
3. Optional fine skew (±15°) when readability improves
4. Running the primary backend on the corrected image

UI reports `detected_rotation_deg`, `skew_correction_deg`, and `was_upright`. Heavily skewed or very low-contrast photos may still require manual REVIEW.

## Marketing and form noise

Non-mandatory text (batch/lot numbers, DSP registry lines, warehouse codes, QR/marketing copy, form bleed phrases) is excluded from brand/class extraction via shared `MARKETING_HINTS` in `app/ocr/noise.py`. This keeps warehouse and marketing-heavy pass samples from polluting field reads.

## Batch behavior

Batch uploads are processed **sequentially, one label at a time**, with terminal-style progress logs. Each label consumes one quota unit.

## Quota and auth

Hosted demo uses:

- Password gate (`REVIEWER_USERNAME` / `REVIEWER_PASSWORD`)
- `MAX_TESTS=10` to limit hosted demo usage and protect API quotas
- Separate **developer** login with unlimited quota for internal testing

Local development can disable quota via `MAX_TESTS=0`.

## Security

- No label image persistence after request completion
- API keys only on server side
- Session secret required for cookie signing
- Cloud Run deploy grants Vision API access to the runtime service account only (no keys in the container for Vision)

## Trade-offs

| Choice | Why | Limit |
|--------|-----|-------|
| Vision primary + EasyOCR rotation | Best accuracy on final read; cheap local orientation sweeps | Requires GCP project; rotation quality still bounded by EasyOCR |
| Field-aware assembly | Uses Vision paragraph boxes and layout hints | Unusual layouts may still need REVIEW |
| Multi-angle + skew OCR | Meets rotated/skewed sticker requirement | Extra latency on first EasyOCR load locally |
| Pluggable backends | EasyOCR/Paddle for offline dev and benchmarks | Three code paths to maintain |
| Selectable LLM | Map-only field ID when enabled | On by default (`USE_LLM=1`); adds latency and key management |
| 10-test cap | Protects prototype resources | Limits reviewer batch size |
| Affix-only uploads | Matches real reviewer workflow | Does not OCR full F 5100.31 form pages |

## Out of scope

- COLA integration
- FedRAMP production controls
- Long-term document retention policies
- Automatic cropping of full form scans (uploads are expected to be pre-cropped affix rectangles)
