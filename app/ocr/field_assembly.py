from __future__ import annotations

import re

from app.ocr.backends.base import OcrDocument, OcrLine
from app.parser import (
    _is_class_fragment,
    _is_warning_fragment,
    brand_lines_from_texts,
    extract_abv_value,
    label_class_from_ocr,
    net_contents_read_from_text,
    normalize_whitespace,
    parse_net_contents_ml,
    trim_warning_text,
)

_CLASS_LINE_HINTS = ("whiskey", "bourbon", "whisky", "spirit", "vodka", "gin", "rum", "tequila", "wine")
_CLASS_PREFIX_HINTS = ("kentucky", "straight", "blended", "single", "indiana", "tennessee", "sour mash", "bottled in bond")
_WARNING_END_PHRASES = ("health problems", "health problem", "may cause health")
from app.ocr.noise import MARKETING_HINTS as _MARKETING_HINTS


def _is_label_body_line(line: str) -> bool:
    lower = line.lower()
    if "government warning" in lower:
        return True
    if extract_abv_value(line) is not None or parse_net_contents_ml(line) is not None:
        return True
    return any(hint in lower for hint in _CLASS_LINE_HINTS)


def _is_marketing_line(line: str) -> bool:
    lower = line.lower()
    return any(hint in lower for hint in _MARKETING_HINTS)


def _line_gap(prev: OcrLine | None, current: OcrLine) -> float:
    if prev is None:
        return 0.0
    return max(0.0, current.y_min - prev.y_max)


def _sorted_lines(document: OcrDocument) -> list[OcrLine]:
    return sorted(document.lines, key=lambda line: (line.y_center, line.x_min))


def raw_lines_from_document(document: OcrDocument) -> list[str]:
    """Unparsed OCR lines in spatial order, before assembly filtering."""
    return [
        normalize_whitespace(line.text)
        for line in _sorted_lines(document)
        if line.text.strip()
    ]


def _extract_brand_lines(lines: list[OcrLine]) -> list[str]:
    texts = brand_lines_from_texts([line.text for line in lines])
    if texts:
        return texts
    for line in lines:
        text = line.text.strip()
        if not text or _is_marketing_line(text):
            continue
        if _is_label_body_line(text) or _is_class_fragment(text) or _is_warning_fragment(text):
            continue
        return [text]
    return []


def _extract_class_lines(lines: list[OcrLine]) -> list[str]:
    texts = [line.text.strip() for line in lines if line.text.strip()]
    merged = label_class_from_ocr("\n".join(texts))
    return [merged] if merged else []


def _extract_abv_line(lines: list[OcrLine]) -> str:
    for line in lines:
        if extract_abv_value(line.text) is not None:
            return line.text.strip()
    return ""


def _extract_net_line(lines: list[OcrLine]) -> str:
    for line in lines:
        snippet = net_contents_read_from_text(line.text)
        if snippet:
            return snippet
    return ""


def _extract_warning_block(lines: list[OcrLine], *, max_gap: float = 28.0) -> str:
    start_index = None
    for index, line in enumerate(lines):
        if re.search(r"GOVERNMENT\s+WARNING", line.text, re.I):
            start_index = index
            break
    if start_index is None:
        return ""

    parts = [lines[start_index].text.strip()]
    prev = lines[start_index]
    for line in lines[start_index + 1 :]:
        gap = _line_gap(prev, line)
        lower = line.text.lower()
        if gap > max_gap and parts:
            break
        if _is_marketing_line(line.text) and "warning" not in lower:
            continue
        parts.append(line.text.strip())
        prev = line
        joined = normalize_whitespace(" ".join(parts))
        if any(phrase in joined.lower() for phrase in _WARNING_END_PHRASES):
            break

    return trim_warning_text(normalize_whitespace(" ".join(parts)))


def _extract_header_lines(lines: list[OcrLine], warning_text: str) -> list[str]:
    """Mandatory TTB header fields excluding marketing noise and warning tail."""
    brand = normalize_whitespace(" ".join(_extract_brand_lines(lines)))
    class_type = " ".join(_extract_class_lines(lines))
    abv = _extract_abv_line(lines)
    net = _extract_net_line(lines)

    header: list[str] = []
    if brand:
        header.append(brand)
    if class_type:
        header.append(class_type)
    if abv:
        header.append(abv)
    if net:
        header.append(net)
    return header


def assemble_label_text(document: OcrDocument) -> str:
    """Build structured OCR text for parser/compare from OCR lines with coordinates."""
    if not document.lines:
        return document.full_text or ""

    lines = _sorted_lines(document)
    header = _extract_header_lines(lines, "")
    warning = _extract_warning_block(lines)

    if not header and not warning:
        return document.full_text or "\n".join(line.text for line in lines)

    parts = header[:]
    if warning:
        parts.append(warning)
    return "\n".join(part for part in parts if part)


def assemble_warning_from_region(document: OcrDocument) -> str:
    """Warning-only read for second-pass merge when full assembly is incomplete."""
    lines = _sorted_lines(document)
    return _extract_warning_block(lines, max_gap=40.0)
