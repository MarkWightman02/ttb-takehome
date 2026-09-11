# Batch verification

Batch verification is optional. It checks many labels in one sitting using a CSV file plus the matching label images. Every label is verified exactly the same way as in single-label review, so the results mean the same thing.

For single-label use, see [USER_GUIDE.md](USER_GUIDE.md). For error messages, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md#batch-verification).

## When to use it

Use batch when you have several applications to work through and their label images are already saved as files. For one or two labels, single-label review is quicker.

## Workflow

1. Open the tool and select **Batch verification**.
2. Select **Download CSV template**. This gives you a correctly-headed file with one example row.
3. Fill in **one row per application**, replacing the example row.
4. Set `image_filename` in each row to the file name of that application's label image.
5. Select **Choose application CSV** and upload your completed file.
6. Select **Choose label images** and select all the matching image files at once.
7. Review the matches in step 3 of the batch view. Every row shows whether its image was found.
8. Select **Verify Batch**.
9. Review results in the table, or select **Export results CSV**.

Each row can be expanded to show the same detailed result you would see in single-label review.

## Required CSV columns

All nine columns must be present, with exactly these names, in the template's order:

| Column | Meaning | Format | Example | Required |
| --- | --- | --- | --- | --- |
| `image_filename` | File name of this application's label image | File name, with or without a folder path | `label-001.png` | Yes |
| `brand_name` | Brand name from the application | Text | `Stone's Throw` | Yes |
| `class_type` | Class/type designation | Text | `Kentucky Straight Bourbon Whiskey` | Yes |
| `abv` | Alcohol by volume | Number only, greater than 0 and at most 100 | `45` | Yes |
| `net_contents` | Stated net contents | A single volume with its unit | `750 mL` | Yes |
| `producer_name` | Producer/bottler name | Text | `Example Distillery LLC` | Yes |
| `producer_address` | Producer/bottler address | Text | `Louisville, KY` | Yes |
| `imported_product` | Whether the product is imported | `true` or `false` | `false` | Yes |
| `country_origin` | Country of origin | Text | `France` | Only when `imported_product` is `true` |

Notes:

- `abv` is a bare number. Do not include a `%` sign.
- `net_contents` accepts millilitres, litres, US pints, and US fluid ounces — for example `750 mL`, `1 L`, `1 pint`, `12 fl oz`.
- A **compound** value naming two units at once, such as `1 PINT (473 ML)`, is not accepted — enter a single unit, for example `473 mL`. This applies to single-label review as well, which returns a "Net contents must use mL, L, US pint, or US fluid ounce units" error for the same input. Where a label prints both forms, enter either one; the tool reads the label itself independently.
- `imported_product` accepts `true`/`false` in any capitalization; surrounding spaces are trimmed. `yes`, `Y`, and `1` are not accepted.
- Leave `country_origin` empty for domestic products.

The parser handles quoted fields containing commas, escaped quotes, CRLF line endings, a UTF-8 byte-order mark, and blank optional values — so a file exported from Excel or Google Sheets works as-is.

## Example CSV

```csv
image_filename,brand_name,class_type,abv,net_contents,producer_name,producer_address,imported_product,country_origin
label-001.png,Stone's Throw,Kentucky Straight Bourbon Whiskey,45,750 mL,Example Distillery LLC,"Louisville, KY",false,
label-002.png,Casa Verde,Red Wine,13,750 mL,Casa Verde Imports,"Miami, FL",true,Spain
```

Note how an address containing a comma is wrapped in double quotes.

## How filenames are matched

For each row, the `image_filename` value is compared against the names of the images you selected. Before comparing, both sides are normalized identically:

- Any folder path is removed — `labels\front.png` and `labels/front.png` both match a selected file named `front.png`.
- Surrounding whitespace is trimmed.
- Unicode is normalized (NFC), so visually identical accented characters match.
- Capitalization is ignored — `Front.PNG` matches `front.png`.

Nothing else is ignored. The extension must match (`front.jpg` will not match `front.png`), and any other difference in the name is a non-match. Ambiguity is never guessed:

- A row whose image was not selected is reported as an unmatched row.
- Two rows resolving to the same image name are both flagged.
- Selected images that no row refers to are listed as a notice.

## Limits

| Limit | Value |
| --- | --- |
| Maximum rows per batch | 300 |
| Maximum images per selection | 300 |
| Image formats | PNG, JPEG, WebP |
| Maximum image size | 10 MB each |

Labels are verified a couple at a time rather than all at once, so a large batch progresses steadily instead of flooding the service. Progress, the count remaining, and which labels are in flight are shown while it runs. **Stop after current labels** stops scheduling new work while letting in-flight labels finish.

## Row statuses

| Status shown | Meaning |
| --- | --- |
| Ready | Row is valid and its image was matched; not yet verified |
| Queued / Processing | Waiting to be verified, or being verified now |
| Automated checks matched | Everything this tool can check matched |
| Needs review | At least one item needs your attention |
| Contains mismatch | At least one item genuinely differs |
| Invalid | The CSV row itself has a problem — it is not sent for verification |
| Processing failed | The request failed; use **Retry failed items** |
| Not processed | Skipped because the batch was stopped |

Failure is isolated per row: an invalid row or a failed request never stops the rest of the batch.

## Exported results

**Export results CSV** writes one row per batch item with these columns:

| Column | Meaning |
| --- | --- |
| `image_filename` | The image file name from the input row |
| `brand_name` | The brand name from the input row |
| `overall_status` | Row outcome: `match`, `review`, `mismatch`, `processing_error`, `cancelled`, or `validation_error` for a row rejected by the CSV check |
| `brand_status` | Per-field result |
| `class_type_status` | Per-field result |
| `abv_status` | Per-field result |
| `net_contents_status` | Per-field result |
| `producer_name_status` | Per-field result |
| `producer_address_status` | Per-field result |
| `country_origin_status` | Per-field result (`not_applicable` for domestic products) |
| `government_warning_status` | Comprehensive warning status, retained for compatibility — this one still includes the unresolved physical checks, so it reads `review` even on a clean label |
| `automated_warning_status` | The warning result for everything checkable from the image — this is the one to read |
| `manual_physical_confirmation_required` | `true` when physical type size / characters-per-inch still need manual confirmation |
| `duration_ms` | How long that label took to verify |
| `error` | Validation or processing error text, if any |

The distinction between the last three columns matters: `overall_status` of `match` and `automated_warning_status` of `match` mean **everything this tool can check passed**. They do not mean physical compliance was established — `manual_physical_confirmation_required` is the explicit flag for that, and it is `true` for ordinary image uploads. See [USER_GUIDE.md](USER_GUIDE.md#why-physical-measurements-say-manual-confirmation).

Per-field status values are the same five used throughout the tool: `match`, `review`, `mismatch`, `not_found`, `not_applicable`.

## A ready-made example

`examples/batch_manifest.csv` is a filled-in manifest for the twenty synthetic label images in `examples/`. You can upload it together with the `examples/T*.png` files to see the batch flow end to end.

All twenty rows pass validation and are verified. Most report **Automated checks matched**; several deliberately report **Needs review**, which is what those fixtures are for. See [examples/README.md](../examples/README.md).

Three of them (`T02`, `T09`, `T11`) are worth a look: their artwork prints both a US and a metric declaration, such as `1 PINT (473 ML)`. The manifest gives the metric value, the tool reads *both* printed values from the label, and because those normalize to two slightly different numbers it reports net contents as **Review** rather than picking the one that happens to match. That is the conservative behavior described in [VERIFICATION_LOGIC.md](VERIFICATION_LOGIC.md#field-comparison), shown on a real fixture.

## Where batch data lives

Nowhere but your browser. The CSV, the images, and the results are held in the page while you work and are discarded when you reload or close it. The service stores no batch history, no application record, and no image.
