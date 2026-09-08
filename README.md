# TTB Label Verification

A standalone prototype for extracting text from alcohol-label artwork and, in a later slice, comparing it with application data. The [take-home specification](https://github.com/treasurytakehome-rgb/instructions), including its stakeholder interviews, defines the intended product.

**Current status: single-label OCR slice.** The React UI accepts one PNG, JPEG, or WebP label image, previews it, sends it to FastAPI for validation and conservative preprocessing, and displays raw text from local Tesseract OCR. Application-data entry, field comparison, and regulatory decisions are not implemented. No AI credentials are required.

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

If Tesseract is installed outside `PATH`, set `TTB_TESSERACT_COMMAND` in `.env` to its executable path. This development machine did not have Tesseract installed during the recorded verification; API and UI tests use dependency injection and do not fake a successful production OCR result.

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
- Preprocessing: EXIF orientation correction, grayscale conversion, automatic contrast, up to 2× enlargement for small images, and light sharpening. The pipeline avoids hard thresholding that could erase label artwork.
- Privacy: bytes remain request-scoped. FastAPI may spool multipart data to secure framework-managed temporary storage; the upload is closed in a `finally` block. The application sends the normalized image to Tesseract over standard input and creates no persistent label file.
- Output: raw text, engine identifier, total and OCR processing duration, original image metadata, and useful warnings. Raw text is not a compliance decision.

Stylized fonts, curved bottles, glare, low contrast, unusual layouts, and poor photographs can reduce accuracy. This slice uses English Tesseract with page-segmentation mode 6 and does not report word-level confidence or label typography such as boldness.

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

This OCR slice does not yet fulfill the specification's application-comparison or final deployed-prototype deliverables.

## Next increment

Add the application-data form and deterministic field-level comparison for one label, beginning with brand name and alcohol content. Preserve raw OCR evidence in each explanation, handle uncertainty explicitly, and measure the full workflow against the approximately five-second target. Confirm applicable TTB rules before encoding regulatory checks. Batch processing and difficult-photo enhancement follow a reliable single-label workflow.
