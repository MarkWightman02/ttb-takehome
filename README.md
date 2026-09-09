# TTB Label Verification

A standalone prototype for extracting text from alcohol-label artwork and comparing common fields with expected application data. The [take-home specification](https://github.com/treasurytakehome-rgb/instructions), including its stakeholder interviews, defines the intended product.

## Live demo

[https://ttb.markwightman.org](https://ttb.markwightman.org)

## What it does

The reviewer enters application data, uploads one PNG, JPEG, or WebP label, and selects **Verify Label**. The application runs local OCR once, compares structured label evidence with the supplied values, analyzes the Government Health Warning, and presents field-level results with explanations and optional raw OCR evidence.

Results support reviewer decisions. They do not approve or reject an application and do not determine legal compliance.

## Why this approach

- **Local Tesseract:** operation does not require cloud OCR, an LLM, credentials, or runtime internet access.
- **Deterministic rules:** normalized values and preserved evidence make each result repeatable and explainable.
- **Explicit uncertainty:** `review` and `not_found` avoid turning weak OCR or incomplete image evidence into false confidence.
- **Request-scoped processing:** label bytes go to Tesseract over standard input and are not persisted by the application.
- **One production container:** the compiled UI, API, Tesseract, and English language data deploy together.

## Supported verification

- Brand name; class/type designation; numeric ABV; metric net contents.
- Producer/bottler name and address.
- Country of origin when the reviewer identifies the application as imported; domestic origin is `not_applicable`.
- Government Health Warning presence, prescribed wording, heading capitalization, and conservative image evidence for weight, continuity, separation, and contrast.
- The applicable warning type-size and characters-per-inch tiers, with physical confirmation left to the reviewer when scale is unavailable.

## What is intentionally not automated

- Final legal or regulatory approval.
- Physical type-size or characters-per-inch proof from an unscaled raster image.
- A comprehensive beverage-specific applicability or regulation engine.
- Batch upload, authentication, persistence, COLAs Online integration, and external/cloud AI.

## Architecture

```text
Image + Application Data
  → Validation → Preprocessing → Tesseract OCR (once)
  → Structured Extraction → Deterministic Comparison + Warning Analysis
  → Reviewer Results
```

```text
frontend/           React + TypeScript + Vite; Vitest and ESLint
backend/app/        FastAPI routes, typed models, validation, preprocessing, local OCR
backend/tests/      pytest API and foundation checks
docs/               Requirements matrix and architecture decisions
Dockerfile          Development targets and single-container production build
docker-compose.yml  Frontend/backend development services with hot reload
```

Vite proxies `/api` to FastAPI during development. In production, FastAPI serves the compiled React files and the API from one container. Local Tesseract runs behind the replaceable OCR protocol. There is no database, authentication, COLAs Online integration, batch processing, or external AI API dependency.

See [requirements](docs/requirements.md) and [architecture](docs/architecture.md) for scope, sources, request flow, assumptions, and tradeoffs.

## Prerequisites

- Python 3.12 (verified with 3.12.14).
- Node.js 24 LTS and pnpm 11.19.0. Install pnpm with `npm install --global pnpm@11.19.0` if needed.
- Tesseract OCR with English language data, available as `tesseract` on `PATH`. The Docker image installs it automatically.
- Docker with Compose v2, only for the container instructions.

Dependency installation and image builds need network access. Once built, this scaffold needs no outbound network access. Direct dependency versions, frontend transitive dependencies, Python constraints, and container image versions are pinned.

## Local setup

Run these commands from the repository root. Create a virtual environment:

```sh
python -m venv .venv
```

Activate it in PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Or in macOS/Linux shells:

```sh
source .venv/bin/activate
```

If PowerShell activation is restricted, use `.venv\Scripts\python.exe` instead of `python` in the commands below; no execution-policy change is necessary.

Install backend dependencies, including test/lint tools:

```sh
python -m pip install -c backend/constraints.txt -e "./backend[dev]"
```

Install frontend dependencies:

```sh
cd frontend
pnpm install --frozen-lockfile
cd ..
```

Optionally copy `.env.example` to `.env` at the repository root. Defaults work without that file. The backend reads `TTB_` settings, and Vite reads `VITE_API_PROXY_TARGET` for its development proxy. Neither setting needs to contain a secret.

Verify the local OCR runtime before starting the API:

```sh
tesseract --version
```

If Tesseract is installed outside `PATH`, set `TTB_TESSERACT_COMMAND` in `.env` to its executable path. Normal unit tests inject an OCR provider; the conditional real-engine tests execute preprocessing and the installed Tesseract binary when it is available.

### Run the backend

From the root with the virtual environment active:

```sh
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Health: [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)

```json
{"status":"ok","service":"ttb-label-verification"}
```

API documentation: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs). Health reports that the API is running; it does not check an OCR engine.

### OCR endpoint

`POST /api/labels/ocr` accepts exactly one multipart field named `file`.

- Supported formats: PNG, JPEG, and WebP. File contents must match the declared MIME type; filename extensions are not trusted.
- Limits: 10 MB, at most 12,000 pixels on either edge, and at most 40 million pixels total. These defaults are configurable through the documented `TTB_` settings.
- Preprocessing: EXIF orientation correction, grayscale conversion, automatic contrast, selective enlargement toward a 2,400-pixel long edge (up to 4× for low-resolution inputs), and light sharpening. The pipeline avoids hard thresholding that could erase label artwork. A separate request-scoped image preserves the original tonal evidence at the same orientation and scale for visual checks, so OCR contrast enhancement cannot create false contrast evidence.
- Privacy: bytes remain request-scoped. FastAPI may spool multipart data to secure framework-managed temporary storage; the upload is closed in a `finally` block. The application sends the normalized image to Tesseract over standard input and creates no persistent label file.
- Output: raw text, engine identifier, total and OCR processing duration, original image metadata, and useful warnings. Internally, the same Tesseract TSV response supplies word confidence, hierarchy, and pixel bounding boxes for warning analysis. Raw text is not a compliance decision.

Stylized fonts, curved bottles, glare, low contrast, unusual layouts, and poor photographs can reduce accuracy. Low-resolution labels may therefore produce `review` or `not_found` rather than a guessed value. This slice uses English Tesseract with sparse-text page-segmentation mode 11, which performed more reliably on the evaluated side-by-side TTB samples. Word confidence and geometry are OCR evidence, not proof of typography or legal legibility.

### Verification endpoint and workflow

`POST /api/labels/verify` accepts one `file` plus multipart fields `brand_name`, `class_type`, `abv`, `net_contents`, `producer_name`, `producer_address`, and the boolean `imported_product`. `country_origin` is required only when `imported_product` is true. It reuses the OCR upload and preprocessing pipeline. Every request begins with one full-image TSV pass; only uncertain brand/class candidates or a missing volume with a defensible nearby region can trigger targeted crop OCR. At most three crop calls are allowed, so a request uses one to four Tesseract invocations. The raw `/ocr` endpoint remains one invocation. The verification response contains expected values, preserved candidates, normalized values, a result for each field, explanations, raw OCR text, engine and duration metadata, warnings, Government Warning analysis, total OCR-call count, and secondary crop-refinement evidence.

- `match`: normalized values are deterministically equivalent.
- `review`: OCR damage or multiple plausible values make the result uncertain.
- `mismatch`: a reliable detected value differs from the application value.
- `not_found`: no reliable candidate was extracted; this is a field result, not an HTTP failure.
- `not_applicable`: the country-of-origin check was explicitly skipped for a domestic application; it does not degrade the overall summary.

Brand and class/type comparison ignores capitalization, harmless punctuation, whitespace, Unicode presentation differences, and straight-versus-curly apostrophes. Conservative approximate text similarity can produce `review`, never `match`. ABV is compared as a percentage number without fuzzy matching. Metric volume plus the label-relevant U.S. pint and fluid-ounce forms are converted to milliliters using exact definitions: one U.S. fluid ounce is 29.5735295625 mL and one U.S. pint is 473.176473 mL. Thus `1 L` and `1000 mL`, or `1 PINT` and `16 FL OZ`, compare equivalently. Other imperial units are not silently converted. Multiple distinct percentages or volumes require review even if one equals the expected value.

Extraction is deliberately deterministic and conservative. It reconstructs spatial lines and lightweight panels from Tesseract TSV words before selecting candidates, so side-by-side front, back, and warning panels are not treated as one flattened reading stream. Brand ranking considers line prominence, panel position, compactness, confidence, repetition, and spatially coherent multiline artwork. Class/type joins require nearby, aligned lines in the same panel; an `IPA` cue can preserve a nearby OCR-damaged type line for review. The localized Government Warning region is excluded from generic product-field extraction. Explicit patterns handle ABV and supported volume units. The extractor does not infer proof, accept incompatible volume units, use an exhaustive beverage taxonomy, or manufacture values when text is uncertain. Results assist reviewers and do not constitute approval, rejection, or a legal-compliance determination.

Targeted refinement crops the already-preprocessed, request-scoped pixels using TSV candidate geometry and slightly expanded margins, then applies local autocontrast and light sharpening. Short display blocks use Tesseract PSM 6; coherent class/type and compact volume lines use PSM 7. Each crop has a one-second timeout. Refinement is retained only when its own OCR confidence is adequate and comparison evidence becomes stronger; the expected application value is never inserted into or used to rewrite OCR output. Full-image candidates, refined text, confidence, selected/not-selected state, PSM, duration, and crop bounds remain available as secondary evidence. The Government Warning continues to use only the full-image pass.

Producer extraction recognizes a small set of role cues such as `Bottled by`, `Distilled and bottled by`, `Produced by`, and `Imported by`. It supports same-line company/city/state blocks as well as multiline cue, company, and location layouts. Nearby address candidates must belong to the same spatial panel; several similarly plausible addresses require review. Address comparison ignores case and punctuation and normalizes U.S. state names to abbreviations; partial addresses require review, while distinct cities or states remain mismatches. This is not postal validation or geocoding. Origin extraction recognizes conservative phrases such as `Product of`, `Produced in`, `Imported from`, and `Made in`. Import applicability always comes from the application toggle, never an OCR guess; multiple distinct statements, ambiguous wording, or unfamiliar wording remains review or not found.

### Government Health Warning analysis

The prescribed statement and presentation rules come from [27 CFR 16.21](https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-16/subpart-C/section-16.21), [27 CFR 16.22](https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-16/subpart-C/section-16.22), and [current TTB warning guidance](https://www.ttb.gov/regulated-commodities/beverage-alcohol/beer/labeling/malt-beverage-health-warning). The application reports separate results for presence, wording, heading capitalization, heading boldness, non-bold body text, continuity, separation, contrast/legibility, type size, and characters per inch.

- Wording is compared deterministically with only Unicode, whitespace, line-wrap, and substantively equivalent typography normalization. Bounded token differences are evaluated using prescribed-clause structure, edit shape, and localized TSV confidence. Likely OCR character, punctuation, or token-fragmentation damage produces `review`, never `match`; confidently missing, changed, or reordered prescribed language remains `mismatch`.
- Capitalization uses the original OCR representation. Plain OCR text does not prove boldness.
- Warning location is derived from Tesseract words, hierarchy, confidence, and bounding boxes. The pixel crop is request-scoped and is not persisted.
- Bold/non-bold evidence uses a conservative within-warning comparison of glyph stroke index and ink density. Similar weights, small text, missing coordinates, or weak image evidence return `review`.
- Continuity and separation use clause order, OCR block/paragraph relationships, unexpected interruptions, bounding boxes, and surrounding whitespace. Normal line wrapping is allowed.
- Contrast uses local luminance separation, background variation, and OCR quality. It is an estimate, not a legal legibility determination; gradients, artwork, glare, or uncertain evidence return `review`.
- For containers up to 237 mL, over 237 mL through 3 L, and over 3 L, the reported minimum type sizes are respectively 1, 2, and 3 mm; maximum characters per inch are respectively 40, 25, and 12. Ordinary raster pixels do not establish physical millimeters or inches, so both actual-measurement checks remain `review` without a trustworthy physical scale.

TTB has itself noted that submitted images can distort size, CPI, and contrast evidence; see [TTB Industry Circular 2011-04](https://www.ttb.gov/public-information/industry-circulars/archives/2011/11-04). The prototype therefore favors explicit manual review over false visual certainty.

### Run the frontend

In a second terminal:

```sh
cd frontend
pnpm dev
```

Open [http://localhost:5173](http://localhost:5173). A development-only status indicator confirms the backend connection. Start the backend first; after changing its availability, refresh the page to repeat the check.

### Run checks

From the root with the virtual environment active:

```sh
python -m pytest -c backend/pyproject.toml backend/tests
python -m ruff check backend
python -m ruff format --check backend
```

From `frontend/`:

```sh
pnpm test
pnpm lint
pnpm typecheck
pnpm format:check
pnpm build
```

Run the deterministic generated-label evaluation corpus against real Tesseract:

```sh
python backend/scripts/evaluate_labels.py
```

Add `--json` for case-level OCR text, expected/actual differences, per-check counts, and latency data. The script exits nonzero for OCR/processing failures or false confident matches. Corpus metadata and images are generated in memory; proprietary assets and output files are not required.

Run the separate repository real-label regression set:

```sh
python backend/scripts/evaluate_real_labels.py
```

The real-label runner discovers matching PNG/JPEG/WebP image and JSON stems under `examples/`, decodes the actual image format, and runs the production flow: preprocessing, one full-image Tesseract TSV invocation, spatial reconstruction, warning exclusion, conditional bounded crop refinement, extraction, and comparison. `--json` includes raw full-image OCR, initial and final candidates/results, crop OCR evidence, call counts, every field and warning result, and per-case latency. Real-label counts are intentionally reported separately from the generated corpus.

`pnpm build` writes `frontend/dist`. For a local production-serving check, set `TTB_FRONTEND_DIST` to that directory's absolute path and start FastAPI. For example, in PowerShell from the root:

```powershell
$env:TTB_FRONTEND_DIST = (Resolve-Path frontend/dist).Path
$env:TTB_ENVIRONMENT = 'production'
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). The production bundle omits the development health indicator. Remove these environment overrides before returning to API-only development.

## Performance

On the Linux development host, the 18-case generated corpus completed all 306 expected status checks correctly with no OCR failures. It includes product-left/warning-right and warning-left/product-right artwork whose raw Tesseract order interleaves the two panels. Representative stage latency in milliseconds was:

| Stage | Median | p90 | Slowest |
| --- | ---: | ---: | ---: |
| Preprocessing | 121 | 129 | 162 |
| Tesseract OCR | 232 | 250 | 253 |
| Extraction, comparison, and warning analysis | 96 | 99 | 99 |
| Total case processing | 502 | 521 | 764 |

These synthetic-label results are a reproducible deterministic regression baseline. Their exact status accuracy is not an estimate of accuracy, precision, or recall on real submitted labels, and the timing is not a promise for every photograph or host. They are comfortably below the stakeholder's approximately five-second ordinary-use target on the measured environment.

The six repository real-label examples produced 32 application-field matches, 1 review, 4 not-found results, 5 not-applicable results, no field mismatches, and no false confident matches in the measured targeted-refinement run. Median OCR calls per case were 1.5 and the maximum was 4. All six Government Warning results remained `review`; targeted crops are not used for warning analysis. Median cumulative OCR time was approximately 442 ms, median total time approximately 957 ms, and the slowest case approximately 1.20 seconds. Six TTB sample images are regression evidence, not an accuracy benchmark or a general real-world accuracy estimate.

## Docker

### Development with hot reload

From the root:

```sh
docker compose up --build
```

Open [http://localhost:5173](http://localhost:5173). The frontend proxies API requests to the backend service; the API is also available on [http://localhost:8000/api/health](http://localhost:8000/api/health). Source directories are mounted for reload. Rebuild after changing dependencies or build configuration.

Stop with Ctrl+C, then `docker compose down`.

### Single-container production build

```sh
docker build --target production -t ttb-label-verification .
docker run --rm --name ttb-label-verification -p 127.0.0.1:8000:8000 ttb-label-verification
```

Open [http://localhost:8000](http://localhost:8000). This image contains the compiled frontend, FastAPI, Tesseract, and English OCR data, and runs as a non-root user. It includes a health check and needs no external AI service or storage volume. The default final Docker stage is also `production`.

Container checks can be run with:

```sh
docker compose run --rm backend python -m pytest -c backend/pyproject.toml backend/tests
docker compose run --rm frontend pnpm test
```

The container supports raw OCR, complete common-field application-data verification, and warning analysis. The reviewer deployment is available at [https://ttb.markwightman.org](https://ttb.markwightman.org); local and container instructions remain the reproducible submission path.

## Limitations and tradeoffs

Deterministic cues are intentionally conservative. Unusual layouts, curved or reflective containers, stylized type, glare, and poor photographs may yield `review` or `not_found`. The generated evaluation corpus covers several layouts and a mildly degraded image but is not representative of every production label. Image-based warning checks provide evidence, not measurements of physical artwork. English is the only bundled OCR language.

## Submission status

The scoped single-label prototype is implemented and deployed. Further real-label sampling would improve confidence in deterministic extraction limits, but the generated corpus and six TTB sample fixtures remain deliberately separate and neither is presented as production accuracy evidence.
