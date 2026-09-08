# Architecture

## Scope and boundaries

This is the first foundation increment of the [specified prototype](https://github.com/treasurytakehome-rgb/instructions). The running slice is React → `/api/health` → FastAPI → a development-only connection indicator. The application-data form, upload, extraction, and verification remain unimplemented. Product requirements and their sources are tracked in [requirements.md](requirements.md).

React, TypeScript, and Vite own presentation in `frontend/`. FastAPI and Pydantic own the API and typed contracts in `backend/app/`. API routing, response models, service interfaces, and configuration/error handling have separate modules. There is no database or additional service infrastructure.

## Request flow

During development, the browser requests `/api/health` from Vite on port 5173. Vite proxies `/api` to FastAPI on port 8000. An explicit origin allowlist also supports direct local API calls; credentials are unnecessary. Production serves the compiled frontend and API from one FastAPI process and one origin.

The next increment will accept one label plus application data, validate the request, extract evidence through an injected OCR provider, run deterministic comparisons, and return field-level findings. That is a proposed flow, not an implemented endpoint. Uploaded bytes should live only for the request; any provider requiring temporary files must remove them on success, cancellation, and failure. Never log document contents or application field values.

## Extraction and comparison

`OcrService` in `services/ocr.py` defines the replaceable extraction boundary: async `extract(image: bytes, *, media_type: str) -> OcrResult`. The result carries original-case text, image dimensions, engine name, and text regions with optional confidence, bounding boxes, and boldness evidence. `None` means unknown, including for boldness. No provider, model download, API key, or inference call exists yet. A later local implementation should be initialized once and injected rather than loaded for each request.

Keep extraction separate from the future validation/comparison layer. Comparisons should return the supplied value, observed evidence, rule, and explanation. Ordinary brand-name capitalization may be normalized; the warning wording and required capitalization must retain exact comparison semantics. **Plain OCR text cannot establish bold styling. Missing or uncertain image/style evidence must require review, not produce a claimed compliance pass.** Distinguish a confirmed missing field from unreadable evidence. This result structure is an implementation proposal derived from the user's explainability principle.

The specification lists common fields but does not define a complete rule set for every beverage. Before implementing those rules, verify applicable TTB primary sources, document beverage-specific exceptions, and add representative fixtures. Do not turn the common-field list into unconditional requirements or guess regulatory tolerances.

## Errors and configuration

Pydantic settings load `TTB_` environment variables, with an optional repository-root `.env`. Invalid settings fail startup. Central exception handlers return a stable `{"error":{"code":"...","message":"..."}}` envelope for request validation, HTTP, and unexpected errors; unexpected failures use a generic public message. Standard Python logging provides operational diagnostics. Errors must not include request bodies or extracted label text.

The health endpoint returns `{"status":"ok","service":"ttb-label-verification"}` as liveness only. It does not attest to OCR readiness or compliance accuracy. The frontend connection check is bounded and handles failure visibly only in development. No verification action is offered until the workflow exists. Future upload errors, extraction timeouts, and unreadable labels need actionable messages; unsupported formats and limits remain to be selected with the OCR adapter.

## Performance and connectivity

The approximately five-second normal-label target is a product goal, not a measured result of this scaffold. Measure the complete user-observed request on agreed representative labels and hardware when OCR exists. Bound image size and processing time, reuse the local model, and profile extraction before adding concurrency. CPU work will need an appropriate worker/thread boundary so it does not block health requests. A queue or batch engine is unnecessary for this increment.

Mandatory cloud inference would conflict with the stakeholder's restricted outbound connectivity. The protocol keeps the deployment able to use local OCR and image analysis. Building the container and installing dependencies currently require package-registry access; a restricted deployment should receive a prebuilt image with any eventual model assets included. Runtime health and static serving require no outbound connection.

## Deployment and tradeoffs

A multi-stage Dockerfile builds React with Node and installs Python dependencies into a slim Python image. Its final stage runs as a non-root user and contains one web service. `TTB_FRONTEND_DIST` enables static serving; absent configuration leaves an API-only development server. The shell uses a single page, so there is no client-side route fallback that could hide unknown API paths or missing assets.

Docker Compose deliberately runs separate frontend and backend development services for hot reload. This does not change the single-container production target. Versions are pinned in package manifests, the pnpm lockfile, Python constraints, and base-image tags. Tags can receive image rebuilds; digest pinning and image publication remain deployment work.

The absence of persistence simplifies retention and keeps the prototype standalone. Authentication, COLAs Online integration, batch processing, and production governance are outside this increment. Distorted-image handling is a later enhancement. A deployed reviewer URL remains a final-product deliverable; this task prepares packaging without claiming the full application is ready.
