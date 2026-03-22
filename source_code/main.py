"""
CLI entry point: orchestrates extraction, normalization, and CSV output.

Usage:
    python -m source_code.main                    # default: Sample_images/
    python -m source_code.main /path/to/images    # custom image directory
    python -m source_code.main --clear-cache      # clear cached results and re-run
"""

import asyncio
import csv
import logging
import sys
from pathlib import Path

from source_code.cache import clear_cache
from source_code.extractor import extract_all
from source_code.normalizer import normalize_results

OUTPUT_FIELDS = [
    "product_image",
    "product_name",
    "nutrient_name_raw",
    "nutrient_name_standard",
    "amount",
    "unit",
    "serving_size",
    "daily_value_pct",
]


def main() -> None:
    """
    CLI entry point: loads environment, runs extraction, normalizes results,
    and writes the output CSV.

    :return: None.
    """
    from dotenv import load_dotenv
    load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    image_dir = Path("Sample_images")
    output_dir = Path("sample_output")
    output_path = output_dir / "nutrition_data.csv"

    # Parse CLI args
    args = sys.argv[1:]
    if "--clear-cache" in args:
        clear_cache()
        args.remove("--clear-cache")
    if args:
        image_dir = Path(args[0])

    if not image_dir.exists():
        logging.error(f"Image directory not found: {image_dir}")
        sys.exit(1)

    # Extract
    results = asyncio.run(extract_all(image_dir))
    if not results:
        logging.warning("No nutrition data extracted from any image")
        sys.exit(0)

    # Normalize
    rows = normalize_results(results)
    logging.info(f"Produced {len(rows)} nutrient rows from {len(results)} images")

    # Write CSV
    output_dir.mkdir(exist_ok=True)
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    logging.info(f"Output written to {output_path}")


if __name__ == "__main__":
    main()
