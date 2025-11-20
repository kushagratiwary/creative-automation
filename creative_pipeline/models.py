from __future__ import annotations

"""
Datamodels used throughout the creative automation pipeline.

These dataclasses are intentionally small and serializable so they can be
constructed from JSON or YAML briefs and passed between modules without
bringing in framework specific dependencies.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class Brand:
    """Basic brand metadata shared across products in a campaign."""

    # Human readable brand name, also surfaced in prompts.
    name: str

    # Primary brand color in hex (for subtle accents in the scene).
    primary_color: str = "#000000"

    # Optional path to a logo image that will be composited onto creatives.
    logo_path: Optional[Path] = None


@dataclass
class Product:
    """Description of a single product that needs ad creatives generated."""

    # Unique slug or identifier used for directory naming, logging, etc.
    id: str

    # Human readable product name that can appear in prompts.
    name: str

    # Default marketing message in the base locale (typically en_US).
    message: str

    # Optional reference image for geometry and appearance.
    image_path: Optional[Path] = None

    # Optional map of locale -> localized marketing message.
    message_localized: Dict[str, str] = field(default_factory=dict)

@dataclass
class LegalConfig:
    """
    Optional legal/compliance configuration for a campaign.

    For now this only carries a list of banned words/phrases that must not
    appear anywhere in the creative (overlay text, packaging, UI text, etc.).
    """
    banned_words: List[str] = field(default_factory=list)

@dataclass
class CampaignBrief:
    """Top level campaign configuration parsed from the brief file."""

    campaign_name: str
    target_region: str
    audience: str

    # Shared brand configuration for the campaign.
    brand: Brand

    # List of products that will each get a full set of creatives.
    products: List[Product]

    # List of banned words
    legal: Optional[LegalConfig] = None
