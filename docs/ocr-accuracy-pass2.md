# OCR accuracy Pass 2 — independent validation

## Decision

Keep and merge the **corrected** accuracy branch, not Pass 1 unchanged. Deploy only
after normal review; nothing was committed or deployed by this audit. The original
six regression examples improve, and three demonstrated unsafe edge cases are now
covered. **Independent generalization improvement was not demonstrated:** both the
stable implementation and Pass 1 matched 13 of 33 manually visible held-out fields.

This is submission-ready as a documented, human-reviewed prototype, not as an
arbitrary-label accuracy or automated regulatory-decision system. The
[take-home specification](https://github.com/treasurytakehome-rgb/instructions)
prioritizes a working prototype, roughly five-second responses, and documented
trade-offs. Remaining false mismatches and missing values must be disclosed.

## Starting state and scope

Started on `feature/ocr-accuracy-pass`, HEAD `a521177` (optional batch workflow).
Preserved the uncommitted Pass 1 implementation, tests, and report. Compared an
export of committed HEAD with the uncommitted Pass 1 tree before corrective edits.
No history rewrite, dependency changes, frontend changes, API changes, batch
enhancements, full-image preprocessing changes, or Docker redesign.

Pass 1 changed oversized brand/type crop scaling, mixed-size crop margins and
retained-line provenance, evidence-based refinement acceptance, weak-token
triggers, and preservation of meaningful `&`, `@`, and `+` symbols. The
original six went from 32 match / 1 review to 33 match / 0 review; four unsupported
producer/address values and five not-applicable origins remained unchanged.
The old MHB status hid a real `@` versus `&` recognition problem because old
normalization erased the distinction. Pass 1 recovers the actual ampersand.

## Overfitting and expected-input audit

No fixture filename, actual sample brand, or fixture-specific pixel coordinates
were found in production rules. Height-relative crop geometry and glyph-size
normalization are defensible general rules, but their thresholds are heuristic,
not validated universal optima.

Existing exceptions deserve explicit qualification:

- The literal `label with mandatory` crop-caption exclusion predates Pass 1.
  It is educational-corpus-specific, not a regulatory cue. Low-risk but ugly,
  with potential exclusion risk for unusual real text; not needed as evidence
  of generalization and not changed without a reproduced correctness failure.
- The city/state parser accepts the literal placeholder `STATE`. This is
  prototype/corpus hygiene, not evidence of real-address coverage.
- The `mI` unit alias addresses a plausible OCR l/I confusion, not a filename.
- The isolated `o®` decoration cleanup is a narrow glyph heuristic. Its former
  whole-word deletion was demonstrably unsafe and was corrected below.

Expected application values still participate in comparison and thus may affect
whether a non-match triggers a crop. They do **not** supply crop text, image
candidate order, crop coordinates, or acceptance confidence. The comparison may
report the closest candidate, but multiple candidates retain review ambiguity.
Refined evidence is selected before comparing against the application; stronger
evidence can legitimately produce a mismatch. Confidence is Tesseract diagnostic
evidence, not a calibrated probability of correctness.

## Held-out protocol and provenance

Nine previously unused crops were manually inspected, with visible truth frozen
before running stable and Pass 1 baselines. Source:
[TTB allowable-changes sample generator](https://www.ttb.gov/regulated-commodities/labeling/allowable-revisions/allowable-changes-sample-label-generator).
Direct source URLs, image-space crop rectangles, visible expectations, notes,
raw OCR, initial/final candidates, confidence, regional/full-image provenance,
field statuses, warning details and timings are preserved in
[the evidence JSON](ocr-accuracy-pass2-evidence.json).

External images were downloaded temporarily, not added to the repository.
Crops remove explanatory slide captions and sibling variants; they are not OCR
enhancement variants. Asset URLs have the form
`https://www.ttb.gov/system/files/images/labels/SlideN.jpg`.

| Case | Slide | Visible application evidence |
| --- | --- | --- |
| chimes_brewhouse | 9 | Chimes Brewhouse; India Pale Ale; 10 fl. oz. |
| chimes_vineyard | 7 | Chimes vineyard; Chardonnay; 12.5%; 750 mL |
| woodson_brandy | 24 | Woodson; Brandy; 40%; 375 mL |
| montainia_ale | 39 | Pont du MONTAINIA; French Ale; 1 Pt. 9.4 Fl. Oz.; shipped by AC France Shipping |
| montainia_rum | 38 | HOUSE OF MONTAINIA; GOLD RUM; 40%; 750 mL; shipped by SE Ltd.; Kingston, JAMAICA |
| sunnyside_acres | 4 | SUNNYSIDE ACRES; WHITE WINE |
| rainy_day | 1 | Rainy Day; Albariño; 12.5%; 750 mL |
| pollys_rum | 2 | Polly's; Spiced Rum; 20%; 1 L |
| our_distillery_back | 47 | Produced and Bottled by Our Distillery; Ft. Mill, SC; complete Government Warning |

This provides spirits, wine, malt, stylized/mixed-size text, metric and US volume,
and a back panel. It does not provide an independent complete front/back pair,
large source diversity, or meaningful explicit-country-origin coverage. These are
small compressed educational images, not a production accuracy benchmark.
The original six are development regressions, not independent validation.
After these cases motivated the corrective changes, their final rerun is also a
regression check; a future accuracy claim needs another untouched hold-out set.

Absent evidence is recorded as null. Required API inputs used explicit
placeholders for absent text/ABV/volume; those fields are excluded from the
33-visible-field assessment. The ale compound volume is manually represented as
25.4 fl oz, not one pint. City text without a responsible-party cue is not
invented into a producer address. The rum uses an imported application scenario;
the label's Jamaican descriptor/address is not an explicit country-origin
statement, and no country was inferred. Most images are incomplete front panels,
so absent back-panel details are not extraction failures.

## Held-out results

| Version | Match | Review | Mismatch | Not found | Median / slowest ms | OCR calls |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| Stable HEAD | 13 | 6 | 4 | 10 | 408.818 / 470.239 | 16: two cases × 1, seven × 2 |
| Pass 1, before corrections | 13 | 6 | 4 | 10 | 414.675 / 496.805 | 21: six cases × 2, three × 3 |
| Corrected final | 13 | 6 | 3 | 11 | 411.305 / 498.922 | 21: six cases × 2, three × 3 |

Statuses alone hid a Pass 1 regression: the correct full-image
`HOUSE OF MONTAINIA` was replaced with crop text containing `MONTAINLA`.
It stayed review for the correct expectation but could falsely match the wrong
application spelling. Final preserves the original candidate and review.

Final extracted values below are literal OCR candidates, not corrected truth.
M = match, R = review, X = mismatch, NF = not_found; dashes mean no visible
expectation, not an extraction success. Full per-field records are in the JSON.

| Case | Brand | Class/type | ABV | Volume | Responsible party / address |
| --- | --- | --- | --- | --- | --- |
| chimes_brewhouse | chimes BreWNOuse (R) | India Pale Ale (M) | — | NF | — |
| chimes_vineyard | Ghimes vineVaira (X) | Chardonnay (M) | NF | NF | — |
| woodson_brandy | Woodsou (R) | Brandy (M) | NF | NF | — |
| montainia_ale | Pant au MONTAINIA (R) | French Ale (M) | — | NF | NF / — |
| montainia_rum | HOUSE OF MONTAINIA (R) | GOLD RUM (M) | 40 (M) | 750 mL (M) | NF / NF |
| sunnyside_acres | SUNNYSIDE ACRES a." 9 A: (R) | WHITE WINE (M) | — | — | — |
| rainy_day | Rainy Day (M) | Wine fora (X) | 12.5 (M) | NF | — |
| pollys_rum | e, (X) | Potty's Spiced Rum (R) | 20 (M) | NF | — |
| our_distillery_back | — | — | — | — | Our Distillery (M) / Ft. Mill SC (M) |

Failure attribution:

- Tiny volume/ABV lines disappear from OCR on Chimes and Woodson: OCR misses.
  Woodson's crop actually spells Woodson but has zero content confidence, so
  conservative acceptance retains review rather than claiming recovery.
- Rainy Day volume becomes `750m!`; Polly's becomes `iL`: OCR/unit evidence
  is insufficient, not permission to substitute the expected quantity.
- Montainia ale has damaged `FI. Oz` in a compound statement: OCR plus partial
  numeric extraction, now safely not_found instead of selecting one component.
- Montainia responsible-party wording `Shipped by` is outside current cue
  coverage; rum text is also rotated/small and its non-US address unsupported.
- SunnySide merges artwork into the brand: segmentation/candidate isolation.
- Chimes vineyard and Polly's brands: stylized recognition/region selection,
  with false mismatch rather than false confident match.
- Rainy Day's readable Albariño is not recognized as a type cue; marketing text
  `Wine fora` wins instead: class candidate extraction, not an absent field.
- The back panel's visibly complete warning receives wording mismatch from OCR
  damage (including merged `DRIVEA` and `ORINK`): an existing warning false
  mismatch, unchanged by Pass 1 or the corrections.

## Three evidence-driven Pass 2 corrections

1. **Compare refinement quality to its actual source region.** Unrelated
   low-confidence brand candidates outside the planned crop previously lowered
   the before-score and promoted the worse MONTAINLA crop. Refinement plans now
   carry their source line numbers; only those candidates form the comparison
   baseline. The real wrong-expectation HTTP probe now returns review with
   `HOUSE OF MONTAINIA`, not a false match to `HOUSE OF MONTAINLA`.
2. **Do not delete trademark-bearing words.** The previous trailing-decoration
   regex could erase `Extra®` or `Ale®` entirely. It now removes only isolated
   mark tokens (including the existing bounded o® artifact). A genuinely extra
   class word remains meaningful; `India Pale Ale Extra®` cannot match
   `India Pale Ale` through deletion.
3. **Do not equate an incomplete compound volume to its first component.**
   If the only parsed unit is a pint and it is immediately followed by another
   numeric/unit-like fragment, discard that partial candidate. Damaged
   `1 Pt. 9.4 FI. Oz` cannot falsely match an application specifying one pint.
   Intact compound statements and genuine multiple declarations keep existing
   behavior. No fixture-name condition, unit guessing, or relaxed numeric
   equality was added.

Ten tests were added beyond Pass 1's 239-test suite. Full tests now total 249.
All eleven requested adversarial pairs execute through application comparison.
None matches: near names/omitted symbols/type qualifiers stay review or mismatch;
all four changed ABV/volume pairs mismatch. Generated real-engine tests also
distinguish printed @ from &, rather than just testing strings.
Three additional demonstrated unsafe counterexamples above are covered.
All 13 final held-out matches agree with manually visible truth; this small
audit does not establish zero false-positive risk in general.

## Original six, final

| Fixture | Brand / class | ABV / net contents | Producer / address / origin |
| --- | --- | --- | --- |
| 12345 | 12345 IMPORTS / RUM WITH COCONUT LIQUEUR: match | 18 / 200 ML: match | 12345 IMPORTS / MIAMI FL / CANADA: match |
| ABC | ABC / STRAIGHT RYE WHISKY: match | 45 / 750 ML: match | ABC DISTILLERY / FREDERICK MD: match; origin not_applicable |
| FBN | Fake Brewery Name / India Pale Ale: match | 5 / 1 PINT: match | producer/address not_found; origin not_applicable |
| MHB | Malt & Hop Brewery / India Pale Ale: match | 4 / 1 PINT 0.9 FL OZ (500 ML): match | producer/address not_found; origin not_applicable |
| WINE | ABC WINERY / AMERICAN RED WINE: match | 13 / 750 ML: match | XYZ CELLARS / CITY STATE: match; origin not_applicable |
| brand-label1 | ABC WINERY / ROSE WINE: match | 12.5 / 750 ML: match | ABC WINERY / CITY STATE: match; origin not_applicable |

Totals: 33 match, 0 review, 0 mismatch, 4 not_found, 5 not_applicable.
The four absent responsible fields are unsupported metadata expectations, not
permission to invent an entity. Some example .jpg files contain PNG bytes; no
fixture bytes or metadata were rewritten. Harness-reported false-confident
matches are zero, but that metric checks normalized consistency rather than
independent human truth and cannot establish real-world precision.

## Warning regression

All existing warning tests passed, including missing/reordered wording, OCR
damage, absence, capitalization and visual evidence. Six real-fixture warning
evidence and outcomes are unchanged apart from timings: 23 match / 37 review
checks. Overall warning status is review for all six. Wording is review for
12345 and FBN, match for ABC, MHB, WINE and brand-label1. Presence and heading
capitalization match for all six; continuity, physical size and CPI remain
review without adequate evidence/physical scale.

The held-out back panel exposes the unchanged OCR-induced wording mismatch
described above. Passing deterministic warning tests does not erase that
real-label limitation. Warning presence on the other eight front crops is
not_found, consistent with their visible artwork.

## Gates and performance

| Gate | Final result |
| --- | --- |
| pip check | No broken requirements |
| Complete backend pytest | 249 passed, 2 existing deprecation warnings, 5.38 s |
| Ruff lint / formatting | Passed; 49 files already formatted |
| git diff --check | Passed |
| Generated corpus | 18 cases; 306/306 expected statuses; no expectation changes |
| Synthetic errors | 0 false confident matches, false mismatches, missed matches, processing failures |
| Synthetic review / not_found | 58 / 10 |
| Frozen pnpm install | Passed; existing lockfile unchanged |
| Vitest | 6 files, 39 tests passed; 1.13 s |
| ESLint / TypeScript / Prettier | All passed |
| Vite production build | Passed, 22 modules, 78 ms; JS 242.83 kB / 76.02 kB gzip |

Frontend gates used isolated Node 24.20.0 and pnpm 11.19.0 because the shell
initially exposed Node 18 and no pnpm. These were temporary development tools,
not new project dependencies. No normal unit test was made dependent on OCR;
the existing conditional real-engine tests executed with installed Tesseract.

Sequential host timings (single runs, not a statistical benchmark):

| Set | Median total | p90 total | Slowest total | OCR calls |
| --- | ---: | ---: | ---: | --- |
| Original six | 932.920 ms | 1185.091 ms | 1185.091 ms | 12 total; median 2; max 4 |
| Held-out nine | 411.305 ms | — | 498.922 ms | 21 total; six × 2, three × 3 |
| Synthetic eighteen | 509.237 ms | 531.517 ms | 788.859 ms | 18 total; median/max 1 |

Original-six OCR median/max: 427.875 / 668.397 ms; analysis median/max:
218.938 / 380.229 ms. Synthetic OCR median/max: 229.766 / 257.617 ms.
Full timing breakdowns are in the evidence JSON. All measured requests are
below the approximate five-second target; these are not concurrent capacity
guarantees. Held-out call count rose 16 to 21 without more correct matches.

## Fresh Docker and batch compatibility

Built `ttb-ocr-accuracy-pass2:validation` from the final application tree,
manifest `sha256:add3c1c5f4198aee981f0a0c6a1c4ce7d7310a56b0d7703e88cf166a2eb1a6af`.
Ran with a 1 GiB memory limit and **no host mounts**. Container became healthy,
UID was 10001 (appuser), internal Tesseract was 5.3.0 with eng and osd data.
Frontend, JS/CSS assets, health, raw OCR and verification routes all returned 200.
The frontend bundle includes the existing batch interface.

Real MHB verification returned its correct brand/type/ABV/compound metric volume,
with four OCR invocations in 1208.024 ms. Warning remained review and unsupported
producer fields remained not_found. The held-out wrong-MONTAINLA expectation
returned review in 414.809 ms with two calls. Host Tesseract is not mounted or
needed by the container.

Compatibility exercised the actual frontend CSV, matching, queue, API and export
modules against the real container, using only a Node window/base-URL adapter.
Three rows (valid, corrupt, valid) produced fulfilled/rejected/fulfilled; maximum
active requests was two. Single and batch runs of the same label had identical
field results and raw text. CSV export retained individual processing errors.
Batch elapsed time was 1415.059 ms, with valid server requests around
1371–1393 ms; single comparison request was 1155.080 ms.
Vitest also covers quoting/BOM, mapping, bounded large queues, cancel/retry and
export. This was compatibility testing, not a new batch implementation or an
end-to-end browser automation run.

Idle memory was 80.58 MiB; cgroup peak was 199741440 bytes (about 190.5 MiB).
Cumulative container CPU usage was about 11.12 CPU seconds across startup and
these checks, not per request. Temporary container was stopped and removed;
the local validation image remains. No public production load test or deployment.

## Complexity, remaining risk, recommendation

The request budget stays one full-image OCR plus at most three targeted crops;
no brute-force OCR search or external service was introduced. More crops consume
CPU and temporary image memory. Across both passes the tracked diff adds roughly
180 net service lines and additional regression tests; this is manageable but
the crop/acceptance path is noticeably more complex. No application dependency
was added. Keep these rules local, evidence-carrying, bounded and unit-tested.

- **Should fix before submission:** the demonstrated false-match cases (source
  region quality, whole-word trademark stripping, partial compound volume) were
  corrected and all gates rerun. No further demonstrated low-risk generalized
  solution is being withheld merely to preserve a score.
- **Acceptable OCR limitations:** missing tiny/stylized text and cautious
  review/not_found on ambiguous candidates; do not label incorrect warning
  mismatch or marketing-line type selection as correct outcomes.
- **Remaining accuracy defects:** stylized brand false mismatches, class cue
  coverage/marketing-line selection, unsupported shipped-by/foreign addresses,
  and OCR-damaged complete-warning false mismatch. These need broader
  representative evidence and calibrated abstention, not another sample alias.
- **False-positive risk:** high-confidence OCR can still be wrong, and heuristic
  cleanup is not proof of identity. Counterexample tests reduce demonstrated
  risks; neither the six-fixture metric nor 306 synthetic checks proves general
  precision.
- **Metadata issues:** missing backs/responsible fields, application import
  assumptions, and example placeholder addresses must not count as extraction
  successes or be filled from expectations.

Recommendation: commit/merge and deploy the **corrected** branch after review,
with these limitations visible. Do not merge Pass 1 unchanged. It is a reasonable
take-home decision-support prototype, not a claim of robust arbitrary-label
verification. Local Tesseract tuning is reaching practical diminishing returns
for this scope: extra held-out calls yielded no extra matches. That does not
prove Tesseract has an absolute accuracy ceiling.

If greater accuracy becomes a requirement, first obtain higher-resolution label
artwork and a larger independently annotated set with explicit abstention and
false-match metrics. Then benchmark a local learned text detector/recognizer
behind the existing OCR interface (for example, evaluating
[docTR](https://github.com/mindee/doctr)), with orientation/layout handling and
measured CPU/memory/latency. Keep comparison and image evidence independent from
expected values. No model is assumed superior without that evaluation; an LLM
should not manufacture ground truth. None of this was implemented in this pass.

## Changed files

Preserved Pass 1: normalization, OCR refinement, comparison/API/normalization/
refinement/real-engine tests, and `docs/ocr-accuracy-pass1.md`.
Pass 2 modified OCR refinement and structured extraction, expanded comparison
and refinement regressions, and added this report plus the evidence JSON.
No frontend, API schema, dependency manifest/lockfile, Dockerfile or fixture asset
changed. Exact final git status is included in the completion message.
