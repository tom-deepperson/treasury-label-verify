"""Generate synthetic TTB-style sample label images."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
LABELS = ROOT / "samples" / "labels"
GOV = (
    "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
    "alcoholic beverages during pregnancy because of the risk of birth defects. "
    "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
    "operate machinery, and may cause health problems."
)


def _font(size: int):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def render_label(
    path: Path,
    *,
    brand: str,
    class_type: str,
    abv: str,
    net: str,
    warning: str,
    rotate: int = 0,
):
    img = Image.new("RGB", (900, 1200), "white")
    draw = ImageDraw.Draw(img)
    y = 40
    for text, size in [
        (brand, 48),
        (class_type, 28),
        (abv, 26),
        (net, 26),
        ("Distilled in Kentucky", 22),
    ]:
        draw.text((40, y), text, fill="black", font=_font(size))
        y += size + 24
    y += 20
    for line in _wrap(warning, 70):
        draw.text((40, y), line, fill="black", font=_font(16))
        y += 22
    if rotate:
        img = img.rotate(rotate, expand=True)
    img.save(path)


def _wrap(text: str, width: int) -> list[str]:
    words = text.split()
    lines = []
    current = []
    for word in words:
        trial = " ".join(current + [word])
        if len(trial) > width:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    return lines


def main():
    LABELS.mkdir(parents=True, exist_ok=True)
    apps = []

    render_label(
        LABELS / "old_tom_pass.png",
        brand="OLD TOM DISTILLERY",
        class_type="Kentucky Straight Bourbon Whiskey",
        abv="45% Alc./Vol. (90 Proof)",
        net="750 mL",
        warning=GOV,
    )
    apps.append(
        {
            "brand_name": "OLD TOM DISTILLERY",
            "class_type": "Kentucky Straight Bourbon Whiskey",
            "alcohol_content": "45% Alc./Vol. (90 Proof)",
            "net_contents": "750 mL",
            "government_warning": GOV,
            "sample_file": "old_tom_pass.png",
        }
    )

    render_label(
        LABELS / "stones_throw_brand_case.png",
        brand="STONE'S THROW",
        class_type="Kentucky Straight Bourbon Whiskey",
        abv="45% Alc./Vol. (90 Proof)",
        net="750 mL",
        warning=GOV,
    )
    apps.append(
        {
            "brand_name": "Stone's Throw",
            "class_type": "Kentucky Straight Bourbon Whiskey",
            "alcohol_content": "45% Alc./Vol. (90 Proof)",
            "net_contents": "750 mL",
            "government_warning": GOV,
            "sample_file": "stones_throw_brand_case.png",
        }
    )

    render_label(
        LABELS / "wrong_abv_fail.png",
        brand="OLD TOM DISTILLERY",
        class_type="Kentucky Straight Bourbon Whiskey",
        abv="40% Alc./Vol. (80 Proof)",
        net="750 mL",
        warning=GOV,
    )
    apps.append(
        {
            "brand_name": "OLD TOM DISTILLERY",
            "class_type": "Kentucky Straight Bourbon Whiskey",
            "alcohol_content": "45% Alc./Vol. (90 Proof)",
            "net_contents": "750 mL",
            "government_warning": GOV,
            "sample_file": "wrong_abv_fail.png",
        }
    )

    bad_warning = GOV.replace("GOVERNMENT WARNING:", "Government Warning:")
    render_label(
        LABELS / "bad_warning_fail.png",
        brand="OLD TOM DISTILLERY",
        class_type="Kentucky Straight Bourbon Whiskey",
        abv="45% Alc./Vol. (90 Proof)",
        net="750 mL",
        warning=bad_warning,
    )
    apps.append(
        {
            "brand_name": "OLD TOM DISTILLERY",
            "class_type": "Kentucky Straight Bourbon Whiskey",
            "alcohol_content": "45% Alc./Vol. (90 Proof)",
            "net_contents": "750 mL",
            "government_warning": GOV,
            "sample_file": "bad_warning_fail.png",
        }
    )

    render_label(
        LABELS / "rotated_pass.png",
        brand="OLD TOM DISTILLERY",
        class_type="Kentucky Straight Bourbon Whiskey",
        abv="45% Alc./Vol. (90 Proof)",
        net="750 mL",
        warning=GOV,
        rotate=90,
    )
    apps.append(
        {
            "brand_name": "OLD TOM DISTILLERY",
            "class_type": "Kentucky Straight Bourbon Whiskey",
            "alcohol_content": "45% Alc./Vol. (90 Proof)",
            "net_contents": "750 mL",
            "government_warning": GOV,
            "sample_file": "rotated_pass.png",
        }
    )

    (ROOT / "samples" / "applications.json").write_text(
        json.dumps(apps, indent=2), encoding="utf-8"
    )
    print(f"Wrote {len(apps)} samples to {LABELS}")


if __name__ == "__main__":
    main()
