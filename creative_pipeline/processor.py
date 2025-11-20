from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Tuple, List

from PIL import Image

from .image_generator import generate_base_image
from .models import CampaignBrief, Product
from .utils import (
    choose_message_for_locale,
    fit_image_with_safe_bottom_zone,
    overlay_message_and_logo,
)
from .review_and_compliance import generate_with_review_loop

# Aspect ratios and pixel sizes we must support
ASPECT_SPECS: Dict[str, Tuple[int, int]] = {
    "1x1": (1080, 1080),
    "9x16": (1080, 1920),
    "16x9": (1920, 1080),
}


# Helper method to read from the brief safely
def _get_banned_words_from_brief(brief: CampaignBrief) -> List[str]:
    """
    Extract banned words from the brief's legal config, if present.

    Returns an empty list if no legal config or banned_words are defined.
    """
    if brief.legal and brief.legal.banned_words:
        return list(brief.legal.banned_words)
    return []


def generate_creatives_for_product(
        product: Product,
        brief: CampaignBrief,
        output_root: Path,
        locale: str = "en_US",
) -> None:
    """
    For one product, generate creatives in all required aspect ratios.

    For each aspect ratio:
      - Generate an image with Gemini via generate_base_image.
      - Fit/crop it with a bias toward preserving a calm lower area.
      - Overlay the localized marketing message and brand logo.
      - Run a Gemini-based review loop (legal + brand compliance + quality).
      - Save the final, approved creative.
    """
    product_out_dir = output_root / product.id
    product_out_dir.mkdir(parents=True, exist_ok=True)

    message = choose_message_for_locale(product, locale)
    logging.info(
        "Generating creatives for product=%s locale=%s (message length=%d)",
        product.id,
        locale,
        len(message),
    )

    banned_words = _get_banned_words_from_brief(brief)
    logging.info(
        "Using %d banned words from brief for product=%s.",
        len(banned_words),
        product.id,
    )


    for ratio_key, size in ASPECT_SPECS.items():
        logging.info(
            "Starting generation for %s [%s] at size %sx%s",
            product.id,
            ratio_key,
            size[0],
            size[1],
        )

        def refinement_callback(
                previous_img: Image.Image | None,
                feedback: str | None,
        ) -> Image.Image:
            """
            Generate or refine a background image for this aspect ratio.

            At the moment this callback ignores feedback and always asks
            Gemini for a fresh image per iteration, but it is structured
            so you could later incorporate feedback into the prompt or
            attach the previous image as a visual reference.
            """
            base_img: Image.Image = generate_base_image(
                brief=brief,
                product=product,
                size=size,
            )

            fitted = fit_image_with_safe_bottom_zone(
                base_img,
                size=size,
                safe_bottom_ratio=0.25,
            )

            final = overlay_message_and_logo(
                fitted,
                message=message,
                brand=brief.brand,
            )
            return final

        # Run iterative generation + Gemini review for this aspect ratio.

        final_img, review = generate_with_review_loop(
            brief=brief,
            generate_fn=refinement_callback,
            max_iterations=3,
            min_quality_score=80,
            banned_words=banned_words,  # CHANGED
        )

        logging.info(
            "Final review for %s [%s]: legal=%s, brand=%s, compliant=%s, score=%d",
            product.id,
            ratio_key,
            review.legal_compliant,
            review.brand_compliant,
            review.compliant,
            review.quality_score,
        )

        # Save under <output_root>/<product_id>/<aspect>/creative.png
        out_dir = product_out_dir / ratio_key
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "creative.png"
        final_img.save(out_path, format="PNG")
        logging.info("Saved creative for %s [%s] to %s", product.id, ratio_key, out_path)

