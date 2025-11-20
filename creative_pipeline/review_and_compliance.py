# review_and_compliance.py
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

from PIL import Image

from .models import CampaignBrief

try:
    # Google GenAI multimodal client
    from google import genai  # type: ignore
except Exception:  # pragma: no cover
    genai = None  # type: ignore


# ---------------------------------------------------------------------------
# Simple static compliance summary for brand configuration
# ---------------------------------------------------------------------------


def summarize_brand_compliance(brief: CampaignBrief) -> Dict[str, bool]:
    """
    Simple static compliance summary used for logging.

    This does not call Gemini. It only checks that:
      - A brand logo path is defined.
      - A primary brand color is defined.

    The CLI logs this summary once per brief so you can quickly see whether
    basic brand configuration has been provided.
    """
    logo_present = brief.brand.logo_path is not None
    brand_color_defined = bool(brief.brand.primary_color)

    return {
        "logo_present": logo_present,
        "brand_color_defined": brand_color_defined,
    }


# ---------------------------------------------------------------------------
# Gemini-based image compliance & quality review
# ---------------------------------------------------------------------------

_CLIENT: Optional["genai.Client"] = None  # type: ignore


def _get_client() -> "genai.Client":  # type: ignore
    """
    Lazily create a singleton Google GenAI client for review calls.

    Uses GEMINI_API_KEY or GOOGLE_API_KEY from the environment.
    """
    global _CLIENT

    if _CLIENT is not None:
        return _CLIENT

    if genai is None:
        raise RuntimeError(
            "google-genai is required for image compliance checks. "
            "Install with: pip install google-genai"
        )

    import os

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY or GOOGLE_API_KEY must be set for Gemini review."
        )

    _CLIENT = genai.Client(api_key=api_key)  # type: ignore

    logging.info("Initialized Gemini client for image review and compliance.")
    return _CLIENT


@dataclass
class ImageReviewResult:
    """Structured result from the Gemini review."""

    legal_compliant: bool
    brand_compliant: bool
    compliant: bool
    quality_score: int
    feedback: str
    raw_json: Dict[str, Any]


def _build_review_prompt(
        brief: CampaignBrief,
        banned_words: Optional[list[str]] | None = None,
) -> str:
    """
    Build the system/user prompt sent to Gemini for reviewing a creative.

    The reviewer is responsible for:
      - Basic legal and safety checks.
      - Brand compliance against the campaign brief.
      - Overall visual quality of the background image.
      - Detecting banned words or phrases anywhere in the visible image
        (overlays, packaging, UI, etc.) if a banned-word list is provided.

    Notes
    -----
    Text overlays and logo cards are added by a deterministic layout step
    after background generation. The reviewer should NOT critique layout
    or typography of those overlays, but MUST still scan any visible text
    for banned words when such a list is supplied.
    """
    brand = brief.brand

    base_instructions = (
        "You are a senior brand-compliance and creative-quality reviewer for "
        "digital marketing campaigns.\n\n"
        "You will be given a single advertisement image along with the official "
        "campaign brief. Review the image for:\n"
        "1) Legal & policy safety (no obviously illegal, hateful, or disallowed content).\n"
        "2) Brand compliance (correct general mood for the audience and region, tasteful "
        "   use of brand colors in the scene, clear focal product, and a usable area "
        "   near the bottom that could host overlays).\n"
        "3) Visual quality (composition, lighting, realism, and whether the bottom area "
        "   is visually calm enough for text overlays later).\n\n"
        f"CAMPAIGN NAME: {brief.campaign_name}\n"
        f"BRAND NAME: {brand.name}\n"
        f"PRIMARY BRAND COLOR: {brand.primary_color or 'undefined'}\n"
        f"TARGET REGION: {brief.target_region}\n"
        f"AUDIENCE: {brief.audience}\n\n"
        "IMPORTANT: The final advertisement includes a text overlay and a brand logo "
        "card that are added AFTER the image is generated. These overlays are NOT the "
        "primary subject of your aesthetic evaluation in this step.\n\n"
        "For layout and visual evaluation:\n"
        "- Do NOT critique or score the readability, placement, color, or spacing of any "
        "  text overlay you see.\n"
        "- Do NOT critique the presence, absence, or placement of the brand logo card.\n"
        "- Do NOT critique the exact shape, size, or alignment of overlay boxes or "
        "  UI-like elements.\n\n"
        "Only evaluate the underlying generated background image itself for:\n"
        "- product clarity and correct proportions,\n"
        "- lighting, environment, atmosphere, and composition,\n"
        "- whether the bottom area is visually calm and suitable for overlays later,\n"
        "- subtle and tasteful use of the brand accent color,\n"
        "- overall aesthetic quality and fit with the campaign brief.\n"
    )

    banned_text = ""
    if banned_words:
        # Present the banned words clearly so the model can look for them
        # on product packaging, UI text, or overlays.
        formatted = ", ".join(f'"{w}"' for w in banned_words)
        banned_text = (
            "\nLEGAL KEYWORD CHECK:\n"
            "There is a list of banned words or phrases that must NOT appear anywhere "
            "in the creative, including on-screen text overlays, product packaging, "
            "or interface elements.\n"
            f"BANNED_WORDS = [{formatted}].\n"
            "If you see ANY of these banned terms (or an obviously equivalent variant) "
            "in the image, you MUST set legal_compliant=false and compliant=false and "
            "explicitly mention which banned word(s) you observed in the feedback.\n"
        )

    json_instructions = (
        "\nReturn a strict JSON object ONLY (no Markdown, no code fences) with the "
        "following keys:\n"
        "- legal_compliant: boolean, true if the image is acceptable from a basic "
        "  legal/safety standpoint.\n"
        "- brand_compliant: boolean, true if the image follows the brand brief "
        "  (mood matches the audience/region and brand color usage is acceptable).\n"
        "- compliant: boolean, true only if BOTH legal_compliant and brand_compliant "
        "  are true. If any banned word appears, this must be false.\n"
        "- quality_score: integer from 0 to 100, higher is better, judging only the "
        "  generated background image (not the overlays).\n"
        "- feedback: short free-form string (1–3 sentences) describing concrete "
        "  improvements that would make the generated background image more on-brief "
        "  and visually stronger. If a banned word is present, the feedback must "
        "  clearly identify it.\n\n"
        "JSON ONLY. Do not include Markdown, code fences, or commentary outside JSON."
    )

    return base_instructions + banned_text + json_instructions


def review_image_with_gemini(
        brief: CampaignBrief,
        image: Image.Image,
        banned_words: Optional[list[str]] | None = None,
) -> ImageReviewResult:
    """
    Call Gemini (gemini-2.5-flash-image-preview) in image-understanding mode
    to evaluate a single generated creative.

    The model returns:
      - legal_compliant: bool
      - brand_compliant: bool
      - compliant: bool
      - quality_score: 0–100
      - feedback: open-ended guidance

    Parameters
    ----------
    brief:
        Campaign metadata used to condition the review.
    image:
        The creative image to review.
    banned_words:
        Optional list of banned words or phrases that must not appear
        anywhere in the visible image. If provided, the prompt instructs
        Gemini to search for these terms and treat them as a legal
        compliance failure.
    """
    client = _get_client()
    prompt = _build_review_prompt(brief, banned_words=banned_words)

    logging.info(
        "Calling Gemini for image review (legal + brand compliance + quality). "
        "banned_words_count=%d",
        len(banned_words) if banned_words else 0,
    )

    response = client.models.generate_content(  # type: ignore
        model="gemini-2.5-flash-image-preview",
        contents=[prompt, image],
    )

    # We ask the model to respond with strict JSON only. Be defensive anyway.
    raw = getattr(response, "text", "") or ""
    raw = raw.strip()
    if not raw:
        raise RuntimeError("Gemini review returned an empty response.")

    try:
        data = json.loads(raw)
    except Exception as exc:
        logging.error("Failed to parse JSON from Gemini review response: %s", exc)
        logging.debug("Raw review response text (truncated): %s", raw[:500])
        # Fall back to a conservative default.
        data = {
            "legal_compliant": False,
            "brand_compliant": False,
            "compliant": False,
            "quality_score": 0,
            "feedback": raw or "Model did not return JSON.",
        }

    legal_compliant = bool(data.get("legal_compliant", False))
    brand_compliant = bool(data.get("brand_compliant", False))
    compliant = bool(data.get("compliant", legal_compliant and brand_compliant))
    quality_score = int(data.get("quality_score", 0))
    feedback = str(data.get("feedback", "")).strip()

    return ImageReviewResult(
        legal_compliant=legal_compliant,
        brand_compliant=brand_compliant,
        compliant=compliant,
        quality_score=quality_score,
        feedback=feedback,
        raw_json=data,
    )


def generate_with_review_loop(
        brief: CampaignBrief,
        generate_fn: Callable[[Optional[Image.Image], Optional[str]], Image.Image],
        max_iterations: int = 3,
        min_quality_score: int = 80,
        banned_words: Optional[list[str]] | None = None,
) -> Tuple[Image.Image, ImageReviewResult]:
    """
    Orchestrate iterative generation + review using Gemini.

    Hard constraints:
      - legal_compliant and brand_compliant must be True in the final result.
      - We never return a non-compliant image.

    Soft constraint:
      - quality_score >= min_quality_score is a target. If no compliant image
        reaches this score within max_iterations, we still return the best
        compliant result we have.

    Parameters
    ----------
    brief:
        Campaign metadata (brand, region, audience) that conditions both
        generation and review.
    generate_fn:
        Callback invoked as:

            current_image = generate_fn(previous_image, previous_feedback)

        where:
          - previous_image is None on the first call, then the last image produced
          - previous_feedback is None on the first call, then the feedback string
            returned by the previous review.

        generate_fn is responsible for optionally passing the previous image and
        feedback into the underlying image-generation prompt (for example, by
        including feedback in the text prompt or attaching the previous image as
        a visual reference to encourage refinements instead of a full restart).
    max_iterations:
        Maximum number of generate → review cycles allowed.
    min_quality_score:
        Minimum acceptable quality score (0–100). If an image reaches this score
        and is compliant, the loop stops early.
    banned_words:
        Optional list of banned words or phrases that should be surfaced to the
        reviewer. When provided, Gemini is instructed to search for these terms
        anywhere in the image and treat them as a legal compliance failure.

    Returns
    -------
    (final_image, last_review_result)
        final_image is the last image generated that met legal & brand
        compliance. It may or may not have met the min_quality_score if the
        loop maxed out.
    """
    last_image: Optional[Image.Image] = None
    last_feedback: Optional[str] = None

    # Track the best compliant image we've seen so far (by quality_score).
    best_compliant_image: Optional[Image.Image] = None
    best_review: Optional[ImageReviewResult] = None

    for iteration in range(max_iterations):
        logging.info(
            "Generation iteration %d / %d (min_quality_score=%d)",
            iteration + 1,
            max_iterations,
            min_quality_score,
            )

        # Ask caller to generate/refine an image, optionally using prior feedback.
        current_image = generate_fn(last_image, last_feedback)

        # Review with Gemini
        review = review_image_with_gemini(
            brief,
            current_image,
            banned_words=banned_words,
        )
        logging.info(
            "Review iteration %d: legal=%s, brand=%s, compliant=%s, score=%d, feedback=%s",
            iteration + 1,
            review.legal_compliant,
            review.brand_compliant,
            review.compliant,
            review.quality_score,
            review.feedback,
            )

        if review.compliant:
            # Track the best compliant image seen so far.
            if best_review is None or review.quality_score > best_review.quality_score:
                best_compliant_image = current_image
                best_review = review

            # Early exit if we hit the quality threshold.
            if review.quality_score >= min_quality_score:
                logging.info(
                    "Stopping early after iteration %d: compliant image reached "
                    "quality_score=%d (threshold=%d).",
                    iteration + 1,
                    review.quality_score,
                    min_quality_score,
                    )
                return current_image, review

        # Prepare for next iteration
        last_image = current_image
        last_feedback = review.feedback

    # After all iterations, we must not return a non-compliant image.
    if best_compliant_image is None or best_review is None:
        raise RuntimeError(
            "Failed to generate a legally and brand-compliant image after "
            f"{max_iterations} iterations."
        )

    # We accept the best compliant image even if its quality_score is below
    # min_quality_score, because compliance is hard and quality is soft.
    return best_compliant_image, best_review
