from __future__ import annotations

import re

from app.schemas import ApplicationFields


GOV_WARNING_CANONICAL = (
    "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
    "alcoholic beverages during pregnancy because of the risk of birth defects. "
    "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
    "operate machinery, and may cause health problems."
)

_CLASS_LINE_HINTS = ("whiskey", "bourbon", "whisky", "spirit", "vodka", "gin", "rum", "tequila", "wine")
_CLASS_PREFIX_HINTS = (
    "kentucky",
    "straight",
    "blended",
    "single",
    "indiana",
    "tennessee",
    "sour mash",
    "bottled in bond",
)

_CLARIFY_ANNOTATION = re.compile(r"\s*\[script OCR read:\s*.+\]\s*$", re.I)


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def normalize_warning_for_match(text: str) -> str:
    """Fold OCR spacing artifacts in TTB warning text for comparison."""
    text = normalize_whitespace(text).lower()
    text = re.sub(r"\s+:", ":", text)
    text = re.sub(r"\(\s*1\s*\)", "(1)", text)
    text = re.sub(r"\(\s*2\s*\)", "(2)", text)
    text = re.sub(r"\s+([,.])", r"\1", text)
    return text.rstrip(".")


def normalize_brand(text: str) -> str:
    text = normalize_whitespace(text).upper()
    text = re.sub(r"[^A-Z0-9' ]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def ocr_normalize_for_match(text: str) -> str:
    """Fold common OCR confusions before fuzzy brand matching."""
    text = normalize_brand(text)
    for src, dst in (("0", "O"), ("1", "I"), ("5", "S"), ("7", "T"), ("3", "E"), ("8", "B")):
        text = text.replace(src, dst)
    return re.sub(r"[^A-Z]", "", text)


def brand_similarity(app: str, candidate: str) -> float:
    from difflib import SequenceMatcher

    app_n = ocr_normalize_for_match(app)
    cand_n = ocr_normalize_for_match(candidate)
    if not app_n or not cand_n:
        return 0.0
    if app_n == cand_n:
        return 1.0
    return SequenceMatcher(None, app_n, cand_n).ratio()


def word_tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9']+", normalize_whitespace(text).lower()))


def extract_abv_value(text: str) -> float | None:
    if not text:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*%\s*alc", text, re.I)
    if match:
        return float(match.group(1))
    match = re.search(r"(\d+(?:\.\d+)?)\s*%\s*alc\s*n\s*vol", text, re.I)
    if match:
        return float(match.group(1))
    match = re.search(r"(\d+(?:\.\d+)?)\s*proof", text, re.I)
    if match:
        return float(match.group(1)) / 2.0
    match = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    if match:
        return float(match.group(1))
    return None


def parse_net_contents_ml(text: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*m[lL]\b", text or "")
    if not match:
        return None
    return float(match.group(1))


def is_volume_label_read(text: str) -> bool:
    return parse_net_contents_ml(text) is not None


def _is_label_body_line(line: str) -> bool:
    lower = line.lower()
    if "government warning" in lower:
        return True
    if extract_abv_value(line) is not None or parse_net_contents_ml(line) is not None:
        return True
    return any(hint in lower for hint in _CLASS_LINE_HINTS)


def label_brand_from_ocr(ocr_text: str) -> str:
    """Brand text from OCR, merging lines split by decorative or serif layout."""
    lines = [_CLARIFY_ANNOTATION.sub("", line.strip()).strip() for line in ocr_text.splitlines() if line.strip()]
    if not lines:
        return ""

    brand_parts = brand_lines_from_texts(lines)
    if brand_parts:
        return normalize_whitespace(" ".join(brand_parts))

    for line in lines:
        if (
            not _is_marketing_line(line)
            and not _is_label_body_line(line)
            and not _is_class_fragment(line)
            and not _is_warning_fragment(line)
        ):
            return line
    return ""


_CLASS_GEO_WORDS = ("kentucky", "indiana", "tennessee")

from app.ocr.noise import MARKETING_HINTS as _MARKETING_HINTS


def _is_marketing_line(text: str) -> bool:
    lower = normalize_whitespace(text).lower()
    return any(hint in lower for hint in _MARKETING_HINTS)


def _is_class_fragment(text: str) -> bool:
    lower = normalize_whitespace(text).lower()
    if any(hint in lower for hint in _CLASS_LINE_HINTS):
        return False
    tokens = lower.split()
    if not tokens:
        return False
    prefix_words: set[str] = set()
    for hint in _CLASS_PREFIX_HINTS:
        prefix_words.update(hint.split())
    return all(token in _CLASS_GEO_WORDS or token in prefix_words for token in tokens)


def _is_warning_fragment(text: str) -> bool:
    lower = normalize_whitespace(text).lower()
    if "government warning" in lower:
        return True
    if re.match(r"^\(\s*2\s*\)", lower):
        return True
    return any(
        phrase in lower
        for phrase in (
            "surgeon general",
            "birth defects",
            "health problem",
            "impairs your ability",
            "not drink alcoholic",
            "during pregnancy",
            "risk of birth",
            "women should not",
            "according to the",
            "ability to drive",
            "operate machinery",
        )
    )


def brand_lines_from_texts(lines: list[str]) -> list[str]:
    brand_parts: list[str] = []
    for line in lines:
        text = _CLARIFY_ANNOTATION.sub("", line.strip()).strip()
        if not text or _is_marketing_line(text):
            continue
        if _is_warning_fragment(text):
            break
        if _is_label_body_line(text) or _is_class_fragment(text):
            continue
        brand_parts.append(text)
    return brand_parts


def _normalize_class_type_order(text: str) -> str:
    tokens = text.split()
    if not tokens:
        return text
    geo = [token for token in tokens if token.lower() in _CLASS_GEO_WORDS]
    if not geo or tokens[0].lower() in _CLASS_GEO_WORDS:
        return text
    rest = [token for token in tokens if token.lower() not in _CLASS_GEO_WORDS]
    return normalize_whitespace(" ".join(geo + rest))


def _merge_class_type_lines(lines: list[str]) -> str:
    for index, line in enumerate(lines):
        lower = line.lower()
        if not any(hint in lower for hint in _CLASS_LINE_HINTS):
            continue

        parts = [line]
        if index > 0 and not _is_label_body_line(lines[index - 1]):
            prev = lines[index - 1]
            if any(hint in prev.lower() for hint in _CLASS_PREFIX_HINTS):
                parts.insert(0, prev)
        if index + 1 < len(lines):
            nxt = lines[index + 1]
            nxt_lower = nxt.lower()
            if any(hint in nxt_lower for hint in _CLASS_PREFIX_HINTS) and not _is_label_body_line(nxt):
                parts.append(nxt)

        geo = [part for part in parts if any(hint in part.lower() for hint in _CLASS_PREFIX_HINTS)]
        rest = [part for part in parts if part not in geo]
        ordered = geo + rest
        return _normalize_class_type_order(normalize_whitespace(" ".join(dict.fromkeys(ordered))))
    return ""


def label_class_from_ocr(ocr_text: str) -> str:
    lines = [normalize_whitespace(line) for line in ocr_text.splitlines() if line.strip()]
    return _merge_class_type_lines(lines)


def is_garbled_brand_read(text: str) -> bool:
    """True when OCR looks like script/noise, not a clear misspelling on the label."""
    normalized = normalize_brand(text)
    if not normalized:
        return True
    digits = sum(1 for char in normalized if char.isdigit())
    if digits >= 2:
        return True
    if digits == 1 and len(normalized) < 14:
        return True
    raw = normalize_whitespace(text)
    if re.search(r"[^A-Za-z0-9' .-]", raw):
        return True
    core = re.sub(r"[^A-Z]", "", normalized)
    if len(core) >= 8:
        vowels = sum(1 for char in core if char in "AEIOU")
        if vowels / len(core) < 0.15:
            return True
    return False


def is_garbled_ocr_read(text: str) -> bool:
    return is_garbled_brand_read(text)


def is_garbled_prose_read(text: str) -> bool:
    if is_volume_label_read(text):
        return False
    return is_garbled_brand_read(text)


def clarify_brand_in_ocr_text(text: str, application_brand: str) -> str:
    """Annotate garbled script OCR for developers; never mask a clear label typo."""
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return text
    raw = label_brand_from_ocr(text) or lines[0].strip()
    if normalize_brand(raw) == normalize_brand(application_brand):
        return text
    if is_garbled_brand_read(raw) and brand_similarity(application_brand, raw) >= 0.68:
        lines[0] = f"{application_brand}  [script OCR read: {raw}]"
    return "\n".join(lines)


def label_fields_from_ocr(ocr_text: str) -> ApplicationFields:
    return parse_fields_from_text(ocr_text)


def parse_fields_from_text(text: str) -> ApplicationFields:
    lines = [normalize_whitespace(line) for line in text.splitlines() if line.strip()]
    joined = "\n".join(lines)

    brand = label_brand_from_ocr(text) or (lines[0] if lines else "")
    class_type = label_class_from_ocr(text)
    alcohol = ""
    net_contents = ""
    warning = ""

    for line in lines:
        lower = line.lower()
        if not alcohol and ("alc" in lower or "proof" in lower or "%" in line):
            alcohol = line
        if not net_contents and re.search(r"\b\d+\s*m[lL]\b", line):
            net_contents = line

    warning_match = re.search(
        r"(GOVERNMENT\s+WARNING\s*:.*?health problems\.?)",
        joined,
        re.I | re.S,
    )
    if warning_match:
        warning = normalize_whitespace(warning_match.group(1))

    return ApplicationFields(
        brand_name=brand,
        class_type=class_type,
        alcohol_content=alcohol,
        net_contents=net_contents,
        government_warning=warning,
    )
