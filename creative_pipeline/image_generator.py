from __future__ import annotations

import logging
import os
from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple, List, Any

from PIL import Image

from .models import CampaignBrief, Product

try:
    # Google Gen AI Python SDK used for text plus image prompting.
    from google import genai  # type: ignore
except Exception:  # pragma: no cover
    genai = None  # type: ignore


_CLIENT: Optional["genai.Client"] = None  # type: ignore


def _get_client() -> "genai.Client":  # type: ignore
    """Lazily create a singleton Google Gen AI client.

    The API key is read from GEMINI_API_KEY or GOOGLE_API_KEY.
    """
    global _CLIENT

    if _CLIENT is not None:
        return _CLIENT

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY or GOOGLE_API_KEY must be set in the environment "
            "for image generation."
        )

    if genai is None:
        raise RuntimeError(
            "google-genai is required for image generation. "
            "Install with: pip install google-genai"
        )

    client = genai.Client(api_key=api_key)  # type: ignore
    _CLIENT = client

    # Do not log the key or prompt, only that the client has been constructed.
    logging.info("Initialized Gemini client for image generation.")
    return client


def _extract_first_image_from_response(response: Any) -> Image.Image:
    """Extract the first inline image from a Google Gen AI response."""
    try:
        for candidate in getattr(response, "candidates", []):
            content = getattr(candidate, "content", None)
            if not content:
                continue
            for part in getattr(content, "parts", []):
                inline_data = getattr(part, "inline_data", None)
                if inline_data and getattr(inline_data, "mime_type", "").startswith("image/"):
                    data = getattr(inline_data, "data", None)
                    if data:
                        return Image.open(BytesIO(data))
    except Exception as exc:  # pragma: no cover - defensive
        logging.error("Failed to parse image from Gemini response: %s", exc)
        raise RuntimeError("Could not extract image from Gemini response") from exc

    raise RuntimeError("No image data found in Gemini response")


def _load_reference_image(product: Product) -> Optional[Image.Image]:
    """Load the product reference image, if available."""
    if product.image_path is None:
        return None

    ref_path = product.image_path
    if not isinstance(ref_path, Path):
        ref_path = Path(ref_path)

    if not ref_path.exists():
        logging.warning(
            "Reference product image not found at %s; generating visual from prompt only.",
            ref_path,
        )
        return None

    try:
        img = Image.open(ref_path).convert("RGB")
        logging.info("Loaded reference product image from %s", ref_path)
        return img
    except Exception as exc:  # pragma: no cover
        logging.warning("Failed to load reference product image: %s", exc)
        return None


def _build_prompt(
        brief: CampaignBrief,
        product: Product,
        size: Tuple[int, int],
        reference_image: Optional[Image.Image],
) -> str:
    """Construct a prompt for the image model using the YAML brief."""
    canvas_w, canvas_h = size
    if canvas_w == canvas_h:
        orientation = "square"
    elif canvas_w > canvas_h:
        orientation = "landscape"
    else:
        orientation = "portrait"

    ref_dims_text = ""
    if reference_image is not None:
        rw, rh = reference_image.size
        ref_dims_text = (
            f"The product in the attached reference photo appears within a "
            f"rectangle approximately {rw} pixels wide by {rh} pixels tall. "
            "Use this as the ground truth for the product's width-to-height ratio. "
        )

    campaign_context = (
        f"You are creating a hero product image for the marketing campaign "
        f"'{brief.campaign_name}'. The brand is '{brief.brand.name}'. "
        f"The campaign runs in {brief.target_region} and targets "
        f"{brief.audience}. Use exactly this region and audience as described; "
        f"do not invent or change them. This information should guide the "
        f"overall environment, mood, and lighting."
    )

    product_context = (
        f"Focus on the product '{product.name}' as the clear main subject. "
        "Render it with realistic materials, lighting, and correct proportions. "
        "The generated product must look like the same physical device as in "
        "the reference photo so that it is instantly recognizable."
    )

    message_guidance = (
        "The core marketing message for this creative is:\n"
        f"\"{product.message}\"\n"
        "Use this ONLY as guidance for what aspects of the product to emphasize "
        "and for the overall mood and setting of the image. Reflect any scene, "
        "environment, seasonal cues, or use-cases that are described in this "
        "message. Do NOT render any of these words or any other text in the "
        "picture."
    )

    geometry_constraints = (
        "PRODUCT GEOMETRY RULES (CRITICAL AND NON-NEGOTIABLE):\n"
        f"- {ref_dims_text}"
        "- You must preserve the exact physical proportions and overall "
        "silhouette of the product from the reference photo.\n"
        "- The product's width and height must always be scaled UNIFORMLY. "
        "You must NEVER scale width and height independently.\n"
        "- Do NOT stretch, elongate, compress, or reshape the product in any way. "
        "The body shape, panel, and width-to-height ratio must remain "
        "consistent with the reference.\n"
        "- If the canvas aspect ratio (such as tall 9:16 portrait or wide 16:9 "
        "landscape) leaves extra space after placing the product with correct "
        "proportions, fill ONLY with background elements (room, environment, "
        "decor, table, floor, etc.). Do NOT change the product's shape to fill "
        "the space.\n"
        "- You MAY choose a different camera angle or composition if it looks "
        "more cinematic or appealing, but the product's geometry must still "
        "match the real device from the reference image."
    )

    layout_and_brand_instructions = (
        "COMPOSITION, BOTTOM SAFE-ZONE, AND BRAND COLOR USAGE:\n"
        f"- Orientation: {orientation}.\n"
        f"- Canvas size in pixels: {canvas_w}x{canvas_h}.\n"
        "- Place the product comfortably in the upper two-thirds of the frame so "
        "it is clearly readable and not cropped off.\n"
        "- The lower ~25% of the image should remain visually calm and "
        "uncluttered, but it must still look like part of the real scene: "
        "for example, a continuation of the table surface, floor, sofa edge, "
        "carpet, or a softly blurred foreground.\n"
        "- Avoid using flat monotone color blocks or abstract gradients in this "
        "bottom area. It must look photographic and consistent with the rest of "
        "the environment.\n"
        "- This region should be slightly darker or more neutral than the main "
        "scene so a semi-translucent white text panel placed there remains "
        "clearly legible.\n"
        "- Keep the bottom-right corner especially clean and simple so a small "
        "white logo card can be placed there later without overlapping complex "
        "details.\n"
        f"- BRAND COLOR ACCENTS: Use the brand primary color "
        f"{brief.brand.primary_color} in subtle, tasteful accents within the "
        "environment. Examples include:\n"
        "  • A soft rim-light or ambient glow on the background.\n"
        "  • Gentle reflections or a faint gradient accent on nearby surfaces.\n"
        "  • A small decor object, LED indicator, or UI glow.\n"
        "  Do NOT use the brand color as a large solid block or dominant region, "
        "and do NOT overpower the product photography. These accents must be "
        "minimal and integrated naturally into the scene."
    )

    strict_no_text_instructions = (
        "VISUAL CONSTRAINTS (CRITICAL):\n"
        "- Do NOT render any words, letters, numbers, captions, user-interface "
        "elements, dialog boxes, or call-to-action buttons anywhere in the image.\n"
        "- Do NOT draw any brand logos or logotypes as separate graphic elements. "
        "Only markings physically printed on the product in the reference photo "
        "are allowed.\n"
        "- Do NOT add simulated user interfaces, app screens, or menus.\n"
        "- The final result must look like a clean standalone product photograph "
        "that we will later overlay text and the brand logo onto programmatically."
    )

    return (
            campaign_context
            + "\n\n"
            + product_context
            + "\n\n"
            + message_guidance
            + "\n\n"
            + geometry_constraints
            + "\n\n"
            + layout_and_brand_instructions
            + "\n\n"
            + strict_no_text_instructions
    )


def _resolve_image_model_and_size(size: Tuple[int, int]) -> Tuple[str, Tuple[int, int]]:
    """Resolve which image model to call and what size to request."""
    default_model = os.environ.get(
        "GEMINI_IMAGE_MODEL",
        "gemini-2.5-flash-image-preview",
    )
    return default_model, size


def generate_base_image(
        brief: CampaignBrief,
        product: Product,
        size: Tuple[int, int],
) -> Image.Image:
    """Generate a background image for a product using the Google GenAI image API."""
    if genai is None:
        raise RuntimeError(
            "google-genai is required for image generation. "
            "Install with: pip install google-genai"
        )

    client = _get_client()

    # Load reference product image if available first.
    reference_image = _load_reference_image(product)

    # Build an aspect-aware, geometry- and layout-constrained prompt.
    prompt = _build_prompt(brief, product, size, reference_image)

    contents: List[Any] = [prompt]
    if reference_image is not None:
        contents.append(reference_image)

    image_model, request_size = _resolve_image_model_and_size(size)

    logging.info(
        "Calling image model %s for product %s with canvas %sx%s",
        image_model,
        product.id,
        request_size[0],
        request_size[1],
    )

    try:
        response = client.models.generate_content(
            model=image_model,
            contents=contents,
        )
    except Exception as exc:
        raise RuntimeError(f"Gemini image generation failed: {exc}") from exc

    img = _extract_first_image_from_response(response)

    # Ensure final canvas size matches downstream expectations
    target_w, target_h = request_size
    if img.size != (target_w, target_h):
        img = img.resize((target_w, target_h), Image.LANCZOS)

    return img
