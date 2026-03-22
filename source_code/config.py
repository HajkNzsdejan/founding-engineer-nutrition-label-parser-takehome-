"""
Configuration: constants, nutrient name overrides, and unit mappings.

Design choice: We do NOT maintain a massive synonym dictionary. The LLM returns
both raw and suggested standard names during extraction. This override map only
corrects known inconsistencies where the LLM might vary between runs.
"""

import os

# --- API Configuration ---
MODEL = "gpt-4o"
MAX_TOKENS = 4096
MAX_CONCURRENT_REQUESTS = int(os.environ.get("MAX_CONCURRENT_REQUESTS", "5"))
MAX_RETRIES = 3

# --- File Handling ---
SUPPORTED_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
CACHE_DIR = ".cache"

# --- Nutrient Name Overrides ---
# Small curated map for enforcing consistency on key nutrients where the LLM
# might return different standard names across runs. Keys are lowercased raw
# names (or LLM-suggested names); values are the canonical standard name.
#
# The normalization cascade is:
#   1. Check NUTRIENT_NAME_OVERRIDES for the raw name
#   2. If miss, check NUTRIENT_NAME_OVERRIDES for the LLM-suggested name
#   3. If miss, use the LLM-suggested name as-is
#   4. If no LLM suggestion, snake_case the raw name
NUTRIENT_NAME_OVERRIDES = {
    # Energy — ensure consistent naming regardless of label format
    "energy": "energy",
    "calories": "energy",
    "brennwert": "energy",

    # Macronutrients
    "protein": "protein",
    "eiweiss": "protein",
    "eiweiß": "protein",
    "total fat": "total_fat",
    "fett": "total_fat",
    "total_carbohydrate": "total_carbohydrate",
    "carbohydrate": "total_carbohydrate",
    "carbohydrates": "total_carbohydrate",
    "kohlenhydrate": "total_carbohydrate",

    # Vitamins — enforce Bx naming for chemical synonyms.
    # Includes both short forms ("thiamine") and full compound names
    # ("thiamine_mononitrate") since labels use both.
    "vitamin_b1": "vitamin_b1",
    "thiamine": "vitamin_b1",
    "thiamin": "vitamin_b1",
    "thiamine_mononitrate": "vitamin_b1",
    "thiamin_mononitrate": "vitamin_b1",
    "vitamin_b2": "vitamin_b2",
    "riboflavin": "vitamin_b2",
    "vitamin_b3": "vitamin_b3",
    "niacin": "vitamin_b3",
    "niacinamide": "vitamin_b3",
    "nicotinamide": "vitamin_b3",
    "vitamin_b5": "vitamin_b5",
    "pantothenic_acid": "vitamin_b5",
    "vitamin_b6": "vitamin_b6",
    "pyridoxine": "vitamin_b6",
    "pyridoxine_hcl": "vitamin_b6",
    "pyridoxine_hydrochloride": "vitamin_b6",
    "vitamin_b7": "vitamin_b7",
    "biotin": "vitamin_b7",
    "vitamin_b9": "vitamin_b9",
    "folate": "vitamin_b9",
    "folic_acid": "vitamin_b9",
    "vitamin_b12": "vitamin_b12",
    "methylcobalamin": "vitamin_b12",
    "cyanocobalamin": "vitamin_b12",
    "cobalamin": "vitamin_b12",
    "vitamin_c": "vitamin_c",
    "ascorbic_acid": "vitamin_c",
    "vitamin_d": "vitamin_d",
    "vitamin_d3": "vitamin_d",
    "cholecalciferol": "vitamin_d",
    "vitamin_e": "vitamin_e",
    "d_alpha_tocopherol": "vitamin_e",
    "alpha_tocopherol": "vitamin_e",
    "vitamin_k": "vitamin_k",
    "vitamin_k2": "vitamin_k",
    "vitamin_a": "vitamin_a",
    "retinol": "vitamin_a",
    "beta_carotene": "vitamin_a",

    # Omega fatty acids — ensure consistent naming
    "epa": "epa",
    "eicosapentaenoic_acid": "epa",
    "dha": "dha",
    "docosahexaenoic_acid": "dha",
}

# --- Unit Mapping ---
# Standardizes unit strings to canonical abbreviations.
UNIT_MAP = {
    # Already standard — pass through
    "mg": "mg",
    "g": "g",
    "µg": "µg",
    "iu": "IU",
    "IU": "IU",
    "kcal": "kcal",
    "kj": "kJ",
    "kJ": "kJ",
    "ml": "ml",

    # Variations
    "milligrams": "mg",
    "milligram": "mg",
    "grams": "g",
    "gram": "g",
    "micrograms": "µg",
    "microgram": "µg",
    "mcg": "µg",
    "ug": "µg",
    "μg": "µg",
    "kilocalories": "kcal",
    "kcals": "kcal",
    "calories": "kcal",
    "cal": "kcal",
    "kilojoules": "kJ",
    "milliliters": "ml",
    "milliliter": "ml",
    "liters": "L",
    "liter": "L",
    "l": "L",
}
