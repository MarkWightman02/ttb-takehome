# Physical warning requirements and status semantics

## Addendum: scope and wording follow-up

The authoritative take-home instructions require verifying the Government Warning's
presence, exact prescribed wording, and heading presentation (all-caps, bold) — they do
not ask for a physical type-size or characters-per-inch measurement. Those two checks
are additional regulatory context this project chose to surface from 27 CFR 16.22, not a
required scoring gate, and this was reconfirmed directly against the instructions repo in
a follow-up pass.

That follow-up pass also hardened `automated_status` so a hypothetical future physical
*mismatch* is never hidden (it is now the single source of truth backend and frontend
both rely on, rather than a separate `overall_status` fallback), and refined the exact
wording below: the Government Warning badge for a clean label now shows a plain **Match**
(not a custom "Automated checks matched" label) with manual physical confirmation shown as
a separate, non-competing note reading "Additional physical confirmation required."; the
top-level summary for that case is the shorter **"All automated checks matched."**, with
"Physical Government Warning measurements require manual confirmation." shown as a
distinct secondary note rather than joined into one sentence. The status *hierarchy* and
JSON shape documented below (`automated_status`, `manual_confirmation_required`, legacy
`overall_status`) are unchanged; only the exact display strings quoted in this report
reflect the wording at the time it was written.

## Decision

Manual-only physical requirements should **not** force the automated warning
result or otherwise-clean application into “Needs review.” They are genuine
requirements, but absence of a physical scale is different from uncertainty in
OCR or image evidence.

Separate the two concepts without a new status enum or a new measurement feature:

- `government_warning.automated_status`: the eight text/image checks.
- `government_warning.manual_confirmation_required`: whether either physical
  check remains unresolved.
- Individual physical cards retain `review`; display them neutrally as
  **Manual confirmation**.
- Keep legacy `government_warning.overall_status` comprehensive and conservative
  for existing API clients. It is no longer used to classify manual-only work as
  automated uncertainty in the updated UI.

These values are computed by the backend from existing checks, not supplied by
application input. No OCR, extraction, image-analysis, physical-tier or comparison
threshold changed. No PDF support, calibration, assumed DPI, database, external
service or new dependency was added.

## Baseline

Started on `main` at `b7b823b`. Two untracked previous audit evidence JSON files
were present and preserved. Inspected result models, aggregation, summaries,
single/batch rendering and tests before editing.

Ran all 26 original/supplied synthetic images through actual Tesseract and the
HTTP verification route before changes. Fifteen synthetic warnings had all
eight automated checks matching, yet their legacy aggregate was review because
type size and CPI were review. Nine also had all applicable application fields
matching. The old single-label summary described pending visual review; batch
classified all these otherwise-clean cases as review.

[Per-fixture before/after evidence](physical-warning-semantics-evidence.json)
records baseline and final summaries, flags, individual problem checks, field
issues, timings and invocation counts.

## Regulatory and technical findings

The current [27 CFR 16.22](https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-16/subpart-C/section-16.22)
and [TTB health-warning guidance](https://www.ttb.gov/regulated-commodities/beverage-alcohol/wine/labeling-wine/wine-labeling-health-warning-statement)
retain these requirements:

| Container volume | Minimum type size | Maximum characters per inch |
| --- | ---: | ---: |
| At most 237 mL | 1 mm | 40 |
| Above 237 mL through 3 L | 2 mm | 25 |
| Above 3 L | 3 mm | 12 |

These are physical type/printing and character-density requirements. A browser
pixel or an OCR word-box height is not a millimeter or a printed inch. The
software reports the applicable tier, not that physical dimensions were measured.
A nominal font point size also is not by itself a validated printed-glyph measurement.

TTB's [COLAs Online FAQ, C31](https://www.ttb.gov/faqs/colas-and-formulas-online-faqs)
expressly distinguishes the submitted image dimensions from the actual printed
label dimensions, which applicants enter separately. Its historical
[Industry Circular 2011-04](https://www.ttb.gov/public-information/industry-circulars/archives/2011/11-04)
documents electronic-image distortion and the industry's continuing responsibility
for proper printed labeling. That historical process guidance is not a waiver of
the physical requirements, nor a claim that every current agency workflow is
identical. Our “manual confirmation” designation is prototype decision support,
not a statement that TTB requires an individual reviewer to measure every COLA.

The [assignment](https://github.com/treasurytakehome-rgb/instructions) asks for a
standalone reviewer aid with quick, understandable results. Regulations do not
prescribe this application's status enum. Separating unmeasured physical
requirements from doubtful automated evidence is an engineering/UI decision,
not a legal conclusion.

### Scale-source assessment

The trust classifications below are technical inferences from the sources and
the current input contract, not official TTB certification of file formats.

| Source | Assessment | Why / conditions |
| --- | --- | --- |
| Ordinary raster, screenshot, CSS size | Insufficient | Pixels alone have no authenticated connection to printed dimensions. |
| DPI/EXIF/pHYs metadata alone | Insufficient | Encoded intended density is not evidence that the image was captured/exported/printed at that scale. Missing or altered metadata, resampling and screenshots break the inference. |
| PDF/vector artwork with physical dimensions | Conditionally trustworthy for intended artwork measurements | Need verified provenance, correct page/trim/crop box, content transforms and output scale. A dimensioned page alone does not prove the label's boundaries or actual printed size. |
| Reviewer-supplied artwork width/height | Conditionally trustworthy | Must refer to the exact label region, with validated crop/aspect ratio, no perspective distortion, and correct mapping for multiple panels. A typed number alone is not independent evidence. |
| Other embedded layout/calibration metadata | Conditionally trustworthy only with controlled provenance | It must describe the actual artwork and survive every transform; a metadata field's existence is insufficient. |
| Verified physical measurement of the actual printed label | Trustworthy enough for human physical confirmation | Uses a suitable calibrated measurement method on the actual product; not an automatic capability of this application. |

[PNG's pHYs specification](https://www.w3.org/TR/png/#11pHYs) describes intended
pixel size/aspect ratio, not provenance or proof of printing. [Adobe's PDF
coordinate-system documentation](https://opensource.adobe.com/dc-acrobat-sdk-docs/library/interapp/IAC_API_CoordinateSystems.html)
distinguishes user-space physical units from screen/device pixels and notes that
content operators can change the coordinate system. The
[PDF specification](https://developer.adobe.com/document-services/docs/assets/35e4369068f86065372c18787171a17e/PDF_ISO_32000-1.pdf)
also permits page UserUnit scaling. A future dimension-aware workflow would have
to honor these transforms and validate a physical measurement method; it should
not merely divide a bounding box by 72, 96 or 300.

**Current answers:** neither physical type size nor CPI can be reliably verified
from this application's ordinary PNG/JPEG/WebP uploads. DPI alone is not trusted.
A verified dimensioned artwork workflow could make measurements possible under
conditions, but none was implemented. Container volume selects a regulatory tier;
it never supplies label dimensions.

## Status hierarchy and compatibility

| Evidence state | Updated behavior |
| --- | --- |
| Any actual field/warning mismatch | Mismatch-oriented summary and batch result; physical requirement remains visible. |
| Any automated uncertainty or missing field/warning evidence | Needs review; physical requirement remains visible. |
| All automated checks match; physical checks unresolved | Automated checks matched, with manual physical confirmation required. |
| All automated checks and trustworthy physical checks pass | Could remove the manual flag in a future supported workflow; unreachable for current raster-only inputs. |

The backend model derives the two additive values from a shared definition of
the manual physical checks. It does not change individual results. An actual
physical mismatch would still take precedence in application/batch decisions if
such evidence becomes supported; excluding manual-only review must not hide a
real defect.

Example current clean response:

```json
{
  "overall_status": "review",
  "automated_status": "match",
  "manual_confirmation_required": true
}
```

This example is the warning object's status metadata, not the complete response.
The comprehensive legacy status remains review intentionally. New consumers
should use automated status plus the physical flag for the two distinct concepts.
New frontend helpers fall back conservatively to legacy status when additive
fields are absent, so an older backend is not silently promoted to match.

The single-label summary for an otherwise-clean application is:
**All automated checks matched; physical Government Warning measurements require
manual confirmation.** Genuine OCR/image or field uncertainty instead retains
**One or more label checks require manual review.**

Both physical cards stay visible with their thresholds and explanations. Their
neutral styling and **Manual confirmation** labels avoid treating an unavoidable
measurement task as a suspected defect. The warning badge and batch match labels
explicitly say **Automated checks matched**.

Batch scheduling, mapping, upload, retry and concurrency did not change. A clean
row may now be `match`, with a persistent physical-confirmation message in its
details. CSV keeps `government_warning_status` with legacy semantics and adds
`automated_warning_status` and `manual_physical_confirmation_required`.
Its row `overall_status=match` means automated checks matched, not physical or
regulatory compliance. Processing-error rows leave result-only columns empty.

## Original-six and twenty-synthetic results

All individual application results, warning sub-checks and OCR invocation counts
were identical before/after. Every row still requires physical confirmation.
All six originals retain genuine automated warning review. Fifteen synthetic
warnings now display automated match; five retain automated review.

Application summary legend:

- **A:** “All automated checks matched; physical Government Warning measurements require manual confirmation.”
- **R:** “One or more label checks require manual review.”

| Fixture | Automated warning | Physical | Application summary | Application-field issues |
| --- | --- | --- | --- | --- |
| 12345 | review | Required | R | None |
| ABC | review | Required | R | None |
| FBN | review | Required | R | producer_name: not_found; producer_address: not_found |
| MHB | review | Required | R | producer_name: not_found; producer_address: not_found |
| T01_harbor_ridge_distilling | match | Required | A | None |
| T02_maple_stone_brewing | match | Required | R | net_contents: review |
| T03_northstar_cellars | match | Required | A | None |
| T04_sol_dorado_imports | match | Required | A | None |
| T05_fjord_house | match | Required | R | class_type: not_found |
| T06_cask_clover | match | Required | A | None |
| T07_juniper_works | match | Required | R | net_contents: not_found |
| T08_copper_finch | match | Required | A | None |
| T09_orchard_line | match | Required | R | net_contents: review |
| T10_mesa_roja | match | Required | A | None |
| T11_hightide_brewing_co | match | Required | R | net_contents: review |
| T12_ember_grain | match | Required | A | None |
| T13_alpine_echo | match | Required | A | None |
| T14_blackbird_rum_co | match | Required | R | brand_name: not_found |
| T15_golden_orchard | match | Required | A | None |
| T16_blue_lantern_imports | review | Required | R | None |
| T17_ironwood_brewery | review | Required | R | None |
| T18_silver_thread_cellars | review | Required | R | class_type: review |
| T19_meridian_spirits | review | Required | R | None |
| T20_old_mill_distillery | review | Required | R | None |
| WINE | review | Required | R | None |
| brand-label1 | review | Required | R | None |

Nine complete synthetic applications move from generic review presentation to A.
Six others have a clean automated warning but retain genuine application-field
issues, so they correctly remain R. The five degraded warnings also remain R.
These are controlled regression examples, not an accuracy benchmark.

T02's companion value `1 PINT (473 ML)` is unsupported as a single expected form
value. Both baseline and final diagnostic HTTP evaluations used its explicit
473 mL component, recorded in the evidence. The fixture and volume parser were
not changed; the existing input limitation was not hidden.

## Tests and performance

- Backend: **308 passed**, two existing deprecation warnings, **9.31 s**.
- New coverage: every automated sub-check's review/mismatch gates, absent warning,
  real field problems, manual-only clean result, additive serialization, computed
  flag integrity, possible future physical defect, and DPI at 72/96/300/1200.
- Existing warning wording, missing-clause, case, weight, contrast, continuity,
  separation, physical tier and real-engine tests all pass unchanged.
- pip check, Ruff lint/format and git diff --check passed; 52 Python files formatted.
- Existing generated corpus: **18 cases, 306/306 checks**, zero false confident
  matches, false mismatches, missed matches or processing failures. **18 OCR calls**.
  No corpus expectations changed in this pass.
- Frontend: **42 tests / six files passed**, latest full run 1.20 s.
  Frozen install, ESLint, TypeScript, Prettier and Vite build passed.
  Build: 22 modules, 71 ms; JS 243.53 kB / 76.24 kB gzip. Lockfile unchanged.
- UI tests verify neutral physical cards, separate automated status and a visible
  requirement. Batch tests distinguish manual-only, genuine review and mismatch,
  validate separate CSV columns and preserve conservative legacy fallback.

Sequential real HTTP total times, in milliseconds:

| Set | Baseline median / max | Final median / max |
| --- | --- | --- |
| Original six | 974.74 / 1234.12 | 985.32 / 1240.04 |
| Twenty synthetic | 604.47 / 763.03 | 616.07 / 770.77 |

These single-run variations do not demonstrate a meaningful OCR performance
regression. No OCR/image algorithm or call count changed. Evaluating both new
computed properties took about **1.29 microseconds** per iteration in a local
10,000-iteration check. The existing approximately five-second target is preserved
in these measurements; this is not a capacity/load benchmark.

## Production container and batch verification

Built `ttb-physical-semantics:validation` from the changed tree, manifest
`sha256:da5e93b69b0bf3f5924611f89c7812624520395a58e2d9db949846dc3553297e`.
Existing Docker architecture unchanged. Verified healthy, UID 10001, no mounts,
internal Tesseract with eng/osd, frontend/static assets, health, raw OCR and
verification routes.

Real container results:

| Fixture | Automated warning | Physical required | Total | Calls |
| --- | --- | --- | ---: | ---: |
| T01 clean | match | true | 658.65 ms | 1 |
| T16 genuine uncertainty | review | true | 536.58 ms | 1 |
| Generated altered wording | mismatch | true | 495.05 ms | 1 |

Actual compiled frontend request/queue/export modules ran against the container:
maximum concurrency two, valid/corrupt/valid outcomes fulfilled/rejected/fulfilled,
same single/batch field results and summary, clean row classified match with
physical requirement visible, and CSV preserving legacy review plus automated
match plus true manual flag. Queue elapsed **860.66 ms**; single clean verification
**664.56 ms**. No batch feature was added. Peak cgroup memory was about **197.84 MiB**
under a 1 GiB limit. Temporary container was removed; the local image remains.

## Files, limits and release recommendation

Changed model/summary logic, focused backend tests, shared frontend status helpers,
single/batch labels and physical-card styling, CSV compatibility and their tests.
Updated README and architecture documentation, and added this report and the
26-case evidence JSON. No analyzer, OCR provider, image preprocessing, fixture,
Dockerfile, dependency or lockfile changed. Existing untracked audit artifacts
were preserved.

The remaining physical limitation is intentional: trustworthy scale and a
validated measurement workflow are not part of this prototype. Existing
recognition/layout limitations remain; statuses are decision support, not final
regulatory approval.

Explicit conclusions:

1. Current raster uploads cannot reliably establish physical type size.
2. They cannot reliably establish physical CPI.
3. DPI metadata alone is insufficient.
4. Verified PDF/vector dimensions could enable a conditional future workflow.
5. Manual-only physical requirements should not force automated warning review.
6. They should not force an otherwise-clean application into Needs review.
7. The defensible model separates automated status from outstanding physical confirmation.
8. The revised UI, individual cards, summaries, batch details and export keep that requirement visible.

This materially improves reviewer UX without increasing automated recognition
claims. Recommend committing and deploying after normal review, not automatically.
After this focused pass, stop expanding the take-home unless a concrete regression
is found. Adding measurement features or further cosmetic/heuristic changes now
would add scope and risk rather than resolving this status-semantics issue.

