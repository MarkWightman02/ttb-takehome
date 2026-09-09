# TTB Label Verification

A standalone prototype for extracting text from alcohol-label artwork and comparing core fields with expected application data. The [take-home specification](https://github.com/treasurytakehome-rgb/instructions), including its stakeholder interviews, defines the intended product.

**Current status: single-label application-data and Government Health Warning verification.** The React UI accepts expected brand, class/type, ABV, and net contents plus one PNG, JPEG, or WebP label image. One primary action runs local OCR once, extracts deterministic candidates, compares application fields, and analyzes warning text and image evidence. Raw OCR remains available as supporting evidence. Results support reviewer decisions and do not constitute final regulatory approval. No AI credentials are required.

## Architecture

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
- Preprocessing: EXIF orientation correction, grayscale conversion, automatic contrast, up to 2× enlargement for small images, and light sharpening. The pipeline avoids hard thresholding that could erase label artwork. A separate request-scoped image preserves the original tonal evidence at the same orientation and scale for visual checks, so OCR contrast enhancement cannot create false contrast evidence.
- Privacy: bytes remain request-scoped. FastAPI may spool multipart data to secure framework-managed temporary storage; the upload is closed in a `finally` block. The application sends the normalized image to Tesseract over standard input and creates no persistent label file.
- Output: raw text, engine identifier, total and OCR processing duration, original image metadata, and useful warnings. Internally, the same Tesseract TSV response supplies word confidence, hierarchy, and pixel bounding boxes for warning analysis. Raw text is not a compliance decision.

Stylized fonts, curved bottles, glare, low contrast, unusual layouts, and poor photographs can reduce accuracy. This slice uses English Tesseract with page-segmentation mode 6. Word confidence and geometry are OCR evidence, not proof of typography or legal legibility.

### Verification endpoint and workflow

`POST /api/labels/verify` accepts one `file` plus multipart text fields `brand_name`, `class_type`, `abv`, and `net_contents`. It reuses the OCR upload and preprocessing pipeline and invokes OCR exactly once per request. The response contains the expected values, preserved extraction candidates, normalized values, a result for each field, plain-language explanations, raw OCR text, engine and duration metadata, and warnings.

- `match`: normalized values are deterministically equivalent.
- `review`: OCR damage or multiple plausible values make the result uncertain.
- `mismatch`: a reliable detected value differs from the application value.
- `not_found`: no reliable candidate was extracted; this is a field result, not an HTTP failure.

Brand and class/type comparison ignores capitalization, harmless punctuation, whitespace, Unicode presentation differences, and straight-versus-curly apostrophes. Conservative approximate text similarity can produce `review`, never `match`. ABV is compared as a percentage number without fuzzy matching. Metric net contents are converted to milliliters, so `1 L` and `1000 mL` match. Multiple distinct percentages or volumes require review even if one equals the expected value.

Extraction is deliberately deterministic and conservative. It uses explicit ABV/metric-volume patterns, a small generic set of beverage cues for class/type candidates, and filtered early OCR lines for brand candidates. It does not infer proof, accept incompatible volume units, use an exhaustive beverage taxonomy, or manufacture values when text is uncertain. Results assist reviewers and do not constitute approval, rejection, or a legal-compliance determination.

### Government Health Warning analysis

The prescribed statement and presentation rules come from [27 CFR 16.21](https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-16/subpart-C/section-16.21), [27 CFR 16.22](https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-16/subpart-C/section-16.22), and [current TTB warning guidance](https://www.ttb.gov/regulated-commodities/beverage-alcohol/beer/labeling/malt-beverage-health-warning). The application reports separate results for presence, wording, heading capitalization, heading boldness, non-bold body text, continuity, separation, contrast/legibility, type size, and characters per inch.

- Wording is compared deterministically with only Unicode, whitespace, line-wrap, and substantively equivalent typography normalization. Missing, changed, reordered, or materially punctuated text is not normalized away. Known OCR character damage produces `review`, never `match`.
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

`pnpm build` writes `frontend/dist`. For a local production-serving check, set `TTB_FRONTEND_DIST` to that directory's absolute path and start FastAPI. For example, in PowerShell from the root:

```powershell
$env:TTB_FRONTEND_DIST = (Resolve-Path frontend/dist).Path
$env:TTB_ENVIRONMENT = 'production'
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). The production bundle omits the development health indicator. Remove these environment overrides before returning to API-only development.

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

The container supports raw OCR, application-data verification, and warning analysis. A hosted reviewer URL and additional beverage-dependent fields remain future deliverables.

## Next increment

Add producer/bottler name and address extraction, followed by imported-product origin applicability, as a separate deterministic field-verification slice. Batch processing and difficult-photo enhancement should remain later work.
