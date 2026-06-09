from __future__ import annotations

import re

from app.schemas import ApplicationFields


GOV_WARNING_CANONICAL = (
    "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
    "alcoholic beverages during pregnancy because of the risk of birth defects. "
    "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
    "operate machinery, and may cause health problems."
)


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def normalize_brand(text: str) -> str:
    text = normalize_whitespace(text).upper()
    text = re.sub(r"[^A-Z0-9' ]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_abv_value(text: str) -> float | None:
    if not text:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*%\s*alc", text, re.I)
    if match:
        return float(match.group(1))
    match = re.search(r"(\d+(?:\.\d+)?)\s*proof", text, re.I)
    if match:
        return float(match.group(1)) / 2.0
    match = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    if match:
        return float(match.group(1))
    return None


def parse_fields_from_text(text: str) -> ApplicationFields:
    lines = [normalize_whitespace(line) for line in text.splitlines() if line.strip()]
    joined = "\n".join(lines)

    brand = lines[0] if lines else ""
    class_type = ""
    alcohol = ""
    net_contents = ""
    warning = ""

    for line in lines:
        lower = line.lower()
        if not class_type and ("whiskey" in lower or "bourbon" in lower or "spirit" in lower):
            class_type = line
        if not alcohol and ("alc" in lower or "proof" in lower or "%" in line):
            alcohol = line
        if not net_contents and re.search(r"\b\d+\s*m[lL]\b", line):
            net_contents = line

    warning_match = re.search(
        r"(GOVERNMENT WARNING:.*?(?:health problems\.|machinery, and may cause health problems\.))",
        joined,
        re.I | re.S,
    )
    if warning_match:
        warning = normalize_whitespace(warning_match.group(1))
        if warning.upper().startswith("GOVERNMENT WARNING"):
            warning = "GOVERNMENT WARNING:" + warning.split(":", 1)[1].strip()

    return ApplicationFields(
        brand_name=brand,
        class_type=class_type,
        alcohol_content=alcohol,
        net_contents=net_contents,
        government_warning=warning,
    )
