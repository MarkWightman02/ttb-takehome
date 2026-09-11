# Example label fixtures

Label images and their matching application values, used for regression testing and for trying the tool by hand. Two sets live here and are deliberately kept separate.

**These are regression cases, not an accuracy benchmark.** They are a small, fixed set chosen to catch changes in behavior. Results across them say nothing statistically meaningful about accuracy on real-world label artwork, and are never reported as a combined score.

## The two sets

### Real sample fixtures (6)

`12345`, `ABC`, `FBN`, `MHB`, `WINE`, `brand-label1` — sample TTB label artwork with a same-stem JSON file holding the application values (`12345.jpg` / `12345.json`).

These are the harder, more realistic set. Several legitimately produce `review` or `not_found` results — for example, `FBN` and `MHB` carry no responsible-party cue for the producer name and address, so those are correctly reported as `not_found` rather than guessed. That behavior is the point of keeping them.

### Synthetic fixtures (20)

`T01`–`T20` — generated label images covering spirits, wine, and malt beverages, imported and domestic, single- and multi-panel layouts, and easy through difficult rendering. Every one includes Government Warning text, and their application values intentionally match the visible label text.

Their JSON uses a filename **prefix**, not the full stem: `T01_harbor_ridge_distilling.png` pairs with `T01.json`. `index.json` lists all twenty with their brand, class/type, layout, and difficulty.

`batch_manifest.csv` is a ready-made CSV manifest for these twenty images — upload it with the `T*.png` files to exercise the batch workflow. All twenty rows validate and are verified. See [BATCH_VERIFICATION.md](../docs/BATCH_VERIFICATION.md).

## JSON structure

The synthetic set uses the current field names:

```json
{
  "brand_name": "HARBOR RIDGE DISTILLING",
  "class_type": "STRAIGHT BOURBON WHISKEY",
  "abv": 45,
  "net_contents": "750 ML",
  "producer_name": "HARBOR RIDGE DISTILLING CO.",
  "producer_address": "NEWPORT, RI",
  "imported_product": false,
  "country_origin": null
}
```

The six real fixtures predate that naming and use `imported` and `country_of_origin`, and `ABC.json` uses `brand` rather than `brand_name`. The real-label evaluation runner accepts both spellings, which is why both sets still work unchanged.

## Two quirks worth knowing

- **`FBN.jpg`, `MHB.jpg`, and `WINE.jpg` contain PNG data despite the `.jpg` extension.** The evaluation runner detects the real format, so it handles them correctly. If you upload one of these by hand through a tool that trusts the extension, the API will reject it — the service validates declared type against actual content on purpose. Uploading through the web UI works fine, because the browser reports the true type.
- **`T02`, `T09`, and `T11` print two volume declarations on the label**, in the US-and-metric style common on beer and cider — for example `1 PINT (473 ML)`. Application values must name a single unit (`473 mL`), which is what `batch_manifest.csv` uses; a compound string is rejected by both batch and single-label review. These three fixtures are therefore a good demonstration of conservative comparison: the tool reads *both* printed declarations, they normalize to two slightly different values, and net contents is reported as **Review** rather than matching the one that agrees with the application. Their companion JSON files still record the label's literal compound text, which is why `evaluate_warnings.py` carries a metric-component fallback.

## How the evaluation scripts use these

```sh
python backend/scripts/evaluate_real_labels.py   # the six real fixtures
python backend/scripts/evaluate_warnings.py      # Government Warning checks across all 26
```

`evaluate_real_labels.py` discovers images that have a same-stem JSON file, so it picks up the six real fixtures and skips the prefix-named synthetic set. It runs the full production path — preprocessing, label reading, extraction, comparison — and reports per-field results, call counts, and latency. Add `--json` for complete per-case detail.

A third script, `backend/scripts/evaluate_labels.py`, does not use this directory at all: it generates its own corpus in memory, so it needs no checked-in assets.

See [DEVELOPMENT.md](../docs/DEVELOPMENT.md#evaluation-scripts) for more.

## Trying one by hand

Open the tool, enter the values from a fixture's JSON, and upload the matching image. `T01` is the easiest starting point — it is a clean single-panel label whose values all match. The Quick Start in the [README](../README.md) has the exact values.

These are test artifacts. They are not legally reviewed labels and carry no regulatory meaning.
