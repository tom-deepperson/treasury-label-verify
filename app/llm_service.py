from __future__ import annotations

import json
import os
import re

from app.parser import parse_fields_from_text
from app.schemas import ApplicationFields


MODEL_OPTIONS = {
    "gpt-4.1-mini": "openai",
    "claude-haiku-4-5": "anthropic",
    "gemini-3.5-flash": "gemini",
}


def available_models() -> list[str]:
    models = []
    if os.getenv("OPENAI_API_KEY"):
        models.append("gpt-4.1-mini")
    if os.getenv("ANTHROPIC_API_KEY"):
        models.append("claude-haiku-4-5")
    if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
        models.append("gemini-3.5-flash")
    return models or list(MODEL_OPTIONS.keys())


def _prompt(ocr_text: str) -> str:
    return f"""Extract alcohol label fields from OCR text. Return JSON only with keys:
brand_name, class_type, alcohol_content, net_contents, government_warning

OCR TEXT:
{ocr_text}
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
    resp = client.models.generate_content(model="gemini-3.5-flash", contents=prompt)
    return resp.text or "{}"


def extract_fields_with_llm(ocr_text: str, model: str) -> ApplicationFields:
    provider = MODEL_OPTIONS.get(model)
    if not provider:
        raise ValueError(f"Unsupported model: {model}")

    prompt = _prompt(ocr_text)
    if provider == "openai":
        raw = _call_openai(prompt)
    elif provider == "anthropic":
        raw = _call_anthropic(prompt)
    else:
        raw = _call_gemini(prompt)
    return _parse_json_response(raw)


def extract_fields(ocr_text: str, model: str) -> tuple[ApplicationFields, str]:
    try:
        return extract_fields_with_llm(ocr_text, model), "llm"
    except Exception:
        return parse_fields_from_text(ocr_text), "regex_fallback"
