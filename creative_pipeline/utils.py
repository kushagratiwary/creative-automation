from __future__ import annotations

import logging
from pathlib import Path
from typing import Tuple

from PIL import Image, ImageDraw, ImageFont

from .models import Brand, Product


# ---------------------------------------------------------------------------
# General helpers
# ---------------------------------------------------------------------------


def slugify(text: str) -> str:
    """
    Convert an arbitrary string into a simple filesystem and id friendly slug.

    - Lowercases the input.
    - Keeps only alphanumeric characters and simple separators.
    - Collapses whitespace and punctuation into hyphens.
    - Returns "item" if everything is stripped away.
    """
    text = text.strip().lower()
    out_chars = []
    for ch in text:
        if ch.isalnum():
            out_chars.append(ch)
        elif ch in (" ", "-", "_"):
            out_chars.append("-")
    result = "".join(out_chars).strip("-")
    return result or "item"


def choose_message_for_locale(product: Product, locale: str) -> str:
    """Pick a localized message for the product if available."""
    if product.message_localized:
        if locale in product.message_localized:
            return product.message_localized[locale]

        lang = locale.split("_", 1)[0]
        if lang in product.message_localized:
            return product.message_localized[lang]

    return product.message


def _parse_hex_color(hex_str: str) -> Tuple[int, int, int]:
    """Convert a #rrggbb or #rgb string to an (r, g, b) triple.

    Falls back to black if parsing fails.
    """
    if not hex_str:
        return (0, 0, 0)
    s = hex_str.strip()
    if s.startswith("#"):
        s = s[1:]
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6:
        return (0, 0, 0)
    try:
        r = int(s[0:2], 16)
        g = int(s[2:4], 16)
        b = int(s[4:6], 16)
        return (r, g, b)
    except ValueError:
        return (0, 0, 0)


# ---------------------------------------------------------------------------
# Image fitting / cover logic
# ---------------------------------------------------------------------------


def _compute_cover_scale(
        src_size: Tuple[int, int],
        dst_size: Tuple[int, int],
) -> float:
    sw, sh = src_size
    dw, dh = dst_size
    return max(dw / sw, dh / sh)


def fit_image_with_safe_bottom_zone(
        img: Image.Image,
        size: Tuple[int, int],
        safe_bottom_ratio: float = 0.25,
) -> Image.Image:
    """
    Scale img to fully cover the destination canvas, then crop, biasing the
    crop slightly upward so the bottom region is cleaner for text overlays.
    """
    dst_w, dst_h = size
    scale = _compute_cover_scale(img.size, size)
    new_w = int(round(img.width * scale))
    new_h = int(round(img.height * scale))

    resized = img.resize((new_w, new_h), Image.LANCZOS)

    left = max(0, (new_w - dst_w) // 2)
    right = left + dst_w

    excess_h = new_h - dst_h
    if excess_h <= 0:
        top = 0
    else:
        # Crop a bit more from the top so the lower part stays calmer.
        bias = 0.35
        top = int(round(excess_h * bias))
    bottom = top + dst_h

    box = (left, top, right, bottom)
    return resized.crop(box)


# ---------------------------------------------------------------------------
# Text and logo overlay
# ---------------------------------------------------------------------------


def _load_font(target_height: int) -> ImageFont.FreeTypeFont:
    size = max(14, int(target_height * 0.7))
    try:
        return ImageFont.truetype("arial.ttf", size)
    except Exception:  # pragma: no cover
        return ImageFont.load_default()


def _measure_text_width(
        draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont
) -> int:
    """Measure single-line text width, compatible with new Pillow."""
    try:
        return int(draw.textlength(text, font=font))
    except Exception:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0]


def _wrap_text(
        draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int
) -> str:
    words = text.split()
    if not words:
        return ""

    lines = []
    current = words[0]
    for word in words[1:]:
        trial = current + " " + word
        w = _measure_text_width(draw, trial, font)
        if w <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return "\n".join(lines)


def overlay_message_and_logo(
        img: Image.Image,
        message: str,
        brand: Brand,
) -> Image.Image:
    """
    Draw a soft vignette at the bottom, then a translucent neutral text panel
    near the bottom-left and a white rounded logo card at the bottom-right.

    The font size is dynamically reduced as needed so that the text panel
    stays within a reasonable height and does not collide horizontally
    with the logo card. Both panel and logo share the same bottom baseline.
    """
    base = img.convert("RGBA")
    result = base.copy()
    w, h = result.size

    # -------------------------------------------------------------
    # 1) Bottom vignette for readability
    # -------------------------------------------------------------
    vignette = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    vg_draw = ImageDraw.Draw(vignette)
    start_y = int(h * 0.65)
    end_y = h
    height = max(1, end_y - start_y)
    for i, y in enumerate(range(start_y, end_y)):
        t = i / height
        alpha = int(120 * t)
        vg_draw.line((0, y, w, y), fill=(0, 0, 0, alpha))
    result = Image.alpha_composite(result, vignette)

    draw = ImageDraw.Draw(result, "RGBA")

    margin_x = int(w * 0.05)
    margin_y = int(h * 0.06)

    # -------------------------------------------------------------
    # 2) Precompute logo card geometry (bottom-right)
    # -------------------------------------------------------------
    card_target_h = int(h * 0.14)           # logo image target height
    card_pad = int(card_target_h * 0.25)    # padding inside card
    card_h = card_target_h + 2 * card_pad
    card_w = card_target_h + 2 * card_pad   # assume roughly square card

    # Logo card anchors
    card_x1 = w - margin_x
    card_y1 = h - margin_y
    card_x0 = card_x1 - card_w
    card_y0 = card_y1 - card_h

    # -------------------------------------------------------------
    # 3) Text panel: choose font size & width so it doesn't clash
    #    with the logo horizontally, while staying near the bottom.
    # -------------------------------------------------------------
    # Leave at least 2*margin_x of space between panel and logo.
    max_panel_right = card_x0 - 2 * margin_x
    panel_max_width = max(int(w * 0.4), max_panel_right - margin_x)

    max_panel_height = int(h * 0.26)  # limit so panel isn't too tall

    font_scales = [0.060, 0.055, 0.050, 0.045, 0.040, 0.035]
    chosen_font = None
    wrapped_text = None
    panel_w = panel_h = 0

    for scale in font_scales:
        line_box_height = int(h * scale)
        font = _load_font(line_box_height)

        temp_img = Image.new("RGBA", (panel_max_width, h))
        temp_draw = ImageDraw.Draw(temp_img)

        wrapped = _wrap_text(
            temp_draw, message, font, panel_max_width - int(w * 0.06)
        )
        text_bbox = temp_draw.multiline_textbbox(
            (0, 0), wrapped, font=font, spacing=4
        )
        text_w = text_bbox[2] - text_bbox[0]
        text_h = text_bbox[3] - text_bbox[1]

        pad_x = int(w * 0.03)
        pad_y = int(h * 0.025)
        trial_panel_w = min(panel_max_width, text_w + 2 * pad_x)
        trial_panel_h = text_h + 2 * pad_y

        if trial_panel_h <= max_panel_height:
            chosen_font = font
            wrapped_text = wrapped
            panel_w = trial_panel_w
            panel_h = trial_panel_h
            break

    # If even the smallest font is too tall, fall back to smallest size
    if chosen_font is None:
        scale = font_scales[-1]
        line_box_height = int(h * scale)
        chosen_font = _load_font(line_box_height)

        temp_img = Image.new("RGBA", (panel_max_width, h))
        temp_draw = ImageDraw.Draw(temp_img)
        wrapped_text = _wrap_text(
            temp_draw, message, chosen_font, panel_max_width - int(w * 0.06)
        )
        text_bbox = temp_draw.multiline_textbbox(
            (0, 0), wrapped_text, font=chosen_font, spacing=4
        )
        text_w = text_bbox[2] - text_bbox[0]
        text_h = text_bbox[3] - text_bbox[1]
        pad_x = int(w * 0.03)
        pad_y = int(h * 0.025)
        panel_w = min(panel_max_width, text_w + 2 * pad_x)
        panel_h = min(max_panel_height, text_h + 2 * pad_y)

    # Panel anchored to bottom-left, same baseline as logo
    panel_x0 = margin_x
    panel_y1 = h - margin_y
    panel_y0 = panel_y1 - panel_h
    panel_x1 = panel_x0 + panel_w

    panel_color = (255, 255, 255, 185)
    draw.rounded_rectangle(
        (panel_x0, panel_y0, panel_x1, panel_y1),
        radius=int(panel_h * 0.25),
        fill=panel_color,
    )

    text_x = panel_x0 + int(w * 0.03)
    text_y = panel_y0 + int(h * 0.025)
    draw.multiline_text(
        (text_x, text_y),
        wrapped_text,
        fill=(0, 0, 0, 255),
        font=chosen_font,
        spacing=4,
    )

    # -------------------------------------------------------------
    # 4) Logo overlay in a white rounded card (bottom-right)
    # -------------------------------------------------------------
    if brand.logo_path:
        try:
            logo_path = Path(brand.logo_path) if isinstance(brand.logo_path, str) else brand.logo_path
            if not logo_path.exists():
                logging.warning("Logo file not found at %s; skipping logo overlay.", logo_path)
            else:
                logo_img = Image.open(logo_path).convert("RGBA")
                scale = card_target_h / float(logo_img.height)
                logo_w = int(logo_img.width * scale)
                logo_h = int(logo_img.height * scale)
                logo_resized = logo_img.resize((logo_w, logo_h), Image.LANCZOS)

                # recompute card size based on actual logo size
                card_w = logo_w + 2 * card_pad
                card_h = logo_h + 2 * card_pad
                card_x1 = w - margin_x
                card_y1 = h - margin_y
                card_x0 = card_x1 - card_w
                card_y0 = card_y1 - card_h

                card_draw = ImageDraw.Draw(result, "RGBA")
                card_draw.rounded_rectangle(
                    (card_x0, card_y0, card_x1, card_y1),
                    radius=int(min(card_w, card_h) * 0.25),
                    fill=(255, 255, 255, 235),
                )

                logo_x = card_x0 + card_pad
                logo_y = card_y0 + card_pad
                result.alpha_composite(logo_resized, dest=(logo_x, logo_y))
        except Exception as exc:
            logging.warning("Failed to overlay brand logo: %s", exc)
    else:
        logging.info("No brand.logo_path configured; skipping logo overlay.")

    return result.convert("RGB")
