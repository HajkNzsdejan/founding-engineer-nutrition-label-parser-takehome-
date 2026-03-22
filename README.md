# Nutrition Label Parser

Takes a folder of product label images and spits out a clean, normalised CSV of nutritional data.

## What I Built

A three-stage pipeline: **extract** (Vision LLM) → **normalise** (static overrides + LLM-suggested names) → **output** (CSV).

```
Sample_images/*.png/*.jpg
        │
        ▼
  ┌─────────────┐     ┌──────────────┐     ┌─────────────┐
  │  extractor   │────▶│  normalizer   │────▶│  CSV output  │
  │  (GPT-4o)    │     │  (overrides)  │     │              │
  └─────────────┘     └──────────────┘     └─────────────┘
        │
        ▼
    .cache/ (JSON per image)
```

The idea is simple: rather than writing brittle OCR pipelines and layout-specific regex for every label format I might encounter, I lean on a vision model that already understands how to read labels — any layout, any language, any background. Then I layer on a lightweight normalisation step to keep the output consistent.

### How to Run

```bash
pip install -r requirements.txt
# Set your OpenAI API key in .env or environment
echo "OPENAI_API_KEY=sk-..." > .env
python3 -m source_code.main
```

Output lands in `sample_output/nutrition_data.csv`.

Options:
- `python3 -m source_code.main /path/to/images` — point at a different image folder
- `python3 -m source_code.main --clear-cache` — wipe cached results and re-extract everything

### Output Schema

| Column | Description |
|--------|-------------|
| `product_image` | Source filename |
| `product_name` | Product name extracted from the label (empty if not visible) |
| `nutrient_name_raw` | Exactly as printed on the label |
| `nutrient_name_standard` | Normalised snake_case English name |
| `amount` | Numeric value |
| `unit` | Standardised unit (mg, g, µg, IU, kcal, kJ) |
| `serving_size` | Serving size text from the label |
| `daily_value_pct` | %DV / %NRV if present |

I extended the brief's schema with three additions:
- **`product_name`** — without it the CSV just says "product_01.png" and you have no idea what you're looking at. Makes the data self-contained and useful standalone.
- **`serving_size`** — shows up on nearly every label. Without it you can't compare across products: "24g protein" means something very different per scoop vs per 100g.
- **`daily_value_pct`** — most labels include %DV or %NRV and it's valuable context for whether an amount is meaningful.

### Results on the Sample Images

| Image | What it is | Result |
|-------|------------|--------|
| product_01.png | MindGuard Nootropic (dark bg, supplement facts) | 7 nutrients extracted |
| product_02.png | Ancient+Brave back (description text only) | Skipped — no nutrition data |
| product_03.png | Brave Immunity (dark bg, nutrition table) | 6 nutrients + %NRV |
| product_04.png | Ancient+Brave front label | Skipped — branding only |
| product_05.png | Ancient+Brave directions panel | Skipped — no nutrition data |
| product_06.png | ProMix Raw Greens front | Skipped — branding only |
| product_07.jpg | Together Health Women's Multi (**dense paragraph text**) | 21 nutrients extracted (caught on retry) |
| product_08.jpg | Together Health front label | Skipped — branding only |
| product_09.png | ProMix Raw Greens (clean table) | 16 nutrients incl. botanicals |
| product_10.png | MindGuard (rotated, dark bg) | 8 nutrients extracted |
| product_11.png | NordHerz Omega-3 (standard table) | 14 nutrients with fatty acid breakdown |
| product_12.png | NordHerz Omega-3 (**circular infographic layout**) | 14 nutrients extracted |
| product_13.png | NordHerz Omega-3 (**German language**, dual-view) | 4 nutrients with German raw names |

90 nutrient rows from 8 images. 5 images correctly identified as having no nutrition data.

---

## Key Decisions

### 1. Vision LLM over Traditional OCR + Regex

Just in these 13 sample images I counted at least 5 distinct layout formats: standard tables, dark-background supplement facts, paragraph-style inline text, a circular infographic, and German-language labels. A traditional OCR pipeline (Tesseract → text → regex parsing) would need layout-specific code for each of these, and every new format encountered at scale would mean writing new parsing rules.

A vision LLM handles all of them with a single prompt. It understands visual layout, reads text in context, handles multiple languages, and can tell the difference between nutrition data and marketing copy. That's a lot of hard problems I don't have to solve myself.

**On cost at scale:** GPT-4o runs about $0.01–0.03 per image. At 10,000 images that's $100–300 — a fraction of what it would cost in engineering time to build and maintain format-specific OCR parsers. And crucially, the LLM approach gets *better* over time as models improve, while regex pipelines only get more brittle as you encounter more formats.

### 2. Hybrid Normalisation (LLM-Suggested + Static Overrides) — for Both Names and Units

This one I went back and forth on. A pure static mapping table ("Ascorbic Acid" → "vitamin_c") sounds clean, but it falls apart fast — you'd need 100+ entries covering every synonym, chemical name, and translation. Miss one and you've got inconsistent data. Add a new product category and you're updating the map again.

Instead, I ask GPT-4o to return both the raw value *and* a suggested standard value — for nutrient names *and* for units — in the same extraction call. The model already knows biochemistry ("Pyridoxine HCL" → "vitamin_b6") and unit conventions ("mcg" → "µg") without me maintaining giant lookup tables.

But I don't fully trust LLM consistency across runs, so there's a small static override map for each — ~30 entries for nutrient names, ~15 for units. If the LLM sometimes says "thiamine" and sometimes "vitamin_b1", the override catches it. Same if it returns "ug" vs "µg".

**The cascade is the same for both names and units:** check static override → use LLM suggestion → fall back to raw value. This consistency makes the normalisation approach easy to understand, easy to extend, and easy to defend.

### 3. Per-Image Processing, No Deduplication

Products 11, 12, and 13 are all the same NordHerz Omega-3 photographed differently. Products 03/04/05 are all Ancient+Brave Immunity. I noticed this but deliberately chose not to deduplicate.

Why? Matching which images belong to the same product is a separate hard problem — it needs fuzzy text matching, brand recognition, maybe even barcode detection. Bolting that on here would add a lot of complexity for marginal gain. Each image is processed independently, and downstream consumers can group and deduplicate however makes sense for their use case.

### 4. Keep All Nutrients, Even Unmapped Ones

Products like MindGuard and ProMix list botanical ingredients (Lion's Mane, Ashwagandha, Wheat Grass) with specific dosage amounts. These don't fit neatly into standard FDA/EU nutrient categories, but they're the *reason people buy these supplements*.

Dropping them would lose genuinely useful data. So the system keeps everything — botanicals get a reasonable snake_case standard name from the LLM, and anyone who only wants conventional nutrients can filter in the CSV.

### 5. Result Caching

Each image's extraction result gets saved as a JSON file in `.cache/`. At 13 images this is a convenience. At 10,000 images it's essential:
- Run fails at image 5,000? Resume from 5,001, not from scratch.
- Re-run the pipeline? Already-processed images are instant.
- New images added to the folder? Only the new ones hit the API.

---

## The Hardest Parts

This section is where I want to be honest about what was genuinely tricky and what I learned while building this.

### Dense paragraph text on textured backgrounds (product_07)

This was the image that broke my first run. The Together Health label crams all its nutrition data into a dense paragraph of tiny text on a low res background: "Vitamin D3 10µg (200%), Vitamin C 25mg (31%), Thiamine 10mg (909%)..."

It's genuinely hard to read — even squinting at it myself I had to zoom in. GPT-4o's first pass consistently returned `has_nutrition_data: false`, which is the same conclusion a quick human glance might reach.

I tried a few things: `detail: high` for higher-resolution processing, adjusting the prompt to mention paragraph-style formats. But the first pass still missed it more often than not.

What actually solved it was a **retry with a more aggressive prompt**. If the first pass says "no data," the system makes one more attempt with a prompt that specifically asks the model to look harder — to check for dense inline text, small print, and unusual formats. That second pass catches product_07 every time, and critically, it doesn't produce false positives for the images that genuinely have no data (products 02, 04, 05, 06, 08 all correctly stay empty after retry).

The cost is one extra API call per "no data" image — negligible. A generic "extract nutrition data" prompt lets the model dismiss borderline images. A prompt that says "look carefully for unusual formats" changes the model's threshold for what counts.

### Distinguishing "no data" from "data I can't read"

Five images had no nutrition data at all — front labels, directions, marketing text. The system needs to confidently say "nothing here" without hallucinating values. But there's a subtle failure mode: what if an image *does* have nutrition data but the model can't read it (blurry, obscured, too small)? That also comes back as "no data."

The two-pass retry approach helps a lot here — the second, more aggressive prompt catches borderline cases like product_07. But it's not a complete solution. If an image is genuinely too blurry or low-res for the model to parse, both passes will return "no data" and the system will silently skip it. In production I'd add an image quality gate upfront, and flag empty results for human review when the image clearly contains a lot of text.

### The circular infographic (product_12)

Product_12 presents its nutrition data as a stylised circular diagram rather than a table. This is exactly the kind of layout that would be a nightmare for OCR + regex — there's no row/column structure to parse. The vision model handled it fine because it understands the visual *semantics*, not just the text. But it did make me wonder: at what point does a "creative" label layout become too abstract for even a vision model? Probably when values are encoded as bar lengths or colour intensities rather than printed numbers.

### The normalisation boundary — how far do you go?

Where do you draw the line between "Vitamin B6" and "Pyridoxine HCL"? They're the same nutrient, but the chemical name tells you the specific *form*, which matters clinically. Same with "Folate" vs "Folic Acid" vs "5-MTHF" — all vitamin B9, but meaningfully different.

I chose to normalise to the common name (`vitamin_b6`, `vitamin_b9`) and preserve the original label text in `nutrient_name_raw`. This means downstream systems can work at either level of specificity. But I acknowledge this loses information — someone might care about the difference between methylcobalamin and cyanocobalamin (both "vitamin_b12"), and the standard name flattens that distinction.

### Non-English labels

Product_13 is entirely in German ("Fischöl-Konzentrat", "davon EPA", "davon DHA"). This worked out of the box because GPT-4o is multilingual. The raw names stay in German, the standard names come back in English. The override map also covers a few common German nutrient terms as a safety net.

But it made me think about scale: if I had labels in Japanese, Arabic, or Thai, would the model handle those equally well? Probably for common nutrients, but I'd want to validate. And there's a question of whether the raw name should include the original script or a transliteration — for this dataset I kept the original.

### Same product, different photos, different results

As I previously mentioned, products 11 and 12 are the same Omega-3 supplement — one photographed as a clean table, the other as a circular infographic. Both extracted 14 nutrients, but with slight differences in how the raw names were captured (e.g., "Of which Saturates" vs "Saturates"). The *amounts* matched, which is what matters, but it shows that raw name consistency across different photos of the same product isn't guaranteed. Another reason deduplication would be nontrivial.

---

## What I Decided Not to Build

- **Test suite** — I chose to spend the time on working code with real output rather than test suites. The normaliser and cache are pure functions that would be straightforward to unit test. The extractor would need mocked API responses. First thing I'd add with more time.

- **Product-level deduplication** — Grouping images of the same product and merging their nutrition data. Interesting problem, but it's really a separate system (product identity matching) bolted onto this one.

- **Confidence scoring** — Rating how confident the system is in each extracted value. The LLM doesn't provide calibrated confidence natively, and bolting on heuristics (image quality scoring, OCR confidence) would add complexity without clear payoff at this stage.

- **Unit conversion** — Converting between units (µg to mg, IU to µg for Vitamin D) for cross-product comparison. This needs nutrient-specific conversion factors and is better owned by whatever system consumes this data.

- **Ingredient list extraction** — The brief mentions images may contain ingredient lists. I deliberately extract only nutrients with numeric amounts, not free-text ingredient lists. Ingredients are a different data type (unstructured text, no amounts/units) and would need a different schema. Worth adding later, but it's a separate problem from nutritional data extraction.

- **Image preprocessing** — Contrast enhancement, deskewing, cropping to the nutrition panel. The vision model handles these well enough raw, and preprocessing adds a dependency on image processing libraries (OpenCV, Pillow) that didn't feel justified for the improvement.

---

## What I'd Do Next

1. **Tests and a golden dataset** — Build a small hand-verified ground truth for 4-5 images. Run the pipeline and diff against it. This catches regressions when I change the prompt or the normalisation logic, and it's the fastest way to build confidence in accuracy.

2. **Structured output mode** — OpenAI's `response_format: json_schema` feature would guarantee valid JSON responses and remove the need for code-fence stripping. I'd probably want to set this up.

3. **Validation layer** — Cross-reference extracted amounts against known reasonable ranges. Vitamin C at 10,000mg or protein at 500g per serving is almost certainly an extraction error. Flagging outliers for human review would catch the LLM mistakes more clearly.

4. **Image quality gating** — Before sending to the API, check image resolution and estimated text density. Low-quality images could be flagged for manual review rather than silently producing wrong output.

5. **Product identity matching** — Group images of the same product and merge their nutrition data. Would need brand/product name extraction and fuzzy matching. Hard to get right, but high value as we could save on costs.

---

## Project Structure

```
source_code/
├── __init__.py
├── main.py          # CLI entry point — orchestrates the pipeline
├── extractor.py     # GPT-4o Vision API — image → structured JSON
├── normalizer.py    # Normalisation cascade — overrides → LLM suggestion → fallback
├── cache.py         # JSON file cache — resume and incremental processing
└── config.py        # Nutrient overrides, unit mappings, constants
sample_output/
└── nutrition_data.csv
Sample_images/       # 13 input images
requirements.txt
.env.example
```
