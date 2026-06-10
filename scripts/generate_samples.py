"""Generate synthetic label samples in a white application affix rectangle."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
LABELS = ROOT / "samples" / "labels"
AFFIX_SPACE_SIZE = (1800, 950)
AFFIX_MARGIN = 56
AFFIX_GAP = 72
BRAND_STICKER_SIZE = (720, 520)
NECK_STICKER_SIZE = (780, 220)
GOV = (
    "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
    "alcoholic beverages during pregnancy because of the risk of birth defects. "
    "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
    "operate machinery, and may cause health problems."
)

STICKER_BORDER = "#3a3a3a"
BRAND_STICKER_FILL = "#eee8dc"
NECK_STICKER_FILL = "#fafafa"

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
    "handwritten": ["segoepr.ttf", "Segoe Print.ttf", "SegoePrint.ttf"],
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


@dataclass
class TextBlock:
    text: str
    xy: tuple[int, int]
    font: tuple[str, int] = ("arial", 16)
    anchor: str = "lt"
    color: str = "black"


@dataclass
class ArtBand:
    xy: tuple[int, int, int, int]
    fill: str = "#d8d0c4"


@dataclass
class PlacedSticker:
    image: Image.Image
    xy: tuple[int, int]


def _text_origin(draw: ImageDraw.ImageDraw, text: str, xy: tuple[int, int], font, anchor: str) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    x, y = xy
    if anchor == "mm":
        return x - width // 2, y - height // 2
    if anchor == "mt":
        return x - width // 2, y
    if anchor == "rt":
        return x - width, y
    if anchor == "rb":
        return x - width, y - height
    return x, y


def _draw_wrapped_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    x: int,
    y: int,
    *,
    width_chars: int,
    font,
    fill: str = "black",
) -> int:
    for line in _wrap(text, width_chars):
        draw.text((x, y), line, fill=fill, font=font)
        bbox = draw.textbbox((x, y), line, font=font)
        y = bbox[3] + 3
    return y


def _sticker_canvas(
    size: tuple[int, int],
    *,
    fill: str,
    border: str = STICKER_BORDER,
    border_width: int = 2,
) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rectangle(
        (0, 0, size[0] - 1, size[1] - 1),
        fill=fill,
        outline=border,
        width=border_width,
    )
    return img, draw


def _rotate_sticker(img: Image.Image, angle: float) -> Image.Image:
    if abs(angle) < 0.01:
        return img
    return img.rotate(
        angle,
        expand=True,
        resample=Image.Resampling.BICUBIC,
        fillcolor=(0, 0, 0, 0),
    )


def build_brand_sticker(
    *,
    brand: str,
    class_type: str,
    abv: str,
    net: str,
    rotate: float = 0,
    brand_font=("arial", 40),
    body_font=("arial", 20),
    background: str = BRAND_STICKER_FILL,
    text_color: str = "black",
    extra_lines: list[str] | None = None,
    size: tuple[int, int] = BRAND_STICKER_SIZE,
    blocks: list[TextBlock] | None = None,
    art_bands: list[ArtBand] | None = None,
) -> Image.Image:
    """Front/brand label sticker — mandatory fields except government warning."""
    img, draw = _sticker_canvas(size, fill=background)
    if blocks:
        for band in art_bands or []:
            draw.rectangle(band.xy, fill=band.fill)
        for block in blocks:
            font = _font(*block.font)
            if block.anchor == "wrap":
                _draw_wrapped_text(
                    draw,
                    block.text,
                    block.xy[0],
                    block.xy[1],
                    width_chars=58,
                    font=font,
                    fill=block.color,
                )
                continue
            origin = _text_origin(draw, block.text, block.xy, font, block.anchor)
            draw.text(origin, block.text, fill=block.color, font=font)
    else:
        x, y = 18, 16
        draw.text((x, y), brand, fill=text_color, font=_font(*brand_font))
        y += brand_font[1] + 10
        draw.text((x, y), class_type, fill=text_color, font=_font(*body_font))
        y += body_font[1] + 8
        draw.text((x, y), abv, fill=text_color, font=_font(*body_font))
        y += body_font[1] + 8
        draw.text((x, y), net, fill=text_color, font=_font(*body_font))
        y += body_font[1] + 8
        if extra_lines:
            for line in extra_lines:
                draw.text((x, y), line, fill=text_color, font=_font(body_font[0], max(body_font[1] - 4, 12)))
                y += body_font[1] + 4
    if rotate:
        img = _rotate_sticker(img, rotate)
    return img


def build_neck_warning_sticker(
    warning: str,
    *,
    warning_font=("arial", 11),
    background: str = NECK_STICKER_FILL,
    text_color: str = "black",
    size: tuple[int, int] = NECK_STICKER_SIZE,
    rotate: float = 0,
) -> Image.Image:
    """Bottle-neck strip sticker with TTB government warning only."""
    img, draw = _sticker_canvas(size, fill=background)
    _draw_wrapped_text(
        draw,
        warning,
        14,
        12,
        width_chars=100,
        font=_font(*warning_font),
        fill=text_color,
    )
    if rotate:
        img = _rotate_sticker(img, rotate)
    return img


def build_wide_brand_strip(
    *,
    brand: str,
    class_type: str,
    abv: str,
    net: str,
    background: str = BRAND_STICKER_FILL,
    text_color: str = "black",
) -> Image.Image:
    size = (900, 240)
    img, draw = _sticker_canvas(size, fill=background)
    draw.text((22, 20), brand, fill=text_color, font=_font("arial", 36))
    draw.text((22, 68), class_type, fill=text_color, font=_font("arial", 18))
    draw.text((22, 102), abv, fill=text_color, font=_font("arial", 18))
    draw.text((22, 136), net, fill=text_color, font=_font("arial", 18))
    return img


def compose_affix_space(
    stickers: list[PlacedSticker],
    *,
    photocopy: bool = False,
) -> Image.Image:
    page = Image.new("RGB", AFFIX_SPACE_SIZE, "white")
    draw = ImageDraw.Draw(page)
    draw.rectangle((0, 0, AFFIX_SPACE_SIZE[0] - 1, AFFIX_SPACE_SIZE[1] - 1), outline="#cccccc", width=1)
    for placed in stickers:
        sticker = placed.image.convert("RGBA")
        page.paste(sticker, placed.xy, sticker)
    if photocopy:
        page = page.filter(ImageFilter.GaussianBlur(radius=0.6))
        page = ImageEnhance.Contrast(page).enhance(0.75)
        page = ImageEnhance.Brightness(page).enhance(1.05)
    return page


def _layout_side_by_side(left: Image.Image, right: Image.Image) -> list[PlacedSticker]:
    """Place two stickers on the affix canvas without clipping."""
    canvas_w, canvas_h = AFFIX_SPACE_SIZE
    left_x = AFFIX_MARGIN
    left_y = max(AFFIX_MARGIN, (canvas_h - left.height) // 2)
    right_x = canvas_w - AFFIX_MARGIN - right.width
    right_y = max(AFFIX_MARGIN, (canvas_h - right.height) // 2)
    min_right = left_x + left.width + AFFIX_GAP
    if right_x < min_right:
        right_x = min_right
    if right_x + right.width > canvas_w - AFFIX_MARGIN:
        right_x = max(AFFIX_MARGIN, canvas_w - AFFIX_MARGIN - right.width)
    return [
        PlacedSticker(left, (left_x, left_y)),
        PlacedSticker(right, (right_x, right_y)),
    ]


def _default_dual_layout(
    brand: Image.Image,
    neck: Image.Image,
) -> list[PlacedSticker]:
    return _layout_side_by_side(brand, neck)


def render_affix_space(path: Path, page: Image.Image) -> None:
    page.save(path)


def add_sample(
    apps: list[dict],
    *,
    filename: str,
    page: Image.Image,
    brand_name: str,
    class_type: str,
    alcohol_content: str,
    net_contents: str,
    government_warning: str,
) -> None:
    render_affix_space(LABELS / filename, page)
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


def _std_app(**overrides) -> dict:
    base = dict(
        brand_name="OLD TOM DISTILLERY",
        class_type="Kentucky Straight Bourbon Whiskey",
        alcohol_content="45% Alc./Vol. (90 Proof)",
        net_contents="750 mL",
        government_warning=GOV,
    )
    base.update(overrides)
    return base


def _dual(
    *,
    brand="OLD TOM DISTILLERY",
    class_type="Kentucky Straight Bourbon Whiskey",
    abv="45% Alc./Vol. (90 Proof)",
    net="750 mL",
    warning=GOV,
    brand_rotate: float = 0,
    neck_rotate: float = 0,
    warning_font=("arial", 11),
    layout: list[PlacedSticker] | None = None,
    photocopy: bool = False,
    **brand_kwargs,
) -> Image.Image:
    brand_sticker = build_brand_sticker(
        brand=brand,
        class_type=class_type,
        abv=abv,
        net=net,
        rotate=brand_rotate,
        **brand_kwargs,
    )
    neck_sticker = build_neck_warning_sticker(
        warning,
        warning_font=warning_font,
        rotate=neck_rotate,
    )
    stickers = layout or _default_dual_layout(brand_sticker, neck_sticker)
    return compose_affix_space(stickers, photocopy=photocopy)


def _generate_all(apps: list[dict]) -> None:
    std = _std_app()
    bad_warning = GOV.replace("GOVERNMENT WARNING:", "Government Warning:")
    bw, bh = BRAND_STICKER_SIZE

    add_sample(apps, filename="old_tom_pass.png", page=_dual(), **std)

    add_sample(
        apps,
        filename="stones_throw_brand_case.png",
        page=_dual(brand="STONE'S THROW"),
        **_std_app(brand_name="Stone's Throw"),
    )

    add_sample(
        apps,
        filename="wrong_abv_fail.png",
        page=_dual(abv="40% Alc./Vol. (80 Proof)"),
        **std,
    )

    add_sample(
        apps,
        filename="bad_warning_fail.png",
        page=_dual(warning=bad_warning),
        **std,
    )

    add_sample(
        apps,
        filename="wrong_net_fail.png",
        page=_dual(net="700 mL", brand_font=("verdana", 30), body_font=("verdana", 16)),
        **std,
    )

    add_sample(
        apps,
        filename="brand_typo_fail.png",
        page=_dual(brand="OLD TUM DISTILLERY", brand_font=("comic", 30), body_font=("comic", 16)),
        **std,
    )

    add_sample(
        apps,
        filename="class_typo_fail.png",
        page=_dual(class_type="Kentucky Staight Bourbon Whiskey"),
        **std,
    )

    add_sample(
        apps,
        filename="rotated_pass.png",
        page=_dual(brand_rotate=90),
        **std,
    )

    add_sample(
        apps,
        filename="rotated_180_pass.png",
        page=_dual(brand_rotate=180, brand_font=("times", 30), body_font=("times", 16)),
        **std,
    )

    add_sample(
        apps,
        filename="slight_skew_pass.png",
        page=_dual(brand_rotate=8),
        **std,
    )

    add_sample(
        apps,
        filename="slight_skew_ccw_pass.png",
        page=_dual(brand_rotate=-12),
        **std,
    )

    add_sample(
        apps,
        filename="script_brand_pass.png",
        page=_dual(brand_font=("script", 38), body_font=("arial", 16)),
        **std,
    )

    add_sample(
        apps,
        filename="script_class_pass.png",
        page=_dual(body_font=("script", 20)),
        **std,
    )

    add_sample(
        apps,
        filename="handwritten_style_pass.png",
        page=_dual(brand_font=("handwritten", 34), body_font=("handwritten", 16)),
        **std,
    )

    add_sample(
        apps,
        filename="impact_display_pass.png",
        page=_dual(brand_font=("impact", 36), body_font=("impact", 16)),
        **std,
    )

    add_sample(
        apps,
        filename="low_contrast_pass.png",
        page=_dual(background="#d8d2c8", text_color="#555555"),
        **std,
    )

    add_sample(
        apps,
        filename="color_navy_gold_pass.png",
        page=_dual(background="#1a2744", text_color="#c9a227"),
        **std,
    )

    add_sample(
        apps,
        filename="color_burgundy_cream_pass.png",
        page=_dual(background="#4a1520", text_color="#f5e6c8"),
        **std,
    )

    add_sample(
        apps,
        filename="serif_mixed_pass.png",
        page=_dual(brand_font=("georgia", 32), body_font=("times", 16)),
        **std,
    )

    add_sample(
        apps,
        filename="condensed_pass.png",
        page=_dual(brand_font=("impact", 32), body_font=("consolas", 14)),
        **std,
    )

    add_sample(
        apps,
        filename="tiny_warning_pass.png",
        page=_dual(warning_font=("arial", 7)),
        **std,
    )

    brand_strip = build_wide_brand_strip(
        brand="OLD TOM DISTILLERY",
        class_type="Kentucky Straight Bourbon Whiskey",
        abv="45% Alc./Vol. (90 Proof)",
        net="750 mL",
    )
    neck = build_neck_warning_sticker(GOV)
    add_sample(
        apps,
        filename="strip_wide_pass.png",
        page=compose_affix_space(_layout_side_by_side(brand_strip, neck)),
        **std,
    )

    add_sample(apps, filename="photocopy_pass.png", page=_dual(photocopy=True), **std)

    add_sample(
        apps,
        filename="warehouse_noise_pass.png",
        page=_dual(
            extra_lines=[
                "Warehouse H",
                "DSP-IN-12345",
                "Bottled at 456 Bond St, Lawrenceburg, IN 47025",
                "Lot OT-2026-042",
            ],
        ),
        **std,
    )

    add_sample(
        apps,
        filename="noisy_marketing_pass.png",
        page=_dual(
            extra_lines=[
                "Batch No. OT-2024-117",
                "Bottled by Old Tom Spirits LLC",
                "Product of USA · Enjoy Responsibly",
                "Scan QR code for cocktail recipes",
            ],
        ),
        **std,
    )

    add_sample(
        apps,
        filename="noisy_reordered_pass.png",
        page=_dual(
            extra_lines=[
                "Distilled in Kentucky · Lot 42A",
                "www.oldtomdistillery.example",
            ],
        ),
        **std,
    )

    add_sample(
        apps,
        filename="noisy_serif_pass.png",
        page=_dual(
            brand_font=("georgia", 32),
            body_font=("times", 16),
            extra_lines=["Batch No. SERIF-09", "Bottled in Bond · Product of Kentucky"],
        ),
        **std,
    )

    add_sample(
        apps,
        filename="layout_center_brand_pass.png",
        page=_dual(
            blocks=[
                TextBlock("Distilled in Kentucky · Est. 2018", (bw // 2, 18), font=("arial", 11), anchor="mt"),
                TextBlock("Kentucky Straight Bourbon Whiskey", (bw // 2, 42), font=("arial", 15), anchor="mt"),
                TextBlock("OLD TOM DISTILLERY", (bw // 2, 120), font=("arial", 32), anchor="mm"),
                TextBlock("45% Alc./Vol. (90 Proof)", (18, bh - 52), font=("arial", 14)),
                TextBlock("750 mL", (bw - 18, bh - 52), font=("arial", 14), anchor="rt"),
            ],
            art_bands=[ArtBand(xy=(24, 150, bw - 24, 250))],
        ),
        **std,
    )

    add_sample(
        apps,
        filename="layout_scattered_pass.png",
        page=_dual(
            blocks=[
                TextBlock("750 mL", (18, 18), font=("arial", 14)),
                TextBlock("45% Alc./Vol. (90 Proof)", (bw - 18, 18), font=("arial", 13), anchor="rt"),
                TextBlock("Kentucky Straight Bourbon Whiskey", (18, 140), font=("arial", 15)),
                TextBlock("OLD TOM DISTILLERY", (bw // 2, 190), font=("arial", 30), anchor="mm"),
                TextBlock("Batch No. OT-2024-117 · Enjoy Responsibly", (bw // 2, 240), font=("arial", 10), anchor="mt"),
            ],
        ),
        **std,
    )

    add_sample(
        apps,
        filename="layout_footer_strip_pass.png",
        page=_dual(
            blocks=[
                TextBlock("OLD TOM DISTILLERY", (18, 18), font=("arial", 24)),
                TextBlock("Kentucky Straight Bourbon Whiskey", (bw - 18, 20), font=("arial", 13), anchor="rt"),
                TextBlock("45% Alc./Vol. (90 Proof)", (18, bh - 52), font=("arial", 14)),
                TextBlock("750 mL", (bw - 18, bh - 52), font=("arial", 14), anchor="rt"),
            ],
            art_bands=[ArtBand(xy=(16, 70, bw - 16, bh - 70))],
        ),
        **std,
    )

    add_sample(
        apps,
        filename="layout_scattered_net_fail.png",
        page=_dual(
            blocks=[
                TextBlock("700 mL", (18, 18), font=("arial", 14)),
                TextBlock("45% Alc./Vol. (90 Proof)", (bw - 18, 18), font=("arial", 13), anchor="rt"),
                TextBlock("Kentucky Straight Bourbon Whiskey", (18, 140), font=("arial", 15)),
                TextBlock("OLD TOM DISTILLERY", (bw // 2, 190), font=("arial", 30), anchor="mm"),
                TextBlock("Lot 42A · Product of USA", (bw // 2, 240), font=("arial", 10), anchor="mt"),
            ],
        ),
        **std,
    )

    ironwood_app = dict(
        brand_name="IRONWOOD CANYON DISTILLING CO.",
        class_type="Small Batch Straight Rye Whiskey",
        alcohol_content="46% Alc./Vol. (92 Proof)",
        net_contents="750 mL",
        government_warning=GOV,
    )
    ironwood_brand = build_brand_sticker(
        brand="IRONWOOD CANYON DISTILLING CO.",
        class_type="Small Batch Straight Rye Whiskey",
        abv="46% Alc./Vol. (92 Proof)",
        net="750 mL",
        background="#0f4c47",
        text_color="#f5f0e1",
        blocks=[
            TextBlock("DEPARTMENT OF THE TREASURY · FORM BLEED", (bw // 2, 10), font=("arial", 9), anchor="mt", color="#7fc8b8"),
            TextBlock("750 mL", (16, 16), font=("impact", 15), color="#ffb347"),
            TextBlock("46% Alc./Vol. (92 Proof)", (bw - 16, 16), font=("arial", 13), anchor="rt", color="#ffb347"),
            TextBlock("Warehouse 7 · DSP-TX-88421", (16, 38), font=("consolas", 10), color="#7fc8b8"),
            TextBlock("BW-4421-A · Plant Registry TX", (bw - 16, 38), font=("consolas", 10), anchor="rt", color="#7fc8b8"),
            TextBlock("Batch RYE-2026-009 · Lot 18C", (bw // 2, 58), font=("arial", 9), anchor="mt", color="#7fc8b8"),
            TextBlock("Bottled at Ironwood Canyon, TX 79001", (16, 76), font=("arial", 9), color="#7fc8b8"),
            TextBlock("www.ironwoodcanyon.example", (bw - 16, 76), font=("arial", 9), anchor="rt", color="#7fc8b8"),
            TextBlock("Small Batch", (18, 118), font=("georgia", 14), color="#c5e8dc"),
            TextBlock("Straight Rye Whiskey", (18, 138), font=("georgia", 14), color="#c5e8dc"),
            TextBlock("IRONWOOD CANYON", (bw // 2, 188), font=("impact", 34), anchor="mm", color="#ff6f59"),
            TextBlock("DISTILLING CO.", (bw // 2, 228), font=("impact", 28), anchor="mm", color="#ff6f59"),
            TextBlock("Scan QR code for cocktail recipes", (bw // 2, 268), font=("arial", 9), anchor="mt", color="#7fc8b8"),
            TextBlock("Product of Texas · Enjoy Responsibly", (16, 292), font=("arial", 9), color="#7fc8b8"),
            TextBlock("Distilled in the Texas High Plains", (bw - 16, 292), font=("arial", 9), anchor="rt", color="#7fc8b8"),
            TextBlock("TTB F 5100.31 · Serial ref. only", (bw // 2, 312), font=("arial", 8), anchor="mt", color="#7fc8b8"),
            TextBlock("750 mL NET WT · NOT FOR RESALE", (16, bh - 48), font=("arial", 9), color="#7fc8b8"),
            TextBlock("46% Alc./Vol. (92 Proof)", (bw - 16, bh - 48), font=("arial", 12), anchor="rt", color="#ffb347"),
        ],
        art_bands=[
            ArtBand(xy=(12, 96, bw - 12, 168), fill="#157a72"),
            ArtBand(xy=(40, 160, bw - 40, 252), fill="#115e59"),
            ArtBand(xy=(8, 278, bw - 8, 334), fill="#157a72"),
        ],
    )
    ironwood_neck = build_neck_warning_sticker(
        GOV,
        background="#115e59",
        text_color="#f4f1de",
        warning_font=("arial", 10),
    )
    add_sample(
        apps,
        filename="ironwood_chaos_pass.png",
        page=compose_affix_space(_layout_side_by_side(ironwood_brand, ironwood_neck)),
        **ironwood_app,
    )


def main() -> None:
    LABELS.mkdir(parents=True, exist_ok=True)
    apps: list[dict] = []
    _generate_all(apps)

    expected = {entry["sample_file"] for entry in apps}
    for path in LABELS.glob("*.png"):
        if path.name not in expected:
            path.unlink()

    (ROOT / "samples" / "applications.json").write_text(
        json.dumps(apps, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {len(apps)} affix-space samples to {LABELS}")


if __name__ == "__main__":
    main()
