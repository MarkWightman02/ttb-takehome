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

An optional **Batch verification** view repeats this for many labels at once — see [Batch verification](#batch-verification) below. For a field-by-field walkthrough written for a nontechnical reviewer, see the [user guide](docs/USER_GUIDE.md).

### Try it with a sample label

The repository ships label fixtures you can use immediately. Start the app, open `http://localhost:8000`, enter these values, and upload `examples/T01_harbor_ridge_distilling.png`:

| Field | Value |
| --- | --- |
| Brand name | `HARBOR RIDGE DISTILLING` |
| Class/type designation | `STRAIGHT BOURBON WHISKEY` |
| Alcohol content / ABV (%) | `45` |
| Net contents | `750 ML` |
| Producer / bottler name | `HARBOR RIDGE DISTILLING CO.` |
| Producer / bottler address | `NEWPORT, RI` |
| Imported product | No |

Select **Verify Label**. The summary reads *"All checks completed by this tool matched."* — six fields report **Match**, country of origin reports **Not applicable** (the product is domestic), and the Government Health Warning reports **Match** with a separate neutral note that physical measurements still need manual confirmation.

Other fixtures in [`examples/`](examples/README.md) deliberately produce `review` and `not_found` results — `FBN` and `MHB`, for instance, have no responsible-party cue on the label, so producer name and address are correctly reported as not found rather than guessed.

## Result meanings

- **Match:** the label supports the entered application value or checked requirement.
- **Review:** the evidence is plausible, but the tool cannot reach a confident conclusion. This is intentional conservative behavior, not necessarily an error.
- **Mismatch:** the label and application appear to differ.
- **Not found:** the tool could not locate reliable supporting evidence on the label.
- **Not applicable:** the check does not apply to this application (for example, country of origin on a domestic product).

## What the tool verifies

Against the application information you enter:

- Brand name
- Class/type designation
- Alcohol content (ABV)
- Net contents
- Producer/bottler name and address
- Country of origin, when the application marks the product as imported
- The Government Health Warning (see below)

Comparison is deterministic and conservative: values are normalized before comparison (so capitalization and punctuation differences do not cause failures), numbers are compared exactly, and anything the tool cannot confirm becomes `review` rather than a confident match. The values you enter never influence what is read from the label. See [verification logic](docs/VERIFICATION_LOGIC.md).

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

`examples/batch_manifest.csv` is a ready-made manifest for the twenty synthetic fixtures. Full column reference, matching rules, and export format: [batch verification guide](docs/BATCH_VERIFICATION.md).

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
docs/               User, batch, troubleshooting, and development guides; design and evaluation records
examples/           Real and synthetic label fixtures used for regression testing
Dockerfile          Development targets and the single-container production build
docker-compose.yml  Default production service, plus a `dev` profile for hot reload
```

## Development

The Docker Quick Start above is the easiest way to run the application; this is only needed if you're modifying the source. A hot-reload Compose profile needs nothing installed locally:

```sh
docker compose --profile dev up --build backend frontend
```

Frontend on [http://localhost:5173](http://localhost:5173), backend on [http://localhost:8000](http://localhost:8000). Name both services — the bare `--profile dev up` form would also start the production service and collide on port 8000.

Native setup (Python 3.12, Node 24 + pnpm 11.19.0, Tesseract on `PATH`), the dev-profile details, and the production image structure are in the [development guide](docs/DEVELOPMENT.md).

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

Deeper OCR/regression evaluation scripts are described in the [development guide](docs/DEVELOPMENT.md#evaluation-scripts); their recorded evidence is in the dated audit reports in `docs/`.

## Performance

- **Synthetic regression:** 18 generated cases completed all 306 expected status checks without an OCR failure. Median total time was about 0.5 seconds.
- **Real-label regression:** six TTB sample fixtures had a median total under one second; the slowest completed in about 1.2 seconds with the bounded maximum of four OCR calls.
- **Optional batch check:** a local production container processed one, five, and ten one-call samples in about 0.57, 2.02, and 3.50 seconds respectively at concurrency two.

These are repeatable measurements from one development host, not production accuracy, latency, or capacity guarantees. Generated and real-label results are intentionally reported separately.

## Troubleshooting

The first two commands to run for almost any problem:

```sh
docker compose ps           # is the container up, and is it healthy?
docker compose logs app     # what did it say on the way up?
```

Three common cases:

- **Docker isn't running:** start Docker Desktop (or the Docker Engine daemon), then retry.
- **Port 8000 is already in use:** something else on your machine has claimed it. The [troubleshooting guide](docs/TROUBLESHOOTING.md#port-8000-is-already-in-use) shows how to identify it and how to run this app on a different port instead.
- **The first build is slow:** base images and dependencies are downloading. Later builds reuse Docker's layer cache and are much faster.

Everything else — image rejections, `review` and `not found` results, batch CSV errors, dev-profile port conflicts — is covered in the **[troubleshooting guide](docs/TROUBLESHOOTING.md)**.

## Limitations and tradeoffs

- Stylized or decorative text, unusual layouts, glare, low resolution, and photographed containers can require manual review.
- Raster images cannot conclusively establish physical type dimensions.
- Responsible-party information is not inferred without sufficient label evidence.
- English is the only bundled OCR language.
- The prototype is standalone and is not integrated with COLAs Online.
- Batch state is not persisted or resumable after a browser reload.
- Generated and sample fixtures are regression evidence, not production-accuracy estimates.

## Documentation

**Using the tool**

- [User guide](docs/USER_GUIDE.md) — field-by-field walkthrough and how to read results, in plain language.
- [Batch verification](docs/BATCH_VERIFICATION.md) — CSV format, filename matching, limits, and export columns.
- [Troubleshooting](docs/TROUBLESHOOTING.md) — symptom-by-symptom fixes for startup, images, results, and batch.

**Understanding the project**

- [Verification logic](docs/VERIFICATION_LOGIC.md) — how a status is decided, and why the tool is conservative.
- [Architecture](docs/architecture.md) — request flow, extraction and comparison design, tradeoffs.
- [Requirements](docs/requirements.md) — requirement-by-requirement scope, sourcing, and acceptance criteria.

**Working on it**

- [Development](docs/DEVELOPMENT.md) — native and Docker development setup, tests, evaluation scripts.
- [Example fixtures](examples/README.md) — the label fixtures and what they are (and are not) evidence of.

**Decision records and evidence** — point-in-time reports, kept as-is for traceability:

- [Physical warning semantics](docs/physical-warning-semantics.md) — why physical measurements are manual-only.
- [Government Warning accuracy](docs/government-warning-accuracy.md), [OCR accuracy pass 1](docs/ocr-accuracy-pass1.md), [pass 2](docs/ocr-accuracy-pass2.md) — dated evaluation passes.
