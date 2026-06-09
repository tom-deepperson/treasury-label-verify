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

FONT_DIRS = [
    Path("C:/Windows/Fonts"),
    Path("/usr/share/fonts/truetype/dejavu"),
    Path("/usr/share/fonts/truetype/liberation"),
    Path("/System/Library/Fonts/Supplemental"),
]

FONT_CANDIDATES = {
    "arial": ["arial.ttf", "Arial.ttf", "DejaVuSans.ttf"],
    "times": ["times.ttf", "Times New Roman.ttf", "DejaVuSerif.ttf"],
    "impact": ["impact.ttf", "Impact.ttf"],
    "comic": ["comic.ttf", "Comic Sans MS.ttf"],
    "georgia": ["georgia.ttf", "Georgia.ttf"],
    "verdana": ["verdana.ttf", "Verdana.ttf"],
    "consolas": ["consola.ttf", "Consolas.ttf", "DejaVuSansMono.ttf"],
    "script": ["BRUSHSCI.TTF", "segoesc.ttf", "Segoe Script.ttf", "SnellBT-Regular.otf"],
    "courier": ["cour.ttf", "Courier New.ttf", "DejaVuSansMono.ttf"],
}


def _font(name: str, size: int):
    for candidate in FONT_CANDIDATES.get(name, FONT_CANDIDATES["arial"]):
        for directory in FONT_DIRS:
            path = directory / candidate
            if path.exists():
                return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _wrap(text: str, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
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


def render_label(
    path: Path,
    *,
    brand: str,
    class_type: str,
    abv: str,
    net: str,
    warning: str,
    rotate: int = 0,
    brand_font=("arial", 48),
    body_font=("arial", 26),
    warning_font=("arial", 16),
    background: str = "white",
    text_color: str = "black",
    subtitle: str = "Distilled in Kentucky",
):
    img = Image.new("RGB", (900, 1200), background)
    draw = ImageDraw.Draw(img)
    y = 40
    draw.text((40, y), brand, fill=text_color, font=_font(*brand_font))
    y += brand_font[1] + 24
    draw.text((40, y), class_type, fill=text_color, font=_font(*body_font))
    y += body_font[1] + 18
    draw.text((40, y), abv, fill=text_color, font=_font(*body_font))
    y += body_font[1] + 18
    draw.text((40, y), net, fill=text_color, font=_font(*body_font))
    y += body_font[1] + 18
    if subtitle:
        draw.text((40, y), subtitle, fill=text_color, font=_font(body_font[0], max(body_font[1] - 4, 18)))
        y += body_font[1] + 10
    y += 20
    for line in _wrap(warning, 70):
        draw.text((40, y), line, fill=text_color, font=_font(*warning_font))
        y += warning_font[1] + 6
    if rotate:
        img = img.rotate(rotate, expand=True)
    img.save(path)


def add_sample(
    apps: list[dict],
    *,
    filename: str,
    brand_name: str,
    class_type: str,
    alcohol_content: str,
    net_contents: str,
    government_warning: str,
    brand: str,
    abv: str,
    net: str,
    warning: str,
    **render_kwargs,
):
    path = LABELS / filename
    render_label(
        path,
        brand=brand,
        class_type=class_type,
        abv=abv,
        net=net,
        warning=warning,
        **render_kwargs,
    )
    apps.append(
        {
            "brand_name": brand_name,
            "class_type": class_type,
            "alcohol_content": alcohol_content,
            "net_contents": net_contents,
            "government_warning": government_warning,
            "sample_file": filename,
        }
    )


def main():
    LABELS.mkdir(parents=True, exist_ok=True)
    apps: list[dict] = []

    add_sample(
        apps,
        filename="old_tom_pass.png",
        brand="OLD TOM DISTILLERY",
        class_type="Kentucky Straight Bourbon Whiskey",
        abv="45% Alc./Vol. (90 Proof)",
        net="750 mL",
        warning=GOV,
        brand_name="OLD TOM DISTILLERY",
        alcohol_content="45% Alc./Vol. (90 Proof)",
        net_contents="750 mL",
        government_warning=GOV,
    )

    add_sample(
        apps,
        filename="stones_throw_brand_case.png",
        brand="STONE'S THROW",
        class_type="Kentucky Straight Bourbon Whiskey",
        abv="45% Alc./Vol. (90 Proof)",
        net="750 mL",
        warning=GOV,
        brand_name="Stone's Throw",
        alcohol_content="45% Alc./Vol. (90 Proof)",
        net_contents="750 mL",
        government_warning=GOV,
    )

    add_sample(
        apps,
        filename="wrong_abv_fail.png",
        brand="OLD TOM DISTILLERY",
        class_type="Kentucky Straight Bourbon Whiskey",
        abv="40% Alc./Vol. (80 Proof)",
        net="750 mL",
        warning=GOV,
        brand_name="OLD TOM DISTILLERY",
        alcohol_content="45% Alc./Vol. (90 Proof)",
        net_contents="750 mL",
        government_warning=GOV,
    )

    bad_warning = GOV.replace("GOVERNMENT WARNING:", "Government Warning:")
    add_sample(
        apps,
        filename="bad_warning_fail.png",
        brand="OLD TOM DISTILLERY",
        class_type="Kentucky Straight Bourbon Whiskey",
        abv="45% Alc./Vol. (90 Proof)",
        net="750 mL",
        warning=bad_warning,
        brand_name="OLD TOM DISTILLERY",
        alcohol_content="45% Alc./Vol. (90 Proof)",
        net_contents="750 mL",
        government_warning=GOV,
    )

    add_sample(
        apps,
        filename="rotated_pass.png",
        brand="OLD TOM DISTILLERY",
        class_type="Kentucky Straight Bourbon Whiskey",
        abv="45% Alc./Vol. (90 Proof)",
        net="750 mL",
        warning=GOV,
        rotate=90,
        brand_name="OLD TOM DISTILLERY",
        alcohol_content="45% Alc./Vol. (90 Proof)",
        net_contents="750 mL",
        government_warning=GOV,
    )

    add_sample(
        apps,
        filename="script_brand_pass.png",
        brand="OLD TOM DISTILLERY",
        class_type="Kentucky Straight Bourbon Whiskey",
        abv="45% Alc./Vol. (90 Proof)",
        net="750 mL",
        warning=GOV,
        brand_font=("script", 54),
        body_font=("arial", 24),
        brand_name="OLD TOM DISTILLERY",
        alcohol_content="45% Alc./Vol. (90 Proof)",
        net_contents="750 mL",
        government_warning=GOV,
    )

    add_sample(
        apps,
        filename="impact_display_pass.png",
        brand="OLD TOM DISTILLERY",
        class_type="Kentucky Straight Bourbon Whiskey",
        abv="45% Alc./Vol. (90 Proof)",
        net="750 mL",
        warning=GOV,
        brand_font=("impact", 56),
        body_font=("impact", 24),
        warning_font=("arial", 15),
        brand_name="OLD TOM DISTILLERY",
        alcohol_content="45% Alc./Vol. (90 Proof)",
        net_contents="750 mL",
        government_warning=GOV,
    )

    add_sample(
        apps,
        filename="low_contrast_pass.png",
        brand="OLD TOM DISTILLERY",
        class_type="Kentucky Straight Bourbon Whiskey",
        abv="45% Alc./Vol. (90 Proof)",
        net="750 mL",
        warning=GOV,
        background="#f2f2f2",
        text_color="#666666",
        brand_name="OLD TOM DISTILLERY",
        alcohol_content="45% Alc./Vol. (90 Proof)",
        net_contents="750 mL",
        government_warning=GOV,
    )

    add_sample(
        apps,
        filename="serif_mixed_pass.png",
        brand="OLD TOM DISTILLERY",
        class_type="Kentucky Straight Bourbon Whiskey",
        abv="45% Alc./Vol. (90 Proof)",
        net="750 mL",
        warning=GOV,
        brand_font=("georgia", 50),
        body_font=("times", 26),
        warning_font=("courier", 14),
        brand_name="OLD TOM DISTILLERY",
        alcohol_content="45% Alc./Vol. (90 Proof)",
        net_contents="750 mL",
        government_warning=GOV,
    )

    add_sample(
        apps,
        filename="wrong_net_fail.png",
        brand="OLD TOM DISTILLERY",
        class_type="Kentucky Straight Bourbon Whiskey",
        abv="45% Alc./Vol. (90 Proof)",
        net="700 mL",
        warning=GOV,
        brand_font=("verdana", 46),
        body_font=("verdana", 24),
        brand_name="OLD TOM DISTILLERY",
        alcohol_content="45% Alc./Vol. (90 Proof)",
        net_contents="750 mL",
        government_warning=GOV,
    )

    add_sample(
        apps,
        filename="tiny_warning_pass.png",
        brand="OLD TOM DISTILLERY",
        class_type="Kentucky Straight Bourbon Whiskey",
        abv="45% Alc./Vol. (90 Proof)",
        net="750 mL",
        warning=GOV,
        brand_font=("arial", 48),
        body_font=("arial", 26),
        warning_font=("arial", 11),
        brand_name="OLD TOM DISTILLERY",
        alcohol_content="45% Alc./Vol. (90 Proof)",
        net_contents="750 mL",
        government_warning=GOV,
    )

    add_sample(
        apps,
        filename="brand_typo_fail.png",
        brand="OLD TUM DISTILLERY",
        class_type="Kentucky Straight Bourbon Whiskey",
        abv="45% Alc./Vol. (90 Proof)",
        net="750 mL",
        warning=GOV,
        brand_font=("comic", 44),
        body_font=("comic", 22),
        brand_name="OLD TOM DISTILLERY",
        alcohol_content="45% Alc./Vol. (90 Proof)",
        net_contents="750 mL",
        government_warning=GOV,
    )

    add_sample(
        apps,
        filename="condensed_pass.png",
        brand="OLD TOM DISTILLERY",
        class_type="Kentucky Straight Bourbon Whiskey",
        abv="45% Alc./Vol. (90 Proof)",
        net="750 mL",
        warning=GOV,
        brand_font=("impact", 48),
        body_font=("consolas", 22),
        brand_name="OLD TOM DISTILLERY",
        alcohol_content="45% Alc./Vol. (90 Proof)",
        net_contents="750 mL",
        government_warning=GOV,
    )

    add_sample(
        apps,
        filename="rotated_180_pass.png",
        brand="OLD TOM DISTILLERY",
        class_type="Kentucky Straight Bourbon Whiskey",
        abv="45% Alc./Vol. (90 Proof)",
        net="750 mL",
        warning=GOV,
        rotate=180,
        brand_font=("times", 48),
        body_font=("times", 24),
        brand_name="OLD TOM DISTILLERY",
        alcohol_content="45% Alc./Vol. (90 Proof)",
        net_contents="750 mL",
        government_warning=GOV,
    )

    (ROOT / "samples" / "applications.json").write_text(
        json.dumps(apps, indent=2), encoding="utf-8"
    )
    print(f"Wrote {len(apps)} samples to {LABELS}")


if __name__ == "__main__":
    main()
