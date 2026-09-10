# Government Warning evidence-quality pass

## Outcome and scope

Baseline commit: `e4a2544`, branch `main` (the accuracy branch was fast-forwarded
before this pass; confirmed by the existing reflog).
The previous OCR accuracy work was already committed. Existing uncommitted
`examples/README.md`, twenty synthetic image/JSON pairs, their index and batch
manifest, and `docs/ocr-accuracy-pass2-evidence.json` were preserved.

The adopted changes materially improve warning analysis without forcing all
checks to match. New-synthetic review checks fall **71 → 59**; original-six
review checks fall **37 → 32**. Fifteen of the twenty new labels now match on
all eight non-physical checks. Overall warning status intentionally remains
review because physical size and CPI cannot be established.

Recommend committing and deploying after review, with the limitations below.
Nothing was committed or deployed. This is reviewer assistance, not legal
approval, font identification, or a real-world accuracy benchmark.

## Baseline protocol

Before production edits, ran the actual preprocessing and local Tesseract
provider on six originals, twenty new supplied synthetic labels and nine
previously held-out TTB crops. Recorded raw OCR, complete warning sub-checks,
explanations, measurements, localized text and mean OCR confidence. Cached
those real OCR/image results solely for paired before/after analysis. A fresh
35-image real-engine run at the end reproduced all final sub-check counts.

[Machine-readable evidence](government-warning-accuracy-evidence.json) contains
every label's baseline/final check and a classification of **every baseline
review**: A potentially automatable, B genuinely uncertain, C physical/manual.
The [earlier audit evidence](ocr-accuracy-pass2-evidence.json) records held-out
source URLs and crop coordinates. Temporary downloaded images were not added
to the repository. The original six and new synthetic fixtures influenced
development; the held-out set is also no longer an untouched accuracy benchmark.

The nine held-out crops include eight front panels without a warning and one
Our Distillery back panel with a visibly complete warning. Missing warnings on
front-only crops are legitimate absent evidence, not recognition failures.

The supplied T02 companion has `1 PINT (473 ML)`, which the existing application
form normalizer does not accept as a single expected value. The warning-only
evaluator explicitly reports using its metric component for the physical tier.
No production volume logic or fixture metadata was changed. Existing misleading
.jpg extensions containing PNG bytes are decoded by content for evaluation.

## Before/after by sub-check

Cells are **Match / Review / Mismatch / Not found**, baseline → final.

| Check | New synthetic (20) | Original six | Held-out (9) |
| --- | --- | --- | --- |
| presence | 20/0/0/0 → 20/0/0/0 | 6/0/0/0 → 6/0/0/0 | 1/0/0/8 → 1/0/0/8 |
| wording | 16/4/0/0 → 16/4/0/0 | 4/2/0/0 → 4/2/0/0 | 0/0/1/8 → 0/0/1/8 |
| heading_capitalization | 20/0/0/0 → 20/0/0/0 | 6/0/0/0 → 6/0/0/0 | 1/0/0/8 → 1/0/0/8 |
| heading_boldness | 20/0/0/0 → 15/5/0/0 | 2/4/0/0 → 2/4/0/0 | 0/1/0/8 → 0/1/0/8 |
| body_not_bold | 20/0/0/0 → 15/5/0/0 | 2/4/0/0 → 2/4/0/0 | 0/1/0/8 → 0/1/0/8 |
| continuous_statement | 0/20/0/0 → 20/0/0/0 | 0/6/0/0 → 4/2/0/0 | 0/1/0/8 → 0/1/0/8 |
| separation | 20/0/0/0 → 20/0/0/0 | 2/4/0/0 → 2/4/0/0 | 1/0/0/8 → 1/0/0/8 |
| legibility_contrast | 13/7/0/0 → 15/5/0/0 | 1/5/0/0 → 2/4/0/0 | 0/1/0/8 → 0/1/0/8 |
| type_size | 0/20/0/0 → 0/20/0/0 | 0/6/0/0 → 0/6/0/0 | 0/9/0/0 → 0/9/0/0 |
| characters_per_inch | 0/20/0/0 → 0/20/0/0 | 0/6/0/0 → 0/6/0/0 | 0/9/0/0 → 0/9/0/0 |

Overall: original six remain 6 review; new synthetic remain 20 review; held-out
remain 8 not_found and 1 mismatch. Keeping the overall status does not mean the
image-based results failed to improve.

## Why reviews occurred

- **Continuity (A):** all twenty new labels and four originals were penalized
  solely for multiple Tesseract blocks. Sparse PSM 11 normally fragments one
  coherent paragraph into blocks. Block/paragraph IDs are not physical breaks.
- **Contrast (A/B):** whole-crop Otsu clustering assigns interpolated glyph edges
  to the background class. T04/T06 had background standard deviations around
  15.6/15.1 despite stable actual whitespace. WINE similarly measured 23.0.
  Other low-quality samples had genuinely weak word-core separation.
- **Weight (B):** all twenty new examples initially matched. Four original
  headings were ambiguous. An independent negative control showed that the
  metric did not normalize text size: a larger *regular* heading could cross
  the boldness threshold with no weight difference.
- **Wording (B):** T16/T19/T20 contain OCR comma-versus-period damage; T18 reads
  `akcoholic`. These remain review, not matches. Original 12345 and FBN retain
  damaged marker/text reviews.
- **Separation (B):** all new labels already matched. Four originals have close
  detected neighboring text; neither a hard border requirement nor relaxed
  spacing threshold was justified.
- **Physical type size/CPI (C):** every ordinary raster lacks trustworthy scale.
  These reviews are intentional, not failures to remove.

## Adopted changes and evidence thresholds

### Geometry-based continuity

Preserve clause anchors/order, numbered markers and unrelated-insertion checks.
Require complete single-page boxes; merge physical rows using at least 50%
vertical overlap of the shorter box, independently of block/paragraph IDs.
Reject an automatic continuity match for a horizontal gap exceeding 4.5 median
word heights, an interline gap exceeding 2.5 median row heights, or non-overlapping
horizontal row spans. These are scale-relative screening heuristics, not legal
spacing definitions. Incomplete/distant geometry remains review; clear missing
or reordered clauses and reliable unrelated insertions remain mismatch.

This promotes twenty synthetic and four original continuity checks. Original
12345/FBN and the held-out damaged marker remain review. A changed phrase can
still have coherent layout: wording and continuity are separate questions.

### Relative weight, normalized for text size

The existing ink-area/perimeter stroke estimate is now divided by glyph height
before comparing heading and body. The existing relative thresholds are retained:
at least 1.2 for heavier heading/lighter body, below 0.85 for reversed emphasis,
otherwise review. Tiny text remains review. Word samples with less than 76/255
10th-to-90th-percentile tonal spread cannot establish relative weight.

Controlled regular-heading/body tests at heading sizes 32/48/64 gave raw ratios
1.053/1.476/2.071, versus normalized ratios 1.098/0.958/1.014. The raw metric
would have falsely matched the two larger regular headings; normalized evidence
correctly retains review. Same-weight, all-bold and body-heavier negatives remain
non-match across the tested sizes. Clean bold/regular controls match at several
sizes and in both contrast polarities.

This correction conservatively changes T16–T20 heading/body checks from match
to review: their visibly degraded raster no longer supplies a strong normalized
weight difference. No threshold was lowered to recover those matches. The six
original and held-out weight outcomes stay unchanged. Relative weight does not
identify exact font weight or guarantee that different font families are comparable.

### Robust contrast corroboration

Keep existing whole-crop luminance measurements, but require text-word contrast
corroboration so dark decoration cannot masquerade as legible body text.
For the additional strong-evidence path:

- Sample at least eight words with boxes at least 12 pixels high.
- Compute each word's 10th-to-90th-percentile luminance spread; the lower quartile
  must be at least 0.55 of the full luminance range.
- Inspect whitespace above and below words, leaving a 0.2-text-height halo around
  glyph edges to avoid treating interpolation as background texture.
- The upper quartile of local whitespace spreads must be at most 12/255.
- Mean OCR confidence must be at least 0.85.

The original whole-crop path retains its 0.45 contrast, 15 background standard
deviation and 0.65 OCR-confidence requirements, with word corroboration of at
least 0.45. Percentile spread is polarity-independent. Textured, weak and
low-contrast negatives cannot pass merely because the warning rectangle includes
high-contrast artwork. These thresholds are tested heuristics, not calibrated
confidence probabilities or a comprehensive legal legibility test.

T04/T06 and WINE gain contrast matches. T16–T20 and the low-quality held-out
warning remain review. The other original contrast outcomes are unchanged.

### Wording and capitalization

Do not relax prescribed wording to make the four damaged synthetic readings
match. Bounded token joins/splits such as `drivea` may produce review, never an
exact wording match. A confidently recognized wrong clause number is mismatch;
low-confidence or geometry-free marker ambiguity can remain review. Omitted
phrases, missing clauses, changed words and reordered clauses remain covered.

Capitalization now examines the alphabetic heading words rather than incidental
colon/dash spacing. It does not rewrite G0VERNMENT to GOVERNMENT or equate
reliably mixed-case headings with uppercase ones.

### Summary compatibility

No public schema or overall-status semantics changed. The existing warning
section adds one explanatory sentence only when all eight non-physical checks
match: “Automated warning checks passed; physical dimensions require manual
confirmation.” The review badge and existing physical-check group remain.
The form, batch workflow, styling and field comparisons are unchanged.

## Experiments and rejected approaches

- Replaced OCR-block continuity penalties only after inspecting actual TSV
  fragmentation and comparing physical rows.
- Rejected raw stroke width/dark-pixel count as sufficient boldness evidence:
  the larger-regular-heading controls demonstrate false positives.
- Tried whitespace samples touching glyph edges; interpolation contaminated the
  estimate. Excluding a small size-relative halo measures actual whitespace.
- Rejected simply raising the whole-crop background-noise tolerance; robust word
  and whitespace evidence is independently required.
- Did not adopt a mandatory rectangular border, fixed pixel-spacing rule,
  black-on-white assumption, fixture coordinates or product-name exceptions.
- Did not introduce warning OCR retries, threshold searches, a new recognition
  engine or any cloud/ML/image-processing dependency. No dead experimental
  production path was retained.

## Negative controls and regression gates

Backend final: **284 passed**, two existing deprecation warnings, **9.34 s**.
All 74 warning tests pass, including six additional actual-Tesseract raster
controls (clean, reverse contrast, same-weight, all-bold, body-heavier, low contrast).
The remaining warning unit tests use deterministic image/text evidence and do
not depend on Tesseract. New evaluator metadata tests also pass.

Covered negatives include absent warning, either missing clause, phrase removal
and replacement, clause reversal, reliable wrong number, unrelated insertion,
mixed/lowercase heading, identical/reversed weight, oversized regular heading,
tiny text, disconnected/incomplete geometry, surrounding text, dark decoration,
textured background and low contrast. Reverse contrast positive controls remain
matches. No defective control receives an inappropriate match on its target check.

- pip check: no broken requirements.
- Ruff lint: passed; formatting: 51 files already formatted.
- git diff --check: passed.
- Existing generated corpus: **18 cases, 306/306 statuses**, zero false confident
  matches, false mismatches, missed matches or processing failures; 42 review,
  10 not_found, 18 OCR invocations.
- The old corpus initially showed 16 differences, all continuity review → match.
  Its clean-layout expectation was corrected; the degraded case explicitly
  retains review. Text-defect and missing-warning expectations were not weakened.
- Fresh warning evaluation: 35 cases, same final counts as paired evaluation,
  one actual Tesseract invocation per case.
- Frozen pnpm install, ESLint, TypeScript, Prettier and Vite build: passed.
- Vitest: **40 tests in six files**, 1.27 s. Vite: 22 modules, 71 ms,
  243.06 kB JS / 76.11 kB gzip. Lockfile unchanged.

These metrics measure controlled regressions, not operational false-positive
rates. The held-out Our Distillery wording false mismatch remains: the OCR says
`(3)`, `ORINK` and `DRIVEA` on a visibly complete warning. This pass does not
claim to solve that recognition problem or turn it into a confident match.

## Runtime, performance and resources

Paired analyzer timings on identical image/TSV evidence (single sequential runs):

| Set | Baseline median analysis | Final median analysis |
| --- | ---: | ---: |
| Original six | 141.16 ms | 175.56 ms |
| New synthetic twenty | 118.22 ms | 146.91 ms |
| Held-out nine | 0.12 ms | 0.12 ms |

The held-out median is dominated by eight absent warnings; its localized case
increased from about 59.28 to 66.56 ms. Extra local image measurements cost
roughly 30–35 ms on the main sets, with no extra OCR subprocesses.

Fresh end-to-end warning-only pipeline (includes decode, preprocessing and OCR,
but not application-field refinement): original median/max **967.503/1064.796 ms**;
new synthetic **621.311/703.522 ms**; held-out **338.430/388.851 ms**.
Actual verification requests in Docker include the unchanged optional refinement
budget of one full-image OCR plus at most three crops and remain below five
seconds in the measured checks. No public deployment was load-tested.

Fresh production Docker builds succeeded, using the existing Dockerfile.
Final image: `ttb-warning-accuracy:validation`,
manifest `sha256:573f13946998def567b2058198d5ad328d50426c8fd896daa688dbd073a71730`.
Verified healthy status, UID 10001, no host mounts, internal Tesseract 5.3.0,
eng/osd language data, frontend and static assets, health, raw OCR and
verification endpoints. Checked all six originals, T01/T04/T16 and the held-out
back panel. Original application-field statuses were unchanged from Pass 2.
T01 matches all eight automated warning checks, while overall remains review.

Actual frontend batch modules were exercised against real container HTTP:
maximum two active requests, valid/corrupt/valid outcomes fulfilled/rejected/
fulfilled, CSV export with isolated processing error, and identical single/batch
field results. This is compatibility testing, not a browser automation or batch
feature change. Full frontend unit coverage also passed.

During the first complete container run, peak cgroup memory was 236568576 bytes
(225.6 MiB), with 109.9 MiB retained after requests under a 1 GiB limit.
This differs from the previous audit's workload, so it is not a measured
before/after memory regression. No application dependency was added.
Temporary verification containers were removed; the local validation image remains.
The final rebuilt-container rerun peaked at 186830848 bytes (178.2 MiB).
Its representative full verification durations were T01 651.63 ms, T04 472.25 ms,
T16 530.27 ms and MHB 1245.66 ms; original-six median 1010.96 ms, maximum
1245.66 ms. The final batch compatibility run completed in 1517.09 ms with
maximum concurrency two and equivalent single/batch results.

## Automation classification and remaining limits

| Check | Classification |
| --- | --- |
| Presence | Reliably automatable when anchors are recognized; absence/weak OCR remains qualified |
| Wording | Reliably automatable on reliable exact OCR; damaged OCR remains partially observable |
| Capitalization | Reliably automatable on recognized alphabetic heading evidence |
| Heading/body weight | Partially automatable; relative raster evidence, not exact font identification |
| Continuity | Partially automatable; requires coherent geometry and reliable clause evidence |
| Separation | Partially automatable; OCR may miss surrounding non-text artwork |
| Contrast/legibility | Partially automatable; strong contrast is not every aspect of legibility |
| Physical type size | Manual by design without trustworthy scale |
| Characters per inch | Manual by design without trustworthy scale |

The physical tiers remain unchanged and were checked against
[27 CFR 16.22](https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-16/subpart-C/section-16.22):
up to 237 mL, 1 mm / 40 CPI; over 237 mL through 3 L, 2 mm / 25 CPI; over 3 L,
3 mm / 12 CPI. Boundary tests at 237, 237.1, 3000 and 3000.1 mL pass.
Raster scaling is never treated as physical scale.

The meaningful gains are removing non-visual block-ID penalties and measuring
actual text/whitespace contrast, while catching a size-induced weight false
positive. Further threshold tuning has diminishing returns for this prototype:
remaining reviews concern degraded evidence, font ambiguity or physical scale.
A larger independent set and better source artwork would be more valuable than
forcing these controls green. No autonomous compliance claim is justified.

## Reproduction and changed files

Run:

```sh
.venv/bin/python backend/scripts/evaluate_warnings.py
.venv/bin/python backend/scripts/evaluate_warnings.py --heldout-images-dir /path/to/ttb-assets
.venv/bin/python backend/scripts/evaluate_labels.py --json
.venv/bin/pytest backend/tests -ra
```

The optional held-out directory contains the original SlideN.jpg filenames from
the source URLs in the earlier evidence JSON; no network download occurs in the
evaluator. The report labels diagnostic physical-tier assumptions explicitly.

Changed by this pass: government_warning.py; its tests; the generated corpus's
continuity expectations; the warning evaluation script and its metadata tests;
one conditional explanatory sentence in the existing warning component and its
test; this report and its evidence JSON. Existing examples and unrelated audit
files were not changed by this pass. Exact final git status is in the completion
message. Nothing was staged, committed or deployed.
