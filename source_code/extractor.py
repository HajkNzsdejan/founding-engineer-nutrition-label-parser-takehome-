"""
Vision LLM extraction: sends product label images to GPT-4o and receives
structured nutritional data as JSON.

Each image is processed independently with async concurrency controlled by
a semaphore. Results are cached immediately after extraction so that failures
mid-run don't lose progress.
"""

import asyncio
import base64
import json
import logging
import re
from pathlib import Path

from openai import AsyncOpenAI

from source_code.cache import get_cached_result, save_result
from source_code.config import (
    MAX_CONCURRENT_REQUESTS,
    MAX_RETRIES,
    MAX_TOKENS,
    MODEL,
    SUPPORTED_EXTENSIONS,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a nutrition label data extraction system. You will be given an image of a product label.

Your task:
1. Determine if the image contains nutritional information with numeric values. This includes: nutrition facts panels, supplement facts tables, nutrition information sections, AND paragraph-style product information text that lists nutrients with amounts (e.g., "Vitamin D3 10µg (200%), Vitamin C 25mg (31%)...").
2. If NO nutritional data with numeric amounts is present (e.g., the image shows only branding, a front label, directions, or marketing text without nutrient amounts), respond with exactly: {"has_nutrition_data": false}
3. If YES, extract ALL nutrients listed with their amounts and units.

Rules for extraction:
- "product_name": Extract the product name/title visible on the label (e.g., "NordHerz Omega-3", "Brave Immunity"). If not visible, use null.
- "nutrient_name_raw": Extract the nutrient name EXACTLY as printed on the label (preserve original language, spelling, capitalization)
- "nutrient_name_standard": Provide a lowercase snake_case standardized English name (e.g., "Ascorbic Acid" → "vitamin_c", "Pyridoxine HCL" → "vitamin_b6", "Fett" → "total_fat", "Eiweiß" → "protein")
- "amount": Extract the numeric amount as a number (not a string). If a range like "< 0.1", use 0.1. If no numeric amount, use null.
- "unit_raw": Extract the unit EXACTLY as written on the label
- "unit_standard": Provide the standard abbreviation (g, mg, µg, IU, kcal, kJ, ml). Convert long forms: "milligrams" → "mg", "micrograms" → "µg", "mcg" → "µg"
- If a % Daily Value / %NRV / %NRI / %RI column exists, extract that percentage as a number
- Extract the serving size text exactly as written
- For energy values that show both kcal and kJ, extract BOTH as separate entries
- Include ALL nutrients, vitamins, minerals, herbs, botanicals, and proprietary blend components that have numeric values
- Do NOT extract ingredients that lack numeric nutritional values
- If text is in a non-English language, still extract raw names exactly as written, but provide English standard names and units

Respond with ONLY valid JSON in this exact format:
{
  "has_nutrition_data": true,
  "product_name": "string or null",
  "serving_size": "string or null",
  "nutrients": [
    {
      "nutrient_name_raw": "string",
      "nutrient_name_standard": "string",
      "amount": number_or_null,
      "unit_raw": "string",
      "unit_standard": "string",
      "daily_value_pct": number_or_null
    }
  ]
}"""

USER_PROMPT = "Extract all nutritional data from this product label image."

# More aggressive prompt for retry when first pass finds nothing — catches dense
# paragraph-style labels and low-contrast text that the model might dismiss.
RETRY_PROMPT = (
    "Look very carefully at this image. It may contain nutritional information "
    "in an unusual format — dense paragraph text, small print, or inline text "
    "listing nutrients with amounts. If there are ANY nutrient names with numeric "
    "values and units anywhere in the image, extract them."
)


def _encode_image(image_path: Path) -> tuple[str, str]:
    """
    Read an image file and return its base64-encoded contents with media type.

    :param image_path: Path to the image file on disk.
    :return: Tuple of (base64-encoded data string, MIME media type string).
    """
    suffix = image_path.suffix.lower()
    media_type = "image/jpeg" if suffix in (".jpg", ".jpeg") else f"image/{suffix.lstrip('.')}"
    with open(image_path, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")
    return data, media_type


def _parse_response(raw_text: str, image_name: str) -> dict:
    """
    Parse the LLM's JSON response. Strips markdown code fences if present.

    :param raw_text: Raw text content from the LLM response.
    :param image_name: Source image filename, used for error messages.
    :return: Parsed extraction dict.
    :raises ValueError: If the response is not valid JSON or missing required keys.
    """
    text = raw_text.strip()
    # Strip markdown code fences: ```json ... ``` or ``` ... ```
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    text = text.strip()

    try:
        result = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON for {image_name}: {e}\nRaw: {text[:500]}")

    if "has_nutrition_data" not in result:
        raise ValueError(f"Missing 'has_nutrition_data' key for {image_name}")

    return result


async def _call_api(
    client: AsyncOpenAI,
    semaphore: asyncio.Semaphore,
    b64_data: str,
    media_type: str,
    user_prompt: str,
    image_name: str,
) -> dict | None:
    """
    Make a single API call with retry on transient errors.

    :param client: Async OpenAI client instance.
    :param semaphore: Concurrency limiter for parallel requests.
    :param b64_data: Base64-encoded image data.
    :param media_type: MIME type of the image (e.g. "image/png").
    :param user_prompt: The user-role prompt text to send alongside the image.
    :param image_name: Source image filename, used for logging.
    :return: Parsed extraction dict, or None if all attempts fail.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with semaphore:
                response = await client.chat.completions.create(
                    model=MODEL,
                    max_tokens=MAX_TOKENS,
                    temperature=0,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": user_prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:{media_type};base64,{b64_data}",
                                        "detail": "high",
                                    },
                                },
                            ],
                        },
                    ],
                )
            return _parse_response(response.choices[0].message.content, image_name)

        except ValueError as e:
            logger.error(f"{e}")
            return None
        except Exception as e:
            if attempt < MAX_RETRIES:
                wait = 2**attempt
                logger.warning(f"Attempt {attempt}/{MAX_RETRIES} failed for {image_name}: {e}. Retrying in {wait}s...")
                await asyncio.sleep(wait)
            else:
                logger.error(f"All {MAX_RETRIES} attempts failed for {image_name}: {e}")
                return None
    return None


async def extract_nutrition_from_image(
    client: AsyncOpenAI,
    image_path: Path,
    semaphore: asyncio.Semaphore,
) -> dict | None:
    """
    Send a single image to GPT-4o Vision API and return the parsed result.

    If the first pass returns has_nutrition_data=false, retries once with a
    more explicit prompt — catches dense paragraph-style labels that the
    model might dismiss on a quick read.

    :param client: Async OpenAI client instance.
    :param image_path: Path to the image file to process.
    :param semaphore: Concurrency limiter for parallel requests.
    :return: Parsed extraction dict, or None if extraction fails.
    """
    image_name = image_path.name

    # Check cache first
    cached = get_cached_result(image_name)
    if cached is not None:
        logger.info(f"Cache hit: {image_name}")
        return cached

    # Encode image
    try:
        b64_data, media_type = _encode_image(image_path)
    except OSError as e:
        logger.error(f"Cannot read {image_name}: {e}")
        return None

    # First pass
    result = await _call_api(client, semaphore, b64_data, media_type, USER_PROMPT, image_name)

    # If first pass found nothing, retry with a more explicit prompt.
    # Cost: one extra API call for images that genuinely have no data.
    # Benefit: catches dense/unusual formats that the model dismissed.
    if result and not result.get("has_nutrition_data", False):
        logger.info(f"Retrying {image_name} with detailed prompt...")
        retry_result = await _call_api(client, semaphore, b64_data, media_type, RETRY_PROMPT, image_name)
        if retry_result and retry_result.get("has_nutrition_data", False):
            logger.info(f"Retry succeeded for {image_name}")
            result = retry_result

    # Cache the final result
    if result is not None:
        save_result(image_name, result)

    return result


async def extract_all(image_dir: Path) -> list[dict]:
    """
    Process all images in a directory concurrently.

    :param image_dir: Path to the directory containing product label images.
    :return: List of extraction result dicts (only images with nutrition data).
    """
    client = AsyncOpenAI()  # Uses OPENAI_API_KEY env var
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    image_paths = sorted(
        p for p in image_dir.iterdir()
        if p.suffix.lower() in SUPPORTED_EXTENSIONS
    )

    if not image_paths:
        logger.warning(f"No images found in {image_dir}")
        return []

    logger.info(f"Processing {len(image_paths)} images (concurrency: {MAX_CONCURRENT_REQUESTS})")

    tasks = [
        extract_nutrition_from_image(client, path, semaphore)
        for path in image_paths
    ]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    results = []
    for path, result in zip(image_paths, raw_results):
        if isinstance(result, Exception):
            logger.error(f"Unexpected error for {path.name}: {result}")
        elif result is None:
            logger.warning(f"No result for {path.name}")
        elif not result.get("has_nutrition_data", False):
            logger.info(f"Skipped {path.name}: no nutrition data detected")
        else:
            result["product_image"] = path.name
            results.append(result)
            logger.info(f"Extracted {len(result.get('nutrients', []))} nutrients from {path.name}")

    logger.info(f"Successfully extracted data from {len(results)}/{len(image_paths)} images")
    return results
