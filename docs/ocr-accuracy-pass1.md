# OCR accuracy experiments — Pass 1

Baseline: clean `feature/ocr-accuracy-pass` at `a521177`. This is an accuracy
engineering pass; Docker/deployment validation and the comprehensive audit are
reserved for Pass 2. No frontend, API schema, batch, or full-image preprocessing
changes were needed.

## Findings and adopted changes

- **Crop geometry and segmentation:** `12345` full-image TSV reports `1234.` in
  `(87,409,788,323)` and `IMPORTS` in `(399,763,454,67)`. The old crop ended at
  x=938 and visibly clipped the final digit. Its crop OCR returned `1234:` even
  with about 91% Tesseract confidence. Display text with a much smaller legible
  following line now receives a margin based on the large line height. PSM 6
  recovers `12345` but omits the small line; that independently recognized line
  is retained with explicit provenance. The resulting candidate is
  `12345 IMPORTS`. Runtime rules use geometry/confidence, never these coordinates,
  strings, or fixture names. Expanded crops that reach localized warning pixels
  are rejected.
- **Excessive local text size:** upscaling the whole image helps small print but
  leaves some display glyphs too large for reliable local recognition. Brand/type
  crops with median TSV word height above 96 pixels are resized to about 48
  pixels with Lanczos, then autocontrasted without another sharpening pass.
  This recovers MHB's actual `&`, improves the confidence of its class/type
  content tokens, and preserves ABC. Mixed-size display/small-line crops retain
  their existing scale so the smaller evidence is not erased. Volume crops keep
  their proven representation.
- **Refinement acceptance:** the old implementation ranked comparison statuses
  (`match` above `review`) when deciding whether to select crop OCR. Selection
  now happens before application comparison. It requires a single candidate,
  sufficient content-token confidence, adequate text completeness and continuity
  with initial OCR, and improved mean or weakest-token confidence. It may select
  stronger evidence that produces a mismatch. Decorative tokens outside the
  candidate do not determine candidate quality. Unknown content-token confidence
  is treated conservatively.
- **Triggering and candidate ranking:** the crop uses image-ranked candidates,
  not the comparison's closest application value. Weak content tokens also
  trigger refinement when an application happens to repeat an OCR misread.
  This adds one unselected WINE class/type check in this set.
- **Normalization defect:** `&`, `@`, and `+` now survive normalization as
  distinct symbols. Previously both `Malt @ Hop` and `Malt & Hop` normalized to
  the same value. Capitalization, Unicode, apostrophes, and ordinary punctuation
  handling remain intact. No fuzzy thresholds were relaxed.

These changes address oversized display lettering, incomplete recognition boxes,
mixed-size brand lines, stylized text and meaningful punctuation. They do not
require application strings, cloud services, new dependencies, or additional
runtime OCR searches.

## Offline experiments

| Experiment | Decision | Observation |
| --- | --- | --- |
| Crop text sizing at 48/64 px, half/double scale | Adopt limited 48 px sizing | MHB brand changes from `@` to actual `&`; MHB class/type token confidence improves; ABC retained. Doubling did not help. |
| Height-relative crop padding | Adopt only mixed-size display opportunity | Restores missing digit pixels; unconditional large margins introduce artwork into MHB crops. |
| RGB channels, luminance, min/max channels | Reject runtime channel selection | No consistent improvement across the difficult fields; blue/max degraded ABC, and channels did not fix clipped geometry. |
| Autocontrast, lighter/unsharp sharpening | Keep existing small-crop path; omit extra sharpening after reduction | Additional sharpening alone cannot recover clipped pixels; some alternatives degraded MHB volume/type. |
| Fixed thresholds and inversion | Reject | No robust benefit; threshold variants damaged class/type and sometimes digit recognition. |
| PSM 6, 7, 8, 11, 13 | Retain 6/7 selection | 8/13 collapsed multiline brands or damaged numeric lines; 11 could include annotations or omit small text. |
| Numeric/unit whitelist on volume crop | Reject | Existing unrestricted crop already recovers the complete pint/fluid-ounce/metric statement. No additional supported value was recovered. |
| High crop mean confidence alone | Reject | Old `1234:` crop was highly confident while incomplete. Per-content-token confidence and completeness are necessary. |
| Selecting OCR nearest the expected application | Remove | Can conceal conflicting label evidence; tests now require evidence-independent selection. |

Experiments were offline only. No brute-force variant search or experimental
scripts were added to production. Tesseract's guidance also identifies text
resolution, borders, and segmentation as relevant variables:
<https://tesseract-ocr.github.io/tessdoc/ImproveQuality.html>.

## Six real fixtures: before / after

Times are single sequential evaluation runs on this Linux host, in milliseconds;
small timing differences are not statistically established speedups.

| Fixture | Field outcome | Calls before → after | Total before → after |
| --- | --- | --- | --- |
| 12345 | Brand `1234. IMPORTS` review → `12345 IMPORTS` match; other six fields match | 2 → 2 | 1124.5 → 1135.8 |
| ABC | All six applicable fields match; brand `ABC` preserved | 2 → 2 | 1083.8 → 1049.7 |
| FBN | Brand/type/ABV/pint match; producer/address not_found; origin not_applicable | 1 → 1 | 830.4 → 829.2 |
| MHB | Brand `Malt @ Hop Brewery` → actual `Malt & Hop Brewery`; type/4%/500 ML match; producer/address not_found | 4 → 4 | 1205.0 → 1174.7 |
| WINE | All six applicable fields match; extra weak-token check leaves candidate unchanged | 1 → 2 | 641.4 → 709.3 |
| brand-label1 | All six applicable fields match | 1 → 1 | 546.1 → 543.4 |

The baseline harness counted MHB as a match because normalization erased `@`/`&`;
that status alone overstated the quality of its extracted text. The new raw
candidate contains the actual ampersand.

Aggregate field statuses: **32 match / 1 review / 4 not_found / 5 not_applicable**
→ **33 match / 0 review / 4 not_found / 5 not_applicable**. Both runs have zero
mismatches and zero harness-reported false-confident matches. The four missing
producer/address values remain unsupported; no entity/address was invented from
the educational malt labels' metadata. The fixture file extensions/content
mismatches and other source metadata were not changed.

- Calls across the set: 11 → 12; median 1.5 → 2; maximum remains 4.
- Hard request budget remains one full-image invocation plus at most three crops.
- Total median: 957.1 → 939.4 ms. Slowest: MHB, 1205.0 → 1174.7 ms.
- OCR median: 441.0 → 430.6 ms; analysis median: 209.8 → 224.9 ms.
- Full-image raw OCR is unchanged for all six fixtures.
- All Government Warning checks, measurements, localized regions, and evidence
  are unchanged apart from analysis duration: 23 match and 37 review checks.
- Synthetic corpus: 18 cases, **306/306 expected statuses**, 18 calls, zero false
  confident matches, false mismatches, missed matches, or processing failures.
  Median total 507.8 → 513.4 ms; slowest 774.4 → 785.8 ms.

## Focused validation

- Full backend suite: **239 passed**, two existing deprecation warnings, 5.36 s.
- Ruff lint and formatting check passed; `git diff --check` passed.
- Frontend TypeScript check passed using the installed local TypeScript binary
  (`node node_modules/typescript/bin/tsc --noEmit`); pnpm was absent from this
  shell's PATH. No install or broad frontend rerun was needed.
- Eight generated real-Tesseract smoke cases preserve printed digits, `@`, `&`,
  class words, ABV, and volume. Seven deliberate disagreements never match; the
  correctly printed ampersand control matches. The seven requested false-positive
  pairs also have deterministic comparison coverage.
- Tests cover missing/weak critical-token confidence, unchanged-confidence
  expected-text substitution rejection, selecting a real volume mismatch,
  application-independent candidates, retained-line provenance, display scaling,
  warning crop exclusion, and the existing OCR budget/API error behavior.
- Real API requests with the same 12345 artwork returned 200 and two OCR calls:
  expected `12345 IMPORTS` → match; expected `1234 IMPORTS` → review. Both extracted
  `12345 IMPORTS`, with evidence `Regional OCR: 12345` and
  `Retained full-image OCR: IMPORTS`.

## Pass 2 and remaining limitations

Keep these changes for comprehensive validation. The six real fixtures are
regression examples, not an accuracy benchmark, and the synthetic set remains
separate. Confidence thresholds are heuristics, not calibrated probabilities.
High-confidence misreads, missing whole lines, unusual overlapping artwork,
severe glare/perspective and fonts outside this sample remain limitations. A
weak-token trigger may cost one extra crop even when the original text is right.
Refinement can decline to replace equally confident competing renderings.

Local Tesseract has practical headroom in image representation, crop geometry
and selection of evidence; these results do not imply every human-readable label
will be recognized correctly. Docker, broader browser checks, deployment and the
final audit remain Pass 2 work. Nothing was committed or deployed in this pass.
