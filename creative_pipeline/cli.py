# cli.py
import argparse
import logging
import sys
from pathlib import Path

from .brief_loader import load_brief
from .compliance_and_review import summarize_brand_compliance
from .processor import generate_creatives_for_product


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate marketing creatives from a YAML campaign brief."
    )
    parser.add_argument(
        "--brief",
        required=True,
        type=Path,
        help="Path to campaign brief YAML file.",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Directory where generated creatives will be written.",
    )
    parser.add_argument(
        "--log",
        required=False,
        type=Path,
        help="Optional path to a log file.",
    )
    parser.add_argument(
        "--locale",
        default="en_US",
        help="Locale for message_localized (e.g. en_US, fr_CA). Defaults to en_US.",
    )

    # If no arguments were supplied, show the help screen instead of failing
    # with a cryptic missing argument error.
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    return parser.parse_args()


def configure_logging(log_path: Path | None) -> None:
    """
    Configure basic logging to stderr and optionally to a file.

    The format is kept simple so logs can be tailed during a demo while still
    being parseable if you later ship them to a log aggregation system.
    """
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_path, encoding="utf-8"))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
        handlers=handlers,
    )


def main() -> None:
    """
    Entry point for the CLI module.

    - Loads the campaign brief.
    - Logs basic brand compliance signals.
    - Iterates over products and generates creatives for each one.
    """
    args = parse_args()
    configure_logging(args.log)

    logging.info("Loading campaign brief from %s", args.brief)
    brief = load_brief(args.brief)

    logging.info(
        "Loaded brief '%s' for region '%s', audience '%s'. Products: %s",
        brief.campaign_name,
        brief.target_region,
        brief.audience,
        [p.id for p in brief.products],
    )

    compliance_summary = summarize_brand_compliance(brief)
    logging.info(
        "Brand compliance: logo_present=%s, brand_color_defined=%s",
        compliance_summary["logo_present"],
        compliance_summary["brand_color_defined"],
    )

    output_root: Path = args.output
    output_root.mkdir(parents=True, exist_ok=True)

    for product in brief.products:
        generate_creatives_for_product(
            product=product,
            brief=brief,
            output_root=output_root,
            locale=args.locale,
        )

    logging.info("Creative generation complete.")


if __name__ == "__main__":
    main()
