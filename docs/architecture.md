# Architecture

## Scope and boundaries

The foundation and first product slice of the [specified prototype](https://github.com/treasurytakehome-rgb/instructions) are implemented. The running slice is React image selection → `POST /api/labels/ocr` → validation → preprocessing → local Tesseract → typed raw text response. The application-data form and verification remain unimplemented. Product requirements and sources are tracked in [requirements.md](requirements.md).

React, TypeScript, and Vite own presentation in `frontend/`. FastAPI and Pydantic own the API and typed contracts in `backend/app/`. API routing, response models, service interfaces, and configuration/error handling have separate modules. There is no database or additional service infrastructure.

## Request flow

During development, the browser sends `/api/health` and the multipart OCR request to Vite on port 5173. Vite proxies `/api` to FastAPI on port 8000. An explicit origin allowlist also supports direct local API calls; credentials are unnecessary. Production serves the compiled frontend and API from one FastAPI process and one origin.

`POST /api/labels/ocr` accepts exactly one `file` field. The endpoint reads it in bounded chunks, decodes and validates it with Pillow, preprocesses it in a worker thread, and invokes the configured `OcrService`. The multipart upload is closed in a `finally` block. Starlette may spool multipart content to secure framework-managed temporary storage; the application creates no label file and Tesseract reads PNG bytes from stdin. Image bytes and extracted text are never logged.

## Extraction and comparison

`OcrService` in `services/ocr.py` remains the replaceable extraction boundary: async `extract(image: bytes, *, media_type: str) -> OcrResult`. `TesseractOcrService` implements it with a shell-free subprocess call to local Tesseract. The result carries original-case text, image dimensions, engine name, OCR duration, warnings, and the existing future text-region structure. Tests inject a stub provider, so the unit suite does not depend on a system binary.

Pillow checks declared MIME type against decoded PNG, JPEG, or WebP content, rejects animated or excessive images, applies EXIF orientation, converts to grayscale, normalizes contrast, enlarges small images by at most 2× toward a 1,600-pixel long edge, and applies light sharpening. Hard thresholding is intentionally omitted because it can erase fine text over label artwork. Low-resolution and empty-result warnings are returned to the user.

Keep extraction separate from the future validation/comparison layer. Comparisons should return the supplied value, observed evidence, rule, and explanation. Ordinary brand-name capitalization may be normalized; the warning wording and required capitalization must retain exact comparison semantics. **Plain OCR text cannot establish bold styling. Missing or uncertain image/style evidence must require review, not produce a claimed compliance pass.** Distinguish a confirmed missing field from unreadable evidence. This result structure is an implementation proposal derived from the user's explainability principle.

The specification lists common fields but does not define a complete rule set for every beverage. Before implementing those rules, verify applicable TTB primary sources, document beverage-specific exceptions, and add representative fixtures. Do not turn the common-field list into unconditional requirements or guess regulatory tolerances.

## Errors and configuration

Pydantic settings load `TTB_` environment variables, with an optional repository-root `.env`. Invalid settings fail startup. Central exception handlers return a stable `{"error":{"code":"...","message":"..."}}` envelope for request validation, HTTP, and unexpected errors; unexpected failures use a generic public message. Standard Python logging provides operational diagnostics. Errors must not include request bodies or extracted label text.

The health endpoint returns `{"status":"ok","service":"ttb-label-verification"}` as liveness only. It does not attest to OCR readiness or accuracy. Expected upload failures use specific codes for missing or multiple files, unsupported type, size, decoding, dimensions, unavailable OCR, and OCR processing failure. Unexpected errors retain the generic centralized envelope. The UI associates errors with the upload, moves focus to completed feedback, and never labels OCR output as verified.

## Performance and connectivity

The approximately five-second normal-label target remains a product goal. The response reports total processing and OCR durations; Tesseract is limited to five seconds by default. Uploads are limited to 10 MB, 12,000 pixels per edge, and 40 million pixels. Measure representative labels and hardware before claiming the target is met. A queue or batch engine is unnecessary for this single-label slice.

Mandatory cloud inference would conflict with the stakeholder's restricted outbound connectivity. The protocol keeps the deployment able to use local OCR and image analysis. Building the container and installing dependencies currently require package-registry access; a restricted deployment should receive a prebuilt image with any eventual model assets included. Runtime health and static serving require no outbound connection.

## Deployment and tradeoffs

A multi-stage Dockerfile builds React with Node and installs Python dependencies, Tesseract, and English language data into a slim Python image. Its final stage runs as a non-root user and contains one web service. `TTB_FRONTEND_DIST` enables static serving; absent configuration leaves an API-only development server. The shell uses a single page, so there is no client-side route fallback that could hide unknown API paths or missing assets.

Docker Compose deliberately runs separate frontend and backend development services for hot reload. This does not change the single-container production target. Versions are pinned in package manifests, the pnpm lockfile, Python constraints, and base-image tags. Tags can receive image rebuilds; digest pinning and image publication remain deployment work.

The absence of application persistence simplifies retention and keeps the prototype standalone. Authentication, COLAs Online integration, application comparison, batch processing, and production governance are outside this slice. Tesseract currently uses English and page-segmentation mode 6, returns no word-level confidence or style evidence, and may struggle with curved, reflective, stylized, or poorly photographed labels. A deployed reviewer URL remains a final-product deliverable.
