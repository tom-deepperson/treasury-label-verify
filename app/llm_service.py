from __future__ import annotations

import json
import os
import re

from app.parser import (
    _is_warning_fragment,
    is_volume_label_read,
    normalize_whitespace,
    parse_fields_from_text,
)
from app.schemas import ApplicationFields


GEMINI_MODEL = "gemini-3.1-flash-live-preview"

MODEL_OPTIONS = {
    "gpt-4.1-mini": "openai",
    "claude-haiku-4-5": "anthropic",
    GEMINI_MODEL: "gemini",
}

OCR_PARSER_MODEL = "ocr-parser"


def use_llm() -> bool:
    return os.getenv("USE_LLM", "1").strip().lower() in ("1", "true", "yes")


def available_models() -> list[str]:
    if not use_llm():
        return []
    models: list[str] = []
    if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
        models.append(GEMINI_MODEL)
    if os.getenv("OPENAI_API_KEY"):
        models.append("gpt-4.1-mini")
    if os.getenv("ANTHROPIC_API_KEY"):
        models.append("claude-haiku-4-5")
    return models or list(MODEL_OPTIONS.keys())


def default_model() -> str:
    models = available_models()
    return models[0] if models else GEMINI_MODEL


def _numbered_ocr_lines(ocr_text: str) -> str:
    lines = [line.strip() for line in ocr_text.splitlines() if line.strip()]
    if not lines:
        return "(empty)"
    return "\n".join(f"{index + 1}. {line}" for index, line in enumerate(lines))


def _map_prompt(ocr_text: str, application: ApplicationFields) -> str:
    return f"""Map OCR lines to TTB label fields. Return JSON only with keys:
brand_name, class_type, alcohol_content, net_contents, government_warning

Rules:
- Each value MUST be copied verbatim from the OCR text below (same words, typos, casing, spacing)
- Do NOT substitute application wording, fix OCR, or merge lines unless they appear contiguously in OCR
- Use application values ONLY to locate the matching field on the label
- Use empty string if a field is not found on the label
- brand_name must be the distillery/brand name, never net contents (e.g. "700 mL") or alcohol content
- government_warning: contiguous OCR span starting at GOVERNMENT WARNING (keep OCR casing/spacing)

APPLICATION (reference only — do not copy into output):
brand_name: {application.brand_name}
class_type: {application.class_type}
alcohol_content: {application.alcohol_content}
net_contents: {application.net_contents}
government_warning: {application.government_warning[:120]}...

OCR LINES:
{_numbered_ocr_lines(ocr_text)}
"""


def _parse_json_response(raw: str) -> ApplicationFields:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?|```$", "", cleaned, flags=re.MULTILINE).strip()
    data = json.loads(cleaned)
    return ApplicationFields(
        brand_name=str(data.get("brand_name", "")),
        class_type=str(data.get("class_type", "")),
        alcohol_content=str(data.get("alcohol_content", "")),
        net_contents=str(data.get("net_contents", "")),
        government_warning=str(data.get("government_warning", "")),
    )


def _field_in_ocr(value: str, ocr_text: str) -> bool:
    if not value:
        return True
    if value in ocr_text:
        return True
    normalized_value = normalize_whitespace(value)
    normalized_ocr = normalize_whitespace(ocr_text)
    if normalized_value in normalized_ocr:
        return True
    collapsed_value = re.sub(r"\s+", "", normalized_value.lower())
    collapsed_ocr = re.sub(r"\s+", "", normalized_ocr.lower())
    return bool(collapsed_value) and collapsed_value in collapsed_ocr


def _brand_mapping_valid(value: str) -> bool:
    if not value:
        return True
    if is_volume_label_read(value):
        return False
    return not _is_warning_fragment(value)


def validate_mapped_fields(fields: ApplicationFields, ocr_text: str) -> bool:
    if not ocr_text.strip():
        return False
    if not _brand_mapping_valid(fields.brand_name):
        return False
    for value in (
        fields.brand_name,
        fields.class_type,
        fields.alcohol_content,
        fields.net_contents,
        fields.government_warning,
    ):
        if not _field_in_ocr(value, ocr_text):
            return False
    return bool(
        fields.brand_name
        or fields.class_type
        or fields.alcohol_content
        or fields.net_contents
        or fields.government_warning
    )


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


def _call_gemini(prompt: str) -> str:
    from google import genai

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    client = genai.Client(api_key=api_key)
    resp = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
    return resp.text or "{}"


def map_fields_with_llm(
    ocr_text: str, model: str, application: ApplicationFields
) -> ApplicationFields:
    provider = MODEL_OPTIONS.get(model)
    if not provider:
        raise ValueError(f"Unsupported model: {model}")

    prompt = _map_prompt(ocr_text, application)
    if provider == "openai":
        raw = _call_openai(prompt)
    elif provider == "anthropic":
        raw = _call_anthropic(prompt)
    else:
        raw = _call_gemini(prompt)
    mapped = _parse_json_response(raw)
    if not validate_mapped_fields(mapped, ocr_text):
        raise ValueError("LLM map failed verbatim validation")
    return mapped


def extract_fields(
    ocr_text: str,
    model: str,
    *,
    application: ApplicationFields | None = None,
) -> tuple[ApplicationFields, str]:
    if not use_llm():
        return parse_fields_from_text(ocr_text), "ocr_parser"
    if application is None:
        return parse_fields_from_text(ocr_text), "ocr_parser"
    try:
        return map_fields_with_llm(ocr_text, model, application), "llm_map"
    except Exception:
        return parse_fields_from_text(ocr_text), "regex_fallback"
