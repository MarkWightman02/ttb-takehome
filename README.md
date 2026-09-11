# TTB Label Verification

A standalone decision-support prototype for Treasury/TTB label reviewers. It extracts visible information from submitted alcohol-label artwork and compares it with application values supplied by the reviewer. The [take-home instructions](https://github.com/treasurytakehome-rgb/instructions) and stakeholder interviews define its scope.

## Try the live demo

[Open the reviewer prototype](https://ttb.markwightman.org)

This hosted prototype is a take-home demonstration, not an official Treasury or TTB service. It does not approve applications or determine legal compliance.

## Reviewer workflow

1. Start with the expected application/COLA data.
2. Enter the brand, class/type, ABV, net contents, responsible party, address, and import information.
3. Upload one submitted PNG, JPEG, or WebP label image.
4. Select **Verify Label**.
5. Review the extracted evidence, field comparisons, and Government Health Warning checks.

The application runs local OCR, extracts visible label information, and identifies matches, discrepancies, missing evidence, and uncertain items. It is standalone and does not connect to COLAs Online.

Single-label review remains the default. In this feature branch, select **Batch verification** for
the optional manifest-based workflow; the stable public deployment is updated separately.

## Optional batch verification

Download the CSV template in the batch view, add one application row per image, select the
corresponding images, review the deterministic filename mapping, and select **Verify Batch**. Each
valid item is sent separately to the existing `POST /api/labels/verify` endpoint, so batch and
single-label review use the same OCR, extraction, comparison, warning analysis, and error behavior.

The CSV columns are:

```text
image_filename,brand_name,class_type,abv,net_contents,producer_name,producer_address,imported_product,country_origin
```

Use `true` or `false` for `imported_product`; `country_origin` is required only for imports. The
parser supports quoted commas, escaped quotes, CRLF, a UTF-8 BOM, and blank optional values.
Filename matching removes CSV path prefixes and normalizes Unicode composition, surrounding
whitespace, and case. Duplicate names, missing images, unmatched uploads, unsupported images, and
invalid rows remain visible rather than being guessed or skipped.

The browser accepts at most 300 manifest records and schedules two verification requests at a
time. One failed label does not stop the queue, failed items can be retried, and stopping prevents
new requests while active ones finish. Each row shows a concise outcome and can expand the normal
detailed result. Results can be exported as CSV. Batch state is browser-local and is discarded on
reload; the server stores no batch history, application record, or image.

## Result meanings

- **Match:** image-derived evidence supports the entered application value or checked requirement.
- **Review:** evidence is plausible, but OCR or image uncertainty prevents a confident automated conclusion. This is intentional conservative behavior, not necessarily an error.
- **Mismatch:** reliable evidence indicates a substantive discrepancy.
- **Not found:** the system could not locate reliable supporting label evidence.
- **Not applicable:** the check does not apply to the submitted application context.

## What it checks

- Brand name, class/type designation, numeric ABV, and supported metric or U.S. fluid-volume forms.
- Producer/bottler name and address.
- Country of origin when the reviewer marks the application as imported.
- Government Health Warning text and available image-based presentation evidence.

Physical type size and characters per inch still require reviewer confirmation because an ordinary raster image has no trustworthy physical scale. The prototype does not implement a comprehensive beverage-regulation engine, authentication, persistence, or final regulatory decisions.

## How it works

```text
Label image + expected application data
  → One request, or an optional two-worker browser queue
  → Validation and selective preprocessing/upscaling
  → Full-image Tesseract TSV OCR (PSM 11)
  → Spatial panel reconstruction and warning localization
  → Up to three conditional regional OCR refinements
  → Deterministic extraction, normalization, and comparison
  → Explained reviewer results and preserved OCR evidence
```

FastAPI and Pydantic provide the API and typed results; React, TypeScript, and Vite provide the reviewer interface. Tesseract runs locally. Difficult brand, class/type, or net-contents regions can receive bounded PSM 6/7 crop refinement, while the full-image result remains the layout and warning evidence. No cloud OCR or LLM is required.

Uploaded images are request-scoped and are not persisted by the application. No database is required, and the production container runs as a non-root user. These are implementation choices, not a general security certification.

## Repository layout

```text
frontend/           React + TypeScript + Vite; Vitest and ESLint
frontend/src/batchVerification.ts  CSV validation, mapping, queue, summaries, export
backend/app/        FastAPI routes, typed models, validation, preprocessing, local OCR
backend/tests/      pytest API and foundation checks
docs/               Requirements matrix and architecture decisions
Dockerfile          Development targets and single-container production build
docker-compose.yml  Frontend/backend development services with hot reload
```

Vite proxies `/api` to FastAPI during development. In production, FastAPI serves the compiled React files and API from one container.

See [requirements](docs/requirements.md) and [architecture](docs/architecture.md) for scope, sources, request flow, assumptions, and tradeoffs.

## Prerequisites

- Python 3.12 (verified with 3.12.14).
- Node.js 24 LTS and pnpm 11.19.0. Install pnpm with `npm install --global pnpm@11.19.0` if needed.
- Tesseract OCR with English language data, available as `tesseract` on `PATH`. The Docker image installs it automatically.
- Docker with Compose v2, only for the container instructions.

Dependency installation and image builds need network access. Once built, the application needs no outbound network access. Direct dependency versions, frontend transitive dependencies, Python constraints, and container image versions are pinned.

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

`POST /api/labels/verify` accepts one image plus the expected application fields. Country of origin is required only when the reviewer marks the product as imported. Each request starts with one full-image TSV pass; uncertain brand/class candidates or a missing volume with suitable geometry can trigger up to three crop OCR calls. The raw `/api/labels/ocr` endpoint remains a single pass.

Comparison is deterministic and field-specific: harmless text presentation differences are normalized, ABV is compared numerically, and supported metric/U.S. fluid volumes are normalized to milliliters. Ambiguous or missing evidence is preserved for review instead of guessed. The response includes explanations, raw OCR, warning analysis, timing, call count, and secondary refinement evidence. See [architecture.md](docs/architecture.md) for extraction rules and tradeoffs.

### Government Health Warning analysis

The prescribed statement and presentation rules come from [27 CFR 16.21](https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-16/subpart-C/section-16.21), [27 CFR 16.22](https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-16/subpart-C/section-16.22), and [current TTB warning guidance](https://www.ttb.gov/regulated-commodities/beverage-alcohol/beer/labeling/malt-beverage-health-warning). The application reports separate results for presence, wording, heading capitalization, heading boldness, non-bold body text, continuity, separation, contrast/legibility, type size, and characters per inch.

- **Deterministic text checks:** warning presence, prescribed wording, and heading capitalization use OCR text and localized TSV confidence. Likely OCR damage produces `review`; reliable substantive differences can produce `mismatch`.
- **Image-based evidence:** heading/body weight, continuity, separation, and contrast use OCR geometry and request-scoped pixels. Weak, distorted, or ambiguous evidence remains `review`.
- **Manual physical confirmation:** the applicable minimum type-size and maximum-characters-per-inch tiers are reported, but actual dimensions remain `review` because raster pixels do not establish millimeters or inches.

Automated warning status and manual physical confirmation are separate. Clean automated
checks show **Automated checks matched**, with neutral physical cards still marked
**Manual confirmation**. Genuine OCR/image uncertainty and mismatches continue to take
priority in the overall summary and batch rows. The API adds `automated_status` and
`manual_confirmation_required` inside `government_warning`; its legacy `overall_status`
still includes physical reviews. Batch CSV retains that legacy column and adds
`automated_warning_status` and `manual_physical_confirmation_required`. Batch `match`
means automated checks matched, not physical compliance. DPI metadata alone is not trusted.
See [physical-confirmation semantics](docs/physical-warning-semantics.md) for the decision
and authoritative references. No PDF or scale-measurement support was added.

These results support reviewer inspection; they are not regulatory approval or a legal-compliance determination. Detailed rules and limitations are documented in [architecture.md](docs/architecture.md).

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

- **Synthetic regression:** 18 generated cases completed all 306 expected status checks without an OCR failure. Median total time was about 0.5 seconds.
- **Real-label regression:** six TTB sample fixtures had a median total under one second; the slowest completed in about 1.2 seconds with the bounded maximum of four OCR calls.
- **Optional batch check:** a local production container processed one, five, and ten one-call
  samples in about 0.57, 2.02, and 3.50 seconds respectively at concurrency two. Mean per-item
  latency was about 0.68 seconds for the concurrent runs, and container memory peaked near 170 MB.

These are repeatable measurements from one Linux development host, not production accuracy,
latency, or capacity guarantees. Generated and real-label results are intentionally reported
separately.

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

The container supports raw OCR, complete common-field application-data verification, optional
client-orchestrated batch verification, and warning analysis. The reviewer deployment is available
at [https://ttb.markwightman.org](https://ttb.markwightman.org); local and container instructions
remain the reproducible submission path.

## Limitations and tradeoffs

- Stylized or decorative text, unusual layouts, glare, low resolution, and photographed containers can require manual review.
- Raster images cannot conclusively establish physical type dimensions.
- Responsible-party information is not inferred without sufficient label evidence.
- English is the only bundled OCR language.
- The prototype is standalone and is not integrated with COLAs Online.
- Batch state is not persisted or resumable after a browser reload.
- Generated and sample fixtures are regression evidence, not production-accuracy estimates.

## Submission status

The scoped single-label prototype and optional client-side batch enhancement are implemented. The
stable public deployment may be updated separately after branch review. Further real-label sampling
would improve confidence in deterministic extraction limits, but the generated corpus and six TTB
sample fixtures remain deliberately separate and neither is presented as production accuracy
evidence.
