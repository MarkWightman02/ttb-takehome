# Development

Setup and day-to-day commands for working on the source. If you only want to *run* the application, the Quick Start in the [README](../README.md) is all you need — nothing in this file is required for that.

- Design and rationale: [architecture.md](architecture.md)
- Comparison behavior in brief: [VERIFICATION_LOGIC.md](VERIFICATION_LOGIC.md)
- When something breaks: [TROUBLESHOOTING.md](TROUBLESHOOTING.md)

## Ways to run it

| Method | Command | Use when |
| --- | --- | --- |
| Production container (default) | `docker compose up --build -d` | Reviewing, or checking the shipped behavior |
| Docker dev profile | `docker compose --profile dev up --build backend frontend` | Editing source without installing Python/Node locally |
| Native | See [Native setup](#native-setup) | Running tests and linters directly, fastest iteration |

## Docker development profile

```sh
docker compose --profile dev up --build backend frontend
```

- Frontend (Vite dev server, hot reload): `http://localhost:5173`
- Backend (FastAPI with reload): `http://localhost:8000`

The Vite dev server proxies `/api` to the backend container, so the browser talks to one origin. Source directories are bind-mounted, so edits to `frontend/src` and `backend/app` take effect without rebuilding. Rebuild when dependencies or build configuration change. Stop with Ctrl+C, then `docker compose down`.

> **Name both services.** Do not run the bare `docker compose --profile dev up`. The production `app` service has no profile, so it is always included and would try to claim port 8000 alongside the dev backend. See [TROUBLESHOOTING.md](TROUBLESHOOTING.md#docker-compose---profile-dev-up-causes-a-port-conflict).

## Native setup

Prerequisites:

- **Python 3.12** (the container builds on 3.12.14)
- **Node.js 24** and **pnpm 11.19.0** (`npm install --global pnpm@11.19.0`)
- **Tesseract OCR** with English language data, on your `PATH`

Verify Tesseract before starting the API:

```sh
tesseract --version
```

From the repository root:

```sh
python -m venv .venv
source .venv/bin/activate        # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -c backend/constraints.txt -e "./backend[dev]"
cd frontend && pnpm install --frozen-lockfile && cd ..
```

Configuration is optional. Copy `.env.example` to `.env` in the repository root only if you want to change a default; no value is a secret. Settings use the `TTB_` prefix — for example `TTB_TESSERACT_COMMAND` if Tesseract is installed outside your `PATH`.

### Run the backend

```sh
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- Health: `http://127.0.0.1:8000/api/health`
- Interactive API docs: `http://127.0.0.1:8000/docs`

By itself this serves the API only. To serve a built frontend from FastAPI as production does, build the frontend and point `TTB_FRONTEND_DIST` at the absolute path of `frontend/dist`.

### Run the frontend

In a second terminal:

```sh
cd frontend
pnpm dev
```

Open `http://localhost:5173`. In development the page shows a small backend-connection indicator; the production bundle omits it.

## Tests and checks

Backend, from the repository root with the virtual environment active:

```sh
python -m pytest -c backend/pyproject.toml backend/tests
python -m ruff check backend
python -m ruff format --check backend
```

Frontend, from `frontend/`:

```sh
pnpm test          # Vitest
pnpm lint          # ESLint, zero warnings allowed
pnpm typecheck     # tsc --noEmit
pnpm format:check  # Prettier
pnpm build         # tsc --noEmit && vite build
```

Backend unit tests inject a stub OCR provider, so they do not need Tesseract installed. A smaller set of conditional tests exercises the real binary when it is available.

## Evaluation scripts

These run the real OCR engine over fixture sets and are slower than the test suite. They are diagnostics, not part of the test run.

```sh
python backend/scripts/evaluate_labels.py        # generated in-memory corpus
python backend/scripts/evaluate_real_labels.py   # the real fixtures in examples/
python backend/scripts/evaluate_warnings.py      # Government Warning checks across examples/
```

Add `--json` to the first two for full per-case detail. `evaluate_labels.py` exits non-zero on a processing failure or a false confident match, so it is usable as a gate. Generated and real-label numbers are deliberately reported separately and neither is a statistical accuracy claim — see [examples/README.md](../examples/README.md).

## Production image

`docker build --target production -t ttb-label-verification .`

The Dockerfile is multi-stage:

1. A Node stage installs frontend dependencies from the lockfile and runs `pnpm build`.
2. A Python stage installs Tesseract with English language data and the backend package under pinned constraints.
3. The final `production` stage copies the built frontend in, creates a non-root user (uid 10001), and runs Uvicorn.

The result is one container serving the compiled React app and the API on port 8000, with a `HEALTHCHECK` that polls `/api/health`. It needs no database, no volume, and no outbound network access at runtime. `docker compose up --build -d` builds exactly this stage.

## Project layout

```text
frontend/src/                 React UI, batch logic, API client
frontend/src/components/      Single-label and batch workflows
backend/app/api/              FastAPI routes
backend/app/models/           Pydantic request/response models
backend/app/services/         OCR, preprocessing, extraction, comparison, warning analysis
backend/evaluation/           Fixture corpus and evaluation runners
backend/tests/                pytest suite
docs/                         This documentation set
examples/                     Label fixtures and a ready-made batch manifest
```

Extraction, normalization, comparison, and warning analysis are plain modules with no HTTP dependency, which is what makes them directly unit-testable. See [architecture.md](architecture.md) for the reasoning behind each boundary.
