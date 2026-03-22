"""
Normalization: applies static overrides to raw extraction results.

Both nutrient names and units use the same hybrid approach:
  1. Check static override map (catches known inconsistencies)
  2. Use the LLM-suggested standard value (leverages model knowledge)
  3. Fallback: clean up the raw value

This keeps the approach consistent and defensible — the LLM handles the
long tail of synonyms and translations, while static overrides enforce
determinism for the most important values.
"""

import re

from source_code.config import NUTRIENT_NAME_OVERRIDES, UNIT_MAP


def _to_snake_case(text: str) -> str:
    """
    Convert a string to lowercase snake_case, stripping non-alphanumeric characters.

    :param text: Raw input string (e.g. "Vitamin B12", "Pyridoxine HCL").
    :return: Cleaned snake_case string (e.g. "vitamin_b12", "pyridoxine_hcl").
    """
    text = text.strip()
    text = re.sub(r"[^a-zA-Z0-9]+", " ", text)
    text = text.strip().lower()
    text = re.sub(r"\s+", "_", text)
    return text


def normalize_nutrient_name(raw_name: str, llm_standard: str | None = None) -> str:
    """
    Resolve a nutrient's standard name using the normalization cascade:
      1. Static override by raw name
      2. Static override by LLM-suggested name
      3. LLM suggestion as-is
      4. Fallback: snake_case raw name

    :param raw_name: Nutrient name exactly as printed on the label.
    :param llm_standard: LLM-suggested standard name, if available.
    :return: Canonical lowercase standard name (e.g. "vitamin_c").
    """
    raw_lower = _to_snake_case(raw_name)

    # 1. Override by raw name
    if raw_lower in NUTRIENT_NAME_OVERRIDES:
        return NUTRIENT_NAME_OVERRIDES[raw_lower]

    # 2. Override by LLM-suggested name
    if llm_standard:
        llm_lower = llm_standard.lower().strip()
        if llm_lower in NUTRIENT_NAME_OVERRIDES:
            return NUTRIENT_NAME_OVERRIDES[llm_lower]
        # 3. Use LLM suggestion as-is
        return llm_lower

    # 4. Fallback
    return raw_lower


def normalize_unit(unit_raw: str, unit_standard_llm: str | None = None) -> str:
    """
    Resolve a unit using the same cascade as nutrient names:
      1. Static override by raw unit
      2. Static override by LLM-suggested unit
      3. LLM suggestion as-is
      4. Fallback: raw unit stripped

    :param unit_raw: Unit string exactly as printed on the label (e.g. "milligrams").
    :param unit_standard_llm: LLM-suggested standard unit, if available.
    :return: Canonical unit abbreviation (e.g. "mg", "µg", "IU").
    """
    if not unit_raw and not unit_standard_llm:
        return ""

    # 1. Override by raw unit
    if unit_raw:
        raw_lookup = unit_raw.strip().lower()
        if raw_lookup in UNIT_MAP:
            return UNIT_MAP[raw_lookup]

    # 2. Override by LLM-suggested unit
    if unit_standard_llm:
        llm_lookup = unit_standard_llm.strip().lower()
        if llm_lookup in UNIT_MAP:
            return UNIT_MAP[llm_lookup]
        # 3. Use LLM suggestion as-is
        return unit_standard_llm.strip()

    # 4. Fallback
    return unit_raw.strip() if unit_raw else ""


def normalize_results(extraction_results: list[dict]) -> list[dict]:
    """
    Flatten extraction results into a list of row dicts ready for CSV output.
    Each nutrient in each product becomes one row.

    :param extraction_results: List of per-image extraction dicts from the LLM.
    :return: List of flat row dicts, one per nutrient, with normalized names and units.
    """
    rows = []
    for result in extraction_results:
        product_image = result.get("product_image", "unknown")
        product_name = result.get("product_name") or ""
        serving_size = result.get("serving_size") or ""

        for nutrient in result.get("nutrients", []):
            raw_name = nutrient.get("nutrient_name_raw", "")
            standard_name = normalize_nutrient_name(
                raw_name, nutrient.get("nutrient_name_standard")
            )
            unit = normalize_unit(
                nutrient.get("unit_raw", nutrient.get("unit", "")),
                nutrient.get("unit_standard"),
            )

            rows.append({
                "product_image": product_image,
                "product_name": product_name,
                "nutrient_name_raw": raw_name,
                "nutrient_name_standard": standard_name,
                "amount": nutrient.get("amount"),
                "unit": unit,
                "serving_size": serving_size,
                "daily_value_pct": nutrient.get("daily_value_pct"),
            })

    return rows
