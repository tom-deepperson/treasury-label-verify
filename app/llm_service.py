from __future__ import annotations

import json
import os
import re
from pathlib import Path

from dotenv import dotenv_values

from app.parser import (
    _is_warning_fragment,
    is_garbled_brand_read,
    is_volume_label_read,
    normalize_whitespace,
    parse_fields_from_text,
)
from app.ocr.noise import DISCARD_LINE_EXAMPLES, is_discard_line
from app.schemas import ApplicationFields


DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"
OPENAI_MODEL = "gpt-4.1-mini"
ANTHROPIC_MODEL = "claude-haiku-4-5"

# Backward-compatible alias used in tests and UI defaults.
GEMINI_MODEL = DEFAULT_GEMINI_MODEL

_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _dotenv_path() -> Path:
    return _PROJECT_ROOT / ".env"


def _configured_gemini_model() -> str:
    """Read GEMINI_MODEL from .env when present; ignore stale shell env on local dev."""
    env_path = _dotenv_path()
    if env_path.exists():
        values = dotenv_values(env_path)
        if "GEMINI_MODEL" not in values:
            return ""
        return (values.get("GEMINI_MODEL") or "").strip()
    return os.getenv("GEMINI_MODEL", "").strip()


def gemini_model_name() -> str:
    configured = _configured_gemini_model()
    return configured or DEFAULT_GEMINI_MODEL


def model_provider(model: str) -> str:
    if model.startswith("gemini-"):
        return "gemini"
    if model == OPENAI_MODEL:
        return "openai"
    if model == ANTHROPIC_MODEL:
        return "anthropic"
    raise ValueError(f"Unsupported model: {model!r}")


OCR_PARSER_MODEL = "ocr-parser"


def use_llm() -> bool:
    return os.getenv("USE_LLM", "1").strip().lower() in ("1", "true", "yes")


def available_models() -> list[str]:
    if not use_llm():
        return []
    models: list[str] = []
    if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
        models.append(gemini_model_name())
    if os.getenv("OPENAI_API_KEY"):
        models.append(OPENAI_MODEL)
    if os.getenv("ANTHROPIC_API_KEY"):
        models.append(ANTHROPIC_MODEL)
    return models or [gemini_model_name(), OPENAI_MODEL, ANTHROPIC_MODEL]


def default_model() -> str:
    models = available_models()
    return models[0] if models else gemini_model_name()


def _ocr_lines(ocr_text: str) -> list[str]:
    return [line.strip() for line in ocr_text.splitlines() if line.strip()]


def _numbered_ocr_lines(ocr_text: str) -> str:
    lines = _ocr_lines(ocr_text)
    if not lines:
        return "(empty)"
    return "\n".join(f"{index + 1}. {line}" for index, line in enumerate(lines))


FIELD_BIN_KEYS = (
    "brand_name",
    "class_type",
    "alcohol_content",
    "net_contents",
    "government_warning",
)

FIELD_KEY_LABELS = {
    "brand_name": "Brand Name",
    "class_type": "Class/Type",
    "alcohol_content": "Alcohol Content",
    "net_contents": "Net Contents",
    "government_warning": "Government Warning",
}

FIELD_LABEL_TO_KEY = {label: key for key, label in FIELD_KEY_LABELS.items()}


def _numbered_lines(lines: list[str]) -> str:
    if not lines:
        return "(empty)"
    return "\n".join(f"{index + 1}. {line}" for index, line in enumerate(lines))


def _lines_to_ocr_text(lines: list[str]) -> str:
    return "\n".join(lines)


def _bin_prompt(ocr_text: str, application: ApplicationFields) -> str:
    discard_examples = "\n".join(f"- {example}" for example in DISCARD_LINE_EXAMPLES)
    return f"""Assign OCR line numbers to TTB label fields. Return JSON only with keys:
brand_name, class_type, alcohol_content, net_contents, government_warning, ignore

Each field value must be an array of 1-based line numbers from OCR LINES (e.g. [1] or [5, 6]).
Do NOT copy label text — only return line number arrays.
Use application values ONLY to locate which lines belong to each mandatory field.
Use [] when a mandatory field is not found on the label.

DISCARD / IGNORE (do not assign to any mandatory field):
- Batch/lot numbers, DSP/warehouse/registry codes, URLs, QR/marketing slogans
- Form header bleed, serial numbers, bottler address lines, random OCR garbage
- Put discard line numbers in "ignore" OR simply omit them from every field array
- Unassigned lines are thrown away — you do not need to bin every line

Examples of lines to ignore:
{discard_examples}

Field rules:
- brand_name: distillery/brand lines only — never net contents or alcohol content
- government_warning: every line from GOVERNMENT WARNING through the end of the warning block

APPLICATION (reference only — do not copy into output):
brand_name: {application.brand_name}
class_type: {application.class_type}
alcohol_content: {application.alcohol_content}
net_contents: {application.net_contents}
government_warning: {application.government_warning[:120]}...

OCR LINES:
{_numbered_ocr_lines(ocr_text)}
"""


def _normalize_line_refs(value: object) -> list[int]:
    if value is None or value == "" or value == []:
        return []
    if isinstance(value, bool):
        return []
    if isinstance(value, int):
        return [value] if value > 0 else []
    if isinstance(value, float):
        whole = int(value)
        return [whole] if whole > 0 and whole == value else []
    if isinstance(value, list):
        refs: list[int] = []
        for item in value:
            refs.extend(_normalize_line_refs(item))
        return refs
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.isdigit():
            return [int(stripped)]
        return []
    return []


def _join_binned_lines(lines: list[str], *, field_key: str) -> str:
    if not lines:
        return ""
    if field_key == "government_warning":
        return normalize_whitespace(" ".join(lines))
    if len(lines) == 1:
        return lines[0]
    return normalize_whitespace(" ".join(lines))


def _should_skip_binned_line(line: str, *, field_key: str) -> bool:
    """Drop marketing/garbage lines even if the LLM assigned them to a field."""
    if field_key == "government_warning":
        if re.search(r"GOVERNMENT\s+WARNING", line, re.I):
            return False
        return is_discard_line(line) and not _is_warning_fragment(line)
    if field_key == "brand_name":
        from app.parser import _extract_distillery_brand

        if _extract_distillery_brand(line):
            return False
    if is_discard_line(line):
        return True
    if field_key == "brand_name" and is_garbled_brand_read(line):
        return True
    return False


def _collapsed_match(left: str, right: str) -> bool:
    a = re.sub(r"\s+", "", (left or "").lower())
    b = re.sub(r"\s+", "", (right or "").lower())
    if not a or not b:
        return False
    return a == b or a in b or b in a


def _refs_from_line_content(value: object, lines: list[str], *, hint: str = "") -> list[int]:
    """Map LLM text labels to OCR line numbers when the model copies text instead of indices."""
    candidates: list[str] = []
    if isinstance(value, str):
        stripped = value.strip()
        if stripped and not stripped.isdigit():
            candidates.append(stripped)
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                stripped = item.strip()
                if stripped and not stripped.isdigit():
                    candidates.append(stripped)

    refs: list[int] = []
    seen: set[int] = set()
    for candidate in candidates:
        matched = False
        for index, line in enumerate(lines, start=1):
            if candidate == line or _collapsed_match(candidate, line):
                if index not in seen:
                    refs.append(index)
                    seen.add(index)
                matched = True
                break
        if matched:
            continue
        if hint:
            for index, line in enumerate(lines, start=1):
                if _collapsed_match(hint, line):
                    if index not in seen:
                        refs.append(index)
                        seen.add(index)
                    break
    return refs


def _refs_for_field(
    key: str,
    value: object,
    lines: list[str],
    application: ApplicationFields,
) -> list[int]:
    refs = _normalize_line_refs(value)
    if refs:
        return refs
    hint = getattr(application, key, "")
    refs = _refs_from_line_content(value, lines, hint=hint)
    if refs:
        return refs
    if key == "government_warning":
        for index, line in enumerate(lines, start=1):
            if re.search(r"GOVERNMENT\s+WARNING", line, re.I):
                return [index]
    if key == "alcohol_content":
        from app.parser import extract_abv_value

        for index, line in enumerate(lines, start=1):
            if extract_abv_value(line) is not None:
                return [index]
    if key == "net_contents":
        from app.parser import parse_net_contents_ml

        for index, line in enumerate(lines, start=1):
            if parse_net_contents_ml(line) is not None:
                return [index]
    if key == "brand_name" and application.brand_name:
        return _refs_from_line_content(application.brand_name, lines, hint=application.brand_name)
    if key == "class_type" and application.class_type:
        return _refs_from_line_content(application.class_type, lines, hint=application.class_type)
    return []


def _normalize_bin_payload(data: dict) -> dict:
    aliases = {
        "brand": "brand_name",
        "brandname": "brand_name",
        "class": "class_type",
        "classtype": "class_type",
        "class_type": "class_type",
        "alcohol": "alcohol_content",
        "alcoholcontent": "alcohol_content",
        "abv": "alcohol_content",
        "net": "net_contents",
        "netcontents": "net_contents",
        "volume": "net_contents",
        "warning": "government_warning",
        "governmentwarning": "government_warning",
        "gov_warning": "government_warning",
    }
    normalized: dict = {}
    for key, value in data.items():
        token = re.sub(r"[^a-z0-9_]", "", str(key).lower())
        target = aliases.get(token, token if token in (*FIELD_BIN_KEYS, "ignore") else None)
        if target:
            normalized[target] = value
    return normalized


def _sanitize_bin_refs(
    data: dict,
    line_count: int,
    lines: list[str],
    application: ApplicationFields,
) -> dict[str, list[int]]:
    data = _normalize_bin_payload(data)
    ignore_refs = set(_normalize_line_refs(data.get("ignore")))
    sanitized: dict[str, list[int]] = {}

    for key in FIELD_BIN_KEYS:
        refs: list[int] = []
        seen: set[int] = set()
        for ref in _refs_for_field(key, data.get(key), lines, application):
            if ref in ignore_refs or ref < 1 or ref > line_count or ref in seen:
                continue
            refs.append(ref)
            seen.add(ref)
        sanitized[key] = refs
    return sanitized


def _pick_lines(
    lines: list[str],
    refs: list[int],
    *,
    field_key: str,
) -> list[str]:
    picked: list[str] = []
    for ref in refs:
        if not 1 <= ref <= len(lines):
            continue
        line = lines[ref - 1]
        if _should_skip_binned_line(line, field_key=field_key):
            continue
        if field_key == "brand_name":
            from app.parser import _extract_distillery_brand

            distilled = _extract_distillery_brand(line)
            picked.append(distilled or line)
            continue
        picked.append(line)
    return picked


def fields_from_line_bins(
    data: dict,
    ocr_text: str,
    *,
    application: ApplicationFields | None = None,
) -> ApplicationFields:
    """Build field values by joining OCR lines selected by the LLM bin map."""
    lines = _ocr_lines(ocr_text)
    app = application or ApplicationFields(
        brand_name="",
        class_type="",
        alcohol_content="",
        net_contents="",
        government_warning="",
    )
    refs_by_field = _sanitize_bin_refs(data, len(lines), lines, app)
    fields: dict[str, str] = {}
    for key in FIELD_BIN_KEYS:
        picked = _pick_lines(lines, refs_by_field[key], field_key=key)
        fields[key] = _join_binned_lines(picked, field_key=key)
    return ApplicationFields(**fields)


def _complete_binned_fields(binned: ApplicationFields, ocr_text: str) -> ApplicationFields:
    """Fill any missing mandatory reads from the deterministic OCR parser (same OCR text)."""
    parsed = parse_fields_from_text(ocr_text)
    return ApplicationFields(
        brand_name=binned.brand_name or parsed.brand_name,
        class_type=binned.class_type or parsed.class_type,
        alcohol_content=binned.alcohol_content or parsed.alcohol_content,
        net_contents=binned.net_contents or parsed.net_contents,
        government_warning=binned.government_warning or parsed.government_warning,
    )


def _missing_binned_fields(fields: ApplicationFields) -> list[str]:
    missing: list[str] = []
    for key in FIELD_BIN_KEYS:
        if not getattr(fields, key, "").strip():
            missing.append(key)
    return missing


def _brand_mapping_valid(value: str) -> bool:
    if not value:
        return True
    if is_volume_label_read(value):
        return False
    return not _is_warning_fragment(value)


def validate_binned_fields(fields: ApplicationFields, ocr_text: str) -> bool:
    if not ocr_text.strip():
        return False
    if not _brand_mapping_valid(fields.brand_name):
        return False
    warning = fields.government_warning
    if warning and not re.search(r"GOVERNMENT\s+WARNING", warning, re.I):
        return False
    required = (
        fields.brand_name,
        fields.class_type,
        fields.alcohol_content,
        fields.net_contents,
        fields.government_warning,
    )
    return all(required)


def validate_mapped_fields(fields: ApplicationFields, ocr_text: str) -> bool:
    """Backward-compatible alias: binned fields are always OCR-derived."""
    return validate_binned_fields(fields, ocr_text)


def _parse_json_bins(raw: str) -> dict:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?|```$", "", cleaned, flags=re.MULTILINE).strip()
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("LLM bin response must be a JSON object")
    return data


def _call_openai(prompt: str) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": "Return valid JSON only."},
            {"role": "user", "content": prompt},
        ],
        temperature=0,
    )
    return resp.choices[0].message.content or "{}"


def _call_anthropic(prompt: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=1024,
        temperature=0,
        system="Return valid JSON only.",
        messages=[{"role": "user", "content": prompt}],
    )
    parts = [b.text for b in msg.content if hasattr(b, "text")]
    return "\n".join(parts)


def _call_gemini(prompt: str, model: str) -> str:
    from google import genai

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    client = genai.Client(api_key=api_key)
    resp = client.models.generate_content(model=model, contents=prompt)
    return resp.text or "{}"


def _rescue_prompt(raw_lines: list[str], application: ApplicationFields, target_field_keys: list[str]) -> str:
    discard_examples = "\n".join(f"- {example}" for example in DISCARD_LINE_EXAMPLES)
    target_lines = "\n".join(
        f"- {FIELD_KEY_LABELS[key]}: {getattr(application, key)}"
        for key in target_field_keys
        if key in FIELD_KEY_LABELS
    )
    field_keys = ", ".join(target_field_keys)
    return f"""The deterministic parser could not confidently match these mandatory fields on a TTB alcohol label.
Find the matching OCR lines for ONLY the fields listed below (they failed compare or need review).

Return JSON only with keys: {field_keys}, ignore

Each field value must be an array of 1-based line numbers from OCR LINES (e.g. [1] or [5, 6]).
Do NOT copy label text — only return line number arrays.
Use application values ONLY to locate which lines belong to each field.
Use [] when a field truly cannot be found in OCR.

DISCARD / IGNORE (do not assign to any mandatory field):
- Batch/lot numbers, DSP/warehouse/registry codes, URLs, QR/marketing slogans
- Form header bleed, serial numbers, bottler address lines, random OCR garbage
- Put discard line numbers in "ignore" OR simply omit them from every field array

Examples of lines to ignore:
{discard_examples}

Field rules:
- brand_name: distillery/brand lines only — never net contents, alcohol content, or class/type prefixes like "Small Batch"
- government_warning: every line from GOVERNMENT WARNING through the end of the warning block

FIELDS TO LOCATE (reference only — do not copy into output):
{target_lines}

OCR LINES:
{_numbered_lines(raw_lines)}
"""


def _normalize_rescued_value(key: str, value: str) -> str:
    if not value.strip():
        return ""
    if key == "brand_name":
        from app.parser import _extract_distillery_brand

        distilled = _extract_distillery_brand(value)
        if distilled:
            value = distilled
    return value.strip()


def _validate_rescued_field(key: str, value: str) -> bool:
    value = _normalize_rescued_value(key, value)
    if not value:
        return False
    if key == "brand_name":
        return _brand_mapping_valid(value)
    if key == "government_warning":
        return bool(re.search(r"GOVERNMENT\s+WARNING", value, re.I))
    return True


def _call_llm(prompt: str, model: str) -> str:
    provider = model_provider(model)
    if provider == "openai":
        return _call_openai(prompt)
    if provider == "anthropic":
        return _call_anthropic(prompt)
    return _call_gemini(prompt, model)


def rescue_failed_fields(
    raw_lines: list[str],
    application: ApplicationFields,
    target_field_keys: list[str],
    model: str,
) -> tuple[ApplicationFields | None, str | None]:
    """LLM rescue: map FAIL/REVIEW fields to verbatim OCR line refs. Returns partial reads only."""
    if not target_field_keys or not raw_lines:
        return None, "No fields to rescue or empty OCR"

    prompt = _rescue_prompt(raw_lines, application, target_field_keys)
    try:
        raw = _call_llm(prompt, model)
        bins = _parse_json_bins(raw)
    except Exception as exc:
        return None, str(exc)

    ocr_text = _lines_to_ocr_text(raw_lines)
    rescued_all = fields_from_line_bins(bins, ocr_text, application=application)

    rescued_values: dict[str, str] = {}
    for key in target_field_keys:
        raw_value = getattr(rescued_all, key, "").strip()
        if not _validate_rescued_field(key, raw_value):
            continue
        rescued_values[key] = _normalize_rescued_value(key, raw_value)

    if not rescued_values:
        return None, "LLM rescue found no valid reads for target fields"

    partial = ApplicationFields(
        brand_name=rescued_values.get("brand_name", ""),
        class_type=rescued_values.get("class_type", ""),
        alcohol_content=rescued_values.get("alcohol_content", ""),
        net_contents=rescued_values.get("net_contents", ""),
        government_warning=rescued_values.get("government_warning", ""),
    )
    return partial, None


def extract_fields(
    ocr_text: str,
    model: str,
    *,
    application: ApplicationFields | None = None,
) -> tuple[ApplicationFields, str, str | None]:
    """Parser-only field extraction; LLM rescue runs later on compare FAIL."""
    _ = model, application
    return parse_fields_from_text(ocr_text), "ocr_parser", None


def map_fields_with_llm(
    ocr_text: str, model: str, application: ApplicationFields
) -> ApplicationFields:
    """Backward-compatible alias for tests; bins all fields via LLM."""
    prompt = _bin_prompt(ocr_text, application)
    raw = _call_llm(prompt, model)
    bins = _parse_json_bins(raw)
    mapped = fields_from_line_bins(bins, ocr_text, application=application)
    completed = _complete_binned_fields(mapped, ocr_text)
    if not validate_binned_fields(completed, ocr_text):
        missing = _missing_binned_fields(completed)
        raise ValueError(
            "LLM bin failed validation (missing mandatory field reads"
            + (f": {', '.join(missing)}" if missing else "")
            + ")"
        )
    return completed
