# Requirements

The [instruction repository][spec], including its stakeholder interviews, is the product specification. The foundation and a single-label raw OCR slice are implemented. Application-data comparison and compliance decisions remain future work. Priorities reflect the requested sequencing, not additional regulatory rules.

`User` means the accompanying first-task request. Linked stakeholder names refer to the authoritative interviews. The implementation and acceptance columns are engineering proposals for meeting those requirements; they are not additional stakeholder mandates.

## Core MVP

### Implemented foundation and raw OCR slice

| Requirement | Source / stakeholder | Priority | Planned implementation | Acceptance criterion |
| --- | --- | --- | --- | --- |
| Required stack and monorepo | User | Now | React, TypeScript, Vite frontend; Python, FastAPI backend; separate `frontend/`, `backend/`, and `docs/` | Both applications start locally; pytest and Vitest are configured. |
| Backend foundation | User | Now | Typed `/api/health`, structured configuration, explicit development CORS, centralized errors, logging, organized modules | `GET /api/health` returns HTTP 200 and `{"status":"ok","service":"ttb-label-verification"}`; backend tests pass. |
| Replaceable local OCR | User; [Marcus][marcus] | Implemented | Run local Tesseract behind the typed OCR protocol; no hosted OCR or LLM API | The provider receives an in-memory normalized image and returns raw text, engine, duration, and warnings. |
| Clear, accessible application shell | User | Implemented | “TTB Label Verification” title, application placeholder, functional upload, raw result area, restrained professional styling | Semantic landmarks, labeled file control, keyboard operation, loading announcement, focused errors, readable contrast, and clearly identified unfinished comparison. |
| Frontend/backend connection | User | Now | Frontend requests `/api/health`; show backend availability in development | Development reports success and handles an unavailable backend; production omits the diagnostic indicator. |
| Single-label image upload | User | Implemented | `POST /api/labels/ocr` accepts exactly one multipart image | PNG, JPEG, and WebP images produce a typed raw OCR response; missing or multiple files are rejected. |
| Defensive image validation | User | Implemented | Bound upload bytes and decoded dimensions; verify declared MIME against Pillow-detected format | Oversized, unsupported, mismatched, corrupt, animated, empty, and excessive-dimension images return typed errors without entering OCR. |
| Conservative preprocessing | User | Implemented | EXIF orientation, grayscale, automatic contrast, limited small-image upscale, light sharpening | Preprocessing is independently tested and supplies normalized PNG bytes without hard thresholding. |
| Request-scoped privacy | User; [Marcus][marcus] | Implemented | Close multipart uploads reliably and stream normalized bytes to Tesseract stdin | The application creates no persistent label file and does not log image contents or extracted text. |
| Configuration and tooling | User | Now | `.gitignore`, `.env.example`, pinned dependencies, appropriate lint/format configuration | Dependencies install; frontend tests, lint, type checking and build pass. |
| Container deployment foundation | User | Now | Dockerfile builds the frontend and packages it with FastAPI; Compose supports development | Production frontend and API share one container; Docker build is checked when available. |
| Reviewer documentation | User; [deliverables][deliverables] | Now | Requirements, architecture and README covering setup, tests, Docker, assumptions and status | Instructions match implemented behavior; verification results and any unavailable checks are reported. |

### Product behavior: subsequent implementation

| Requirement | Source / stakeholder | Priority | Planned implementation | Acceptance criterion |
| --- | --- | --- | --- | --- |
| Compare application data with one label | [Sarah][sarah]; User | Core | Future upload, extraction, comparison | Results identify matches and discrepancies. |
| Beverage-dependent fields: brand, class/type, alcohol, net contents, producer/bottler name/address; imported origin | [Label requirements][fields] | Core | Future conditional validation | Required fields follow documented beverage/import applicability; alcohol exceptions remain explicit. |
| Exact health warning; uppercase, bold `GOVERNMENT WARNING:` | [Jenny][jenny]; [Label requirements][fields] | Core | Future text and visual checks | Confirmed omissions or wording/style violations are flagged; uncertain evidence requires review. |
| Case-only brand differences are acceptable | [Dave][dave] | Core | Future field-specific normalization | Capitalization alone causes no mismatch. |
| Approximately five-second normal verification | [Sarah][sarah]; User | Core | Future latency measurement | Record end-to-end timings, fixture set and hardware; representative normal labels meet the target. |
| Obvious workflow across technical abilities | [Sarah][sarah] | Core | Future simple form and results | Primary actions are easy to locate. |
| Explainable, deterministic compliance decisions | User | Core | Separate comparison rules from extraction; show observed/expected values and reasons | Reviewers can understand each decision; an LLM does not decide exact requirements. |
| Standalone, minimal document retention | User; [Marcus][marcus] | Core | Request-scoped processing; no database or COLAs integration | Uploads are not unnecessarily persisted; core operation needs no COLAs connection. |

No complete regulatory rule set, canonical warning text, numeric tolerances, font-size threshold, image limits or confidence cutoff is specified here. Confirm and cite applicable requirements before implementing them. **Plain OCR text cannot establish bold styling. Unknown style or extraction evidence requires review, not a claimed compliance pass.** These are implementation gaps, not claims that verification already exists.

## Important enhancement

| Requirement | Source / stakeholder | Priority | Planned implementation | Acceptance criterion |
| --- | --- | --- | --- | --- |
| Batch uploads | [Sarah][sarah]; User | Deferred | After reliable single-label workflow | Multiple labels can be submitted together; determine capacity after the single-label baseline. |

The interview's 200–300-application deliveries describe workload context, not a prescribed batch limit.

## Future / out of scope

| Requirement | Source / stakeholder | Priority | Planned implementation | Acceptance criterion |
| --- | --- | --- | --- | --- |
| Difficult photographs | [Jenny][jenny] | Optional, deferred | Explore angle, lighting and glare handling | Evaluate representative difficult images. |
| Accessible deployed prototype | [Deliverables][deliverables] | Later delivery | Deploy completed core | Reviewers receive a working URL. |
| Authentication, database, COLAs integration, Kubernetes, microservices and LLM API | User | Excluded from this task | Do not implement | No such components or dependencies are introduced. |
| Application-data entry, field comparison, and verification | User | Beyond this slice | Implement incrementally after raw OCR | The application placeholder is replaced only when comparisons work and have been verified. |

[spec]: https://github.com/treasurytakehome-rgb/instructions
[sarah]: https://github.com/treasurytakehome-rgb/instructions#interview-notes-sarah-chen-deputy-director-of-label-compliance
[marcus]: https://github.com/treasurytakehome-rgb/instructions#interview-notes-marcus-williams-it-systems-administrator
[dave]: https://github.com/treasurytakehome-rgb/instructions#interview-notes-dave-morrison-senior-compliance-agent-28-years
[jenny]: https://github.com/treasurytakehome-rgb/instructions#interview-notes-jenny-park-junior-compliance-agent-8-months
[fields]: https://github.com/treasurytakehome-rgb/instructions#about-ttb-label-requirements
[deliverables]: https://github.com/treasurytakehome-rgb/instructions#deliverables
