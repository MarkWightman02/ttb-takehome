# TTB Label Verification

A standalone prototype foundation for comparing alcohol-label artwork with application data. The [take-home specification](https://github.com/treasurytakehome-rgb/instructions), including its stakeholder interviews, defines the intended product.

**Current status: runnable scaffold only.** The React shell connects to a working FastAPI health endpoint. Application-data entry, label upload, OCR, regulatory checks, and verification results are not implemented. The UI labels those areas as placeholders. No documents are accepted or stored, and no AI credentials are required.

## Architecture

```text
frontend/           React + TypeScript + Vite; Vitest and ESLint
backend/app/        FastAPI routes, typed models, config, errors, OCR protocol
backend/tests/      pytest API and foundation checks
docs/               Requirements matrix and architecture decisions
Dockerfile          Development targets and single-container production build
docker-compose.yml  Frontend/backend development services with hot reload
```

Vite proxies `/api` to FastAPI during development. In production, FastAPI serves the compiled React files and the API from one container. OCR is a protocol only, ready for a later local implementation. There is no database, authentication, COLAs Online integration, batch processing, or external AI API dependency.

See [requirements](docs/requirements.md) and [architecture](docs/architecture.md) for scope, sources, request flow, assumptions, and tradeoffs.

## Prerequisites

- Python 3.12 (verified with 3.12.14).
- Node.js 24 LTS and pnpm 11.19.0. Install pnpm with `npm install --global pnpm@11.19.0` if needed.
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

Open [http://localhost:8000](http://localhost:8000). This image contains the compiled frontend and runs FastAPI as a non-root user. It includes a health check and needs no external AI service or storage volume. The default final Docker stage is also `production`.

Container checks can be run with:

```sh
docker compose run --rm backend python -m pytest -c backend/pyproject.toml backend/tests
docker compose run --rm frontend pnpm test
```

This foundation does not yet fulfill the specification's final deployed-prototype deliverable.

## Next increment

Implement and test one label plus application-data submission, then add a local OCR provider behind the existing protocol and deterministic field comparisons. Preserve source evidence in explanations, handle uncertainty explicitly, and measure normal-label latency against the approximately five-second target. Confirm applicable TTB rules before encoding regulatory checks. Batch processing and difficult-photo enhancement follow a reliable single-label workflow.
# ttb-takehome
# ttb-takehome
