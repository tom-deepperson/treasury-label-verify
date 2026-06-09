# Treasury Label Verify

AI-powered alcohol label verification prototype for the Treasury take-home assessment. Compares TTB-style label artwork against application fields using **EasyOCR (rotation-aware)**, a **user-selected LLM extraction phase**, and deterministic **field comparison rules**.

## Features

- Retro dark terminal UI
- Rotation detection during OCR (0/90/180/270 sweep)
- Sequential batch processing (one label at a time)
- Selectable LLM model: `gpt-4.1-mini`, `claude-haiku-4-5`, `gemini-3.5-flash`
- Password-protected reviewer access
- Hosted demo quota: **10 total verifications** (configurable)

## Quick start (local)

Recommended path: `E:\dev\treasury-label-verify` (avoid Google Drive for virtualenvs).

```bash
cd E:\dev\treasury-label-verify
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python scripts/generate_samples.py
uvicorn app.main:app --reload --port 8080
```

Open `http://127.0.0.1:8080/login`

Default local credentials (change in `.env`):

- User: `treasury`
- Pass: value of `REVIEWER_PASSWORD`

Set `MAX_TESTS=0` in `.env` for unlimited local testing.

## Sample tests

Synthetic labels and paired application JSON live in:

- `samples/labels/`
- `samples/applications.json`

Suggested manual checks:

| File | Expected |
|------|----------|
| `old_tom_pass.png` | PASS |
| `stones_throw_brand_case.png` | PASS (brand casing) |
| `wrong_abv_fail.png` | FAIL (ABV) |
| `bad_warning_fail.png` | FAIL (warning) |
| `rotated_pass.png` | PASS or REVIEW with rotation metadata |

## API

- `POST /api/verify` (multipart: image + application fields + `llm_model`)
- `POST /api/batch/stream` (SSE; multipart: `images[]`, `applications_json`, `llm_model`)
- `GET /api/usage`

## Deploy (GCP Cloud Run)

**Important:** project `YOUR_GCP_PROJECT_ID` must be accessed with the **personal** Google account that created it. If `gcloud` is on your business account, see [DEPLOY_AUTH.md](DEPLOY_AUTH.md).

```powershell
cd E:\dev\treasury-label-verify
# After: gcloud auth login (personal) + gcloud config set project YOUR_GCP_PROJECT_ID
.\scripts\deploy.ps1
```

## Reviewer access (Treasury)

Provide reviewers:

1. Deployed URL
2. Username (`REVIEWER_USERNAME`)
3. Password (`REVIEWER_PASSWORD`)

Note the **10-test quota** applies to reviewer logins only.

## Developer access (you)

Set in `.env` / Cloud Run env vars (keep private, not for Treasury):

```env
DEVELOPER_USERNAME=developer
DEVELOPER_PASSWORD=your-strong-dev-password
```

Developer login bypasses the 10-test quota on the live deploy. Header shows `ROLE: developer` and `TESTS: unlimited (developer)`.

## Tests

```bash
pytest tests/test_compare.py -q
pytest tests/test_rotation_ocr.py -q
```

Rotation OCR tests require generated samples and EasyOCR model download.

## Submission form

- Instructions URL: `https://github.com/treasurytakehome-rgb/instructions.git`
- Repo URL: this repository
- Deployed URL: Cloud Run service URL

## Known limitations

- OCR rotation sweep can exceed 5 seconds on CPU for large images
- LLM extraction depends on configured API keys
- Prototype does not integrate with COLA
- Label images are not persisted after processing

See [APPROACH.md](APPROACH.md) for design rationale.
