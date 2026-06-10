"""Non-mandatory label and form text patterns to exclude from field extraction."""

import re

MARKETING_HINTS = (
    "batch no",
    "lot no",
    "qr code",
    "scan here",
    "www.",
    "http",
    "bottled by",
    "bottled at",
    "bottled in bond",
    "product of",
    "enjoy responsibly",
    "distilled in",
    "est.",
    "est ",
    "cocktail recipes",
    "warehouse",
    "dsp-",
    "bw-",
    "tpwbh-",
    "registry",
    "plant no",
    "ttb f 5100",
    "serial number",
    "rep. id",
    "department of the treasury",
    "alcohol and tobacco tax",
    "form bleed",
    "not for resale",
    "net wt",
)

_BATCH_LOT_LINE = re.compile(
    r"\bbatch\b.*(?:\blot\b|\d{4}-\d|\d{3,})",
    re.I,
)


def is_batch_lot_line(text: str) -> bool:
    """True for batch/lot/registry-style metadata lines, not 'Small Batch Whiskey' class lines."""
    lower = (text or "").strip().lower()
    if not lower:
        return False
    if _BATCH_LOT_LINE.search(lower):
        return True
    return bool(re.search(r"\bbatch\b", lower) and re.search(r"\blot\s+\d", lower))


# Examples shown to the LLM bin prompt (not an exhaustive runtime list).
DISCARD_LINE_EXAMPLES = (
    "Batch No. OT-2024-117",
    "Batch RYE-2026-009 · Lot 18C",
    "Warehouse H / DSP-IN-12345",
    "www.example.com · Scan QR code",
    "DEPARTMENT OF THE TREASURY / SERIAL NUMBER",
    "Random OCR garbage or partial form bleed",
)


def is_discard_line(text: str) -> bool:
    """True for marketing, warehouse, registry, and form-noise lines to skip when binning."""
    lower = (text or "").strip().lower()
    if not lower:
        return True
    return is_batch_lot_line(text) or any(hint in lower for hint in MARKETING_HINTS)
