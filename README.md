# TTB Label Verification

A standalone decision-support prototype for Treasury/TTB label reviewers. It reads visible information from submitted alcohol-label artwork and compares it with application values entered by the reviewer, flagging matches, differences, and anything that needs a human look. The [take-home instructions](https://github.com/treasurytakehome-rgb/instructions) and stakeholder interviews define its scope.

No API keys, database, cloud service, or local OCR installation is required. The Docker image contains the frontend, backend, Tesseract, and required language data; nothing else needs to be installed to run it.

## Live demo

[https://ttb.markwightman.org](https://ttb.markwightman.org)

This hosted prototype is a take-home demonstration, not an official Treasury or TTB service. It does not approve applications or determine legal compliance.

## Quick Start

Prerequisites: **Git** and **Docker** (Docker Desktop, or Docker Engine with Compose v2).

```sh
git clone https://github.com/MarkWightman02/ttb-takehome.git
cd ttb-takehome
docker compose up --build -d
```

Open [http://localhost:8000](http://localhost:8000).

Verify:

```sh
curl http://localhost:8000/api/health
# {"status":"ok","service":"ttb-label-verification"}
```

Stop:

```sh
docker compose down
```

This builds and runs the single production container: compiled frontend, FastAPI, Tesseract, and English OCR data, served on one port as a non-root user. No environment variables need to be set — the image already configures itself for production. No host directories are mounted and nothing is written outside the container.

## How to use

1. Enter the information from the alcohol label application.
2. Upload the submitted label artwork.
3. Select **Verify Label** and review any differences.

An optional **Batch verification** view repeats this for many labels at once — see [Batch verification](#batch-verification) below.

## Result meanings

- **Match:** the label supports the entered application value or checked requirement.
- **Review:** the evidence is plausible, but the tool cannot reach a confident conclusion. This is intentional conservative behavior, not necessarily an error.
- **Mismatch:** the label and application appear to differ.
- **Not found:** the tool could not locate reliable supporting evidence on the label.
- **Not applicable:** the check does not apply to this application (for example, country of origin on a domestic product).

## Government Health Warning & physical measurements

The Government Warning's presence, exact prescribed wording, and heading presentation (all-caps, bold) can be checked directly from the uploaded image, along with body formatting, continuity, layout, and readability.

Minimum physical type size and maximum characters-per-inch are additional regulatory context from [27 CFR 16.22](https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-16/subpart-C/section-16.22) — the take-home itself does not ask for a physical measurement. An ordinary raster image has no trustworthy physical scale, so these two are shown separately for **manual confirmation** and never turn an otherwise-clean automated result into a review or failure. A label with clean automated checks shows **Match**; the physical note stays visually neutral and secondary, not a warning.

This tool is decision support for a human reviewer, not a final regulatory approval. See [physical-confirmation semantics](docs/physical-warning-semantics.md) for the full decision record and authoritative references.

## Batch verification

Batch is optional. In the batch view:

1. Download the CSV template.
2. Add one row per application.
3. Upload the completed CSV.
4. Upload the matching label images — each row's `image_filename` must match an uploaded image's filename.
5. Select **Verify Batch**.
6. Review results in the table, or export them as CSV.

The CSV columns are `image_filename, brand_name, class_type, abv, net_contents, producer_name, producer_address, imported_product, country_origin` (use `true`/`false` for `imported_product`; `country_origin` only for imports). For example, a row with `image_filename = label-001.png` is matched by uploading a file named `label-001.png`.

Batch and single-label review share the same verification endpoint, so results mean the same thing in both places. Up to 300 rows are supported per batch. Batch state lives in the browser only; the server keeps no batch history, application record, or image.

## Architecture

```text
Label image + application information
  → Validation and preprocessing
  → Local Tesseract OCR (full image, plus a few bounded targeted re-reads when needed)
  → Deterministic extraction, normalization, and comparison
  → Explained reviewer results
```

- **Frontend:** React, TypeScript, Vite.
- **Backend:** FastAPI, Pydantic, local Tesseract OCR — no cloud OCR or LLM service is used or required.
- **Deployment:** one production container serves the compiled frontend and the API from a single origin; no database.

See [architecture.md](docs/architecture.md) for the full request flow, extraction rules, and tradeoffs, and [requirements.md](docs/requirements.md) for the requirement-by-requirement scope and sourcing.

### Repository layout

```text
frontend/           React + TypeScript + Vite; Vitest and ESLint
backend/app/        FastAPI routes, typed models, validation, preprocessing, local OCR
backend/tests/      pytest API and foundation checks
docs/               Requirements matrix, architecture decisions, and dated evaluation reports
examples/           Real and synthetic label fixtures used for regression testing
Dockerfile          Development targets and the single-container production build
docker-compose.yml  Default production service, plus a `dev` profile for hot reload
```

## Development setup

The Docker Quick Start above is the easiest way to run the application. This section is only needed if you're modifying the source.

Prerequisites:

- Python 3.12 (verified with 3.12.14)
- Node.js 24 LTS and pnpm 11.19.0 (`npm install --global pnpm@11.19.0`)
- Tesseract OCR with English language data, available as `tesseract` on `PATH`

A hot-reload Docker Compose path is also available and needs none of the above installed locally:

```sh
docker compose --profile dev up --build backend frontend
```

Open [http://localhost:5173](http://localhost:5173) (frontend, proxies `/api` to the backend) and [http://localhost:8000/api/health](http://localhost:8000/api/health) (backend). Source directories are bind-mounted for reload; stop with Ctrl+C, then `docker compose down`.

### Native setup

From the repository root:

```sh
python -m venv .venv
source .venv/bin/activate        # or .venv\Scripts\Activate.ps1 on Windows
python -m pip install -c backend/constraints.txt -e "./backend[dev]"
cd frontend && pnpm install --frozen-lockfile && cd ..
```

Run the backend:

```sh
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Run the frontend, in a second terminal:

```sh
cd frontend
pnpm dev
```

Open [http://localhost:5173](http://localhost:5173). Optionally copy `.env.example` to `.env` at the repository root; defaults work without it, and neither setting needs a secret. If Tesseract is installed outside `PATH`, set `TTB_TESSERACT_COMMAND`. See [architecture.md](docs/architecture.md) for endpoint details (`/api/labels/ocr`, `/api/labels/verify`) and request limits.

## Testing

Backend:

```sh
python -m pytest -c backend/pyproject.toml backend/tests
python -m ruff check backend
python -m ruff format --check backend
```

Frontend (from `frontend/`):

```sh
pnpm test
pnpm lint
pnpm typecheck
pnpm format:check
pnpm build
```

Production Docker build:

```sh
docker build --target production -t ttb-label-verification .
```

Deeper OCR/regression evaluation commands (`backend/scripts/evaluate_labels.py`, `backend/scripts/evaluate_real_labels.py`) and their evidence are documented in [requirements.md](docs/requirements.md) and the dated audit reports in `docs/`.

## Performance

- **Synthetic regression:** 18 generated cases completed all 306 expected status checks without an OCR failure. Median total time was about 0.5 seconds.
- **Real-label regression:** six TTB sample fixtures had a median total under one second; the slowest completed in about 1.2 seconds with the bounded maximum of four OCR calls.
- **Optional batch check:** a local production container processed one, five, and ten one-call samples in about 0.57, 2.02, and 3.50 seconds respectively at concurrency two.

These are repeatable measurements from one development host, not production accuracy, latency, or capacity guarantees. Generated and real-label results are intentionally reported separately.

## Troubleshooting

- **Docker isn't running:** start Docker Desktop (or the Docker Engine daemon) before `docker compose up`.
- **Port 8000 is already in use:** stop whatever else is using it, or change the published port for the `app` service in `docker-compose.yml` (for example `"127.0.0.1:8080:8000"`), then open that port instead.
- **The first build is slow:** the first `docker compose up --build` downloads base images and dependencies; later builds reuse Docker's layer cache and are much faster.

## Limitations and tradeoffs

- Stylized or decorative text, unusual layouts, glare, low resolution, and photographed containers can require manual review.
- Raster images cannot conclusively establish physical type dimensions.
- Responsible-party information is not inferred without sufficient label evidence.
- English is the only bundled OCR language.
- The prototype is standalone and is not integrated with COLAs Online.
- Batch state is not persisted or resumable after a browser reload.
- Generated and sample fixtures are regression evidence, not production-accuracy estimates.

## Documentation

- [requirements.md](docs/requirements.md) — requirement-by-requirement scope, sourcing, and acceptance criteria.
- [architecture.md](docs/architecture.md) — request flow, extraction/comparison rules, and tradeoffs.
- [physical-warning-semantics.md](docs/physical-warning-semantics.md) — the automated-vs-physical status decision record.
- `docs/*-accuracy*.md` and `docs/ocr-accuracy-pass*.md` — dated OCR and Government-Warning evaluation passes, kept as point-in-time evidence.
- [examples/README.md](examples/README.md) — the real and synthetic label fixtures used for regression testing.
