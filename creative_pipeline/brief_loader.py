from __future__ import annotations

"""
Helpers for loading a campaign brief from YAML or JSON into strongly typed
dataclasses.

The expected schema is documented in the README and mirrored in the
CampaignBrief, Brand, and Product models.
"""

import json
from pathlib import Path
from typing import Union

import yaml

from .models import Brand, CampaignBrief, Product, LegalConfig
from .utils import slugify


def load_brief(path: Union[str, Path]) -> CampaignBrief:
    """
    Load a campaign brief from a YAML or JSON file and construct a CampaignBrief.

    The function:
      - Accepts .yml, .yaml, or .json files.
      - Validates that at least one product is present.
      - Ensures each product has a stable id and default message.
      - Normalizes string paths into Path objects for images and logos.

    Parameters
    ----------
    path:
        Filesystem path to the brief document.

    Returns
    -------
    CampaignBrief
        Parsed and validated brief object that can be used by downstream
        modules such as image generation and processing.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Brief file not found: {path}")

    # Support both YAML and JSON so the caller can choose their preferred format.
    with path.open("r", encoding="utf-8") as f:
        if path.suffix.lower() in {".yml", ".yaml"}:
            raw = yaml.safe_load(f)
        else:
            raw = json.load(f)

    products_data = raw.get("products") or []
    if len(products_data) < 1:
        raise ValueError("Brief must contain at least one product.")

    products = []
    for p in products_data:
        name = p.get("name")
        msg = p.get("message")
        if not name or not msg:
            raise ValueError("Each product must have 'name' and 'message' fields.")

        # Fall back to a slug based on the name if id is not provided.
        pid = p.get("id") or slugify(name)
        image_path = p.get("image_path")
        image_path = Path(image_path) if image_path else None

        message_localized = p.get("message_localized") or {}

        products.append(
            Product(
                id=pid,
                name=name,
                message=msg,
                image_path=image_path,
                message_localized=message_localized,
            )
        )

    brand_data = raw.get("brand") or {}
    brand = Brand(
        name=brand_data.get("name", "Brand"),
        primary_color=brand_data.get("primary_color", "#222222"),
        logo_path=Path(brand_data["logo_path"]) if brand_data.get("logo_path") else None,
    )

    # Optional legal section (legal.banned_words).
    legal_data = raw.get("legal") or {}
    legal = None
    if legal_data:
        banned_words_raw = legal_data.get("banned_words") or []
        # Normalize to strings
        banned_words = [str(w) for w in banned_words_raw]
        legal = LegalConfig(banned_words=banned_words)


    brief = CampaignBrief(
        campaign_name=raw.get("campaign_name", "Campaign"),
        target_region=raw.get("target_region", "Unknown"),
        audience=raw.get("audience", "Unknown"),
        brand=brand,
        products=products,
        legal=legal,
    )
    return brief
