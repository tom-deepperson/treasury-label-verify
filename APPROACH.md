# Approach

## Problem

TTB compliance agents compare alcohol label artwork to application data. Much of the work is repetitive field matching. This prototype automates OCR extraction, LLM structuring, and deterministic comparison for a standalone proof-of-concept.

## Tools

- Python 3.11, FastAPI, Uvicorn
- EasyOCR + OpenCV for rotation-aware text extraction
- OpenAI, Anthropic, Google Gemini for selectable LLM extraction
- Session cookie auth and file/Firestore usage counter
- Docker + GCP Cloud Run deployment

## Pipeline

1. **OCR phase (fixed):** preprocess image, evaluate OCR at 0/90/180/270 degrees, select best score, record rotation metadata.
2. **LLM phase (user-selected model):** convert OCR plain text to structured fields (brand, class/type, ABV, net contents, government warning).
3. **Compare phase (fixed rules):** deterministic pass/fail/review against application values.

LLM assists extraction only. Final compliance status comes from explicit rules.

## Field rules and assumptions

- **Brand:** normalized case/punctuation comparison (`Stone's Throw` vs `STONE'S THROW` passes).
- **ABV:** numeric parse with small tolerance.
- **Class/type and net contents:** normalized overlap matching to tolerate OCR noise.
- **Government warning:** exact match after whitespace normalization; `GOVERNMENT WARNING:` must appear in extracted warning text.

Primary TTB context: [ttb.gov](https://www.ttb.gov)

## Rotation handling

Labels photographed off-angle are deskewed logically by selecting the best OCR rotation. UI reports `detected_rotation_deg` and `was_upright`. Heavily skewed or low-contrast photos may still require manual review.

## Batch behavior

Batch uploads are processed **sequentially, one label at a time**, with terminal-style progress logs. Each label consumes one quota unit.

## Quota and auth

Hosted demo uses:

- Password gate (`REVIEWER_USERNAME` / `REVIEWER_PASSWORD`)
- `MAX_TESTS=10` to prevent production misuse on personal API keys

Local development can disable quota via `MAX_TESTS=0`.

## Security

- No label image persistence after request completion
- API keys only on server side
- Session secret required for cookie signing

## Trade-offs

| Choice | Why | Limit |
|--------|-----|-------|
| EasyOCR vs vision-only | Matches existing OCR pipeline experience; deterministic text layer | Slower on CPU, sensitive to photo quality |
| Multi-angle OCR | Meets rotated label requirement | Up to 4x OCR cost |
| Selectable LLM | Demonstrates multi-provider orchestration | Adds latency and key management |
| 10-test cap | Protects prototype resources | Limits reviewer batch size |

## Out of scope

- COLA integration
- FedRAMP production controls
- Long-term document retention policies

## Author

Thomas S. Tedone
