# Troubleshooting

Practical fixes, organized by what you actually see. Start with the two commands that answer most questions:

```sh
docker compose ps           # is the container running, and is it healthy?
docker compose logs app     # what did it say on the way up?
```

For how to use the tool, see [USER_GUIDE.md](USER_GUIDE.md). For development setup, see [DEVELOPMENT.md](DEVELOPMENT.md).

---

## Startup and Docker

### `docker compose up --build -d` fails immediately

**Symptom.** The command exits with an error instead of starting a container.

**Likely causes.** Docker is not running; no network access for the first build; not enough disk space.

**How to check.**

```sh
docker info          # fails outright if the Docker daemon is not running
docker version
df -h                # free disk space
```

**Resolution.**

- **Docker not running:** start Docker Desktop (Windows/macOS) or the Docker Engine service (Linux) and retry.
- **Network:** the first build downloads base images and dependencies. Reconnect and retry; the build resumes from cached layers.
- **Disk space:** free space and retry. Docker needs room for the Node and Python base images plus the built image (roughly 1–2 GB total).

### Port 8000 is already in use

**Symptom.** The build succeeds, then startup fails with a message like:

```text
Bind for 0.0.0.0:8000 failed: port is already allocated
```

**Likely cause.** Another program on your machine is already listening on port 8000. This is common — several developer tools and container dashboards default to it.

**How to check.**

Linux/macOS:

```sh
lsof -i :8000
```

or:

```sh
ss -ltnp | grep ':8000'
```

Windows PowerShell:

```powershell
Get-NetTCPConnection -LocalPort 8000
```

**Resolution — pick one.**

*Option A — stop the other service.* Identify the program from the output above and stop it through its normal controls. Do not force-kill an unfamiliar process just to free the port; it may belong to something you rely on.

*Option B — run this app on a different port instead.* Create a file named `docker-compose.override.yml` next to `docker-compose.yml`. Docker Compose picks it up automatically, and it leaves the tracked configuration untouched:

```yaml
services:
  app:
    ports: !override
      - "127.0.0.1:8080:8000"
```

Then:

```sh
docker compose up --build -d
```

and open `http://localhost:8080` instead. The `!override` marker is required — without it Compose *adds* the new mapping to the existing one and still tries to claim port 8000. Delete the override file when you no longer need it.

### The first build seems to hang

**Symptom.** `docker compose up --build` sits for a long time on a dependency or image step.

**Likely cause.** This is normal on a first build. Base images, Python packages, and frontend packages are all being downloaded.

**Resolution.** Let it finish. Later builds reuse Docker's layer cache and are much faster. If it genuinely stalls with no progress for several minutes, interrupt it, check connectivity, and rerun — completed layers are cached.

### Container starts but the app will not load

**Symptom.** The container is up, but the browser shows nothing or an error.

**How to check.**

```sh
docker compose ps
docker compose logs app
curl http://localhost:8000/api/health
```

**What you are looking for.** In `docker compose ps`, the `STATUS` column should read `Up ... (healthy)`. Immediately after startup it briefly reads `(health: starting)` — wait about ten seconds and check again. `(unhealthy)` or a restart loop means the application failed to start; the reason will be in `docker compose logs app`.

**Resolution.** Address whatever the logs report, then do a clean restart (below).

### Health check fails

**Symptom.** `curl http://localhost:8000/api/health` returns nothing, refuses the connection, or the container reports `(unhealthy)`.

**What a healthy response looks like.**

```json
{"status":"ok","service":"ttb-label-verification"}
```

This reports only that the API process is running and serving. It does not attest that label reading is working or that any result is accurate.

**How to check.** Confirm the container is up (`docker compose ps`), confirm the published port matches the URL you are using, then read `docker compose logs app`.

### Browser cannot reach localhost

**Symptom.** The container is healthy, but the browser cannot connect.

**How to check, in order.**

1. `docker compose ps` — confirm `STATUS` is `Up (healthy)` and note the `PORTS` column.
2. Confirm the port in the URL matches the left-hand port in that column.
3. Confirm the URL spelling: `http://localhost:8000` — `http`, not `https`.
4. If you are on a corporate VPN or have a strict local firewall, confirm it is not blocking loopback connections.

Note that the port is published on `127.0.0.1` only, so the app is reachable from the machine running it, not from other machines on the network. That is intentional.

### Clean restart

Safe, and the right first move after most configuration confusion:

```sh
docker compose down
docker compose up --build -d
```

### Clean rebuild

Only if you suspect a genuinely stale build layer:

```sh
docker compose down
docker compose build --no-cache
docker compose up -d
```

A `--no-cache` build re-downloads and reruns every step, so it is considerably slower. It is not routine maintenance and is rarely necessary. This project needs no volume or image pruning to work correctly, so there is no reason to run broad Docker cleanup commands as a fix.

---

## Using the tool

### "This file type is not supported"

Supported formats are **PNG, JPEG, and WebP**, up to **10 MB**, at most 12,000 pixels on a side and 40 million pixels total.

The file's actual content is checked, not its extension. A PNG that has simply been renamed to `.jpg` is detected and reported, which is why a file that opens fine elsewhere can still be rejected. Re-export it properly in a supported format.

### "The label image could not be read"

**Likely causes.** The file is corrupt or truncated; it is an unusual encoding or color profile; it is technically valid but visually unusable.

**Resolution.** Open the file locally to confirm it displays, then re-export it as a standard PNG or JPEG and try again.

### A result says Not found

This is a normal result, not a crash. It means the tool could not locate reliable evidence for that item on the image.

**Common causes.**

- The information is on a panel that was not included in the uploaded image.
- The text is too stylized, too small, or too low-contrast to read reliably.
- For producer/bottler name and address: the label shows a company name with no responsible-party cue such as *Bottled by*, *Produced by*, or *Imported by*. The tool deliberately reports *Not found* rather than assuming which company plays that role.

**Resolution.** Upload a complete, higher-quality image, or confirm the item by eye.

### A result says Review

*Review* is not *Mismatch*. *Mismatch* means the tool is confident the two values differ. *Review* means the tool found something plausible but is not confident enough to call it either way, so it is handing the decision to you.

Common triggers: low image quality, two similar candidates found on the label (for example a brand name that appears twice in different styles), or partial address evidence. See [USER_GUIDE.md](USER_GUIDE.md#what-to-do-when-a-result-says-review) for how to resolve one.

### The Government Warning says Review

Common reasons:

- **Readability** — contrast between the warning text and its background is not clearly sufficient in the image.
- **Heading emphasis** — the image evidence does not clearly show the heading as heavier than the body text.
- **Warning wording** — the recognized text differs from the prescribed statement in a way consistent with imperfect reading rather than an actual wording change.
- **Warning layout or continuity** — the geometry of the statement in the image is ambiguous.

Each individual check shows its own explanation. Read the specific card rather than the section heading.

### The Government Warning shows "Manual confirmation" on type size and characters per inch

This is expected on every label and is not an error. Those two requirements describe the **physical printed label**, and an image has no dependable real-world scale. They are shown for reference with the applicable limit and must be confirmed against the physical item. They never cause an otherwise clean result to be reported as a problem. See [USER_GUIDE.md](USER_GUIDE.md#why-physical-measurements-say-manual-confirmation).

---

## Batch verification

Full instructions are in [BATCH_VERIFICATION.md](BATCH_VERIFICATION.md).

### "Missing required columns"

The CSV must contain all nine columns, named exactly:

```text
image_filename,brand_name,class_type,abv,net_contents,producer_name,producer_address,imported_product,country_origin
```

Download the template from the batch view rather than building the header by hand. Extra or renamed columns are also reported.

### "No selected image matches ..."

The `image_filename` value in that row does not match any image you selected.

Matching ignores capitalization, surrounding spaces, and any folder path in the cell (`labels/front.png` matches a selected file named `front.png`). It does **not** ignore anything else — `front.jpg` will not match `front.png`, and `front (1).png` will not match `front.png`.

### "More than one row uses the image filename ..."

Two or more CSV rows point at the same image after that normalization. Give each application its own distinctly named image; the tool will not guess which row a duplicate belongs to.

### "Images not represented in the CSV"

You selected image files that no CSV row refers to. Either add rows for them or deselect them. This is a notice, not a blocker.

### "The imported_product column must be true or false"

Only `true` or `false` are accepted (capitalization does not matter, surrounding spaces are trimmed). Values like `yes`, `Y`, or `1` are rejected.

### "The country_origin column is required when imported_product is true"

Fill in `country_origin` for that row, or set `imported_product` to `false` if the product is domestic.

### "The net_contents column must use mL, L, US pint, or US fluid ounce units"

Each row needs a single volume expression, such as `750 mL`, `1 L`, `1 pint`, or `12 fl oz`.

A **compound** value that states two units at once — for example `1 PINT (473 ML)` — is not accepted, even though such wording is common on real labels. Enter a single unit instead, such as `473 mL`. Single-label review applies the same rule and reports `Net contents must use mL, L, US pint, or US fluid ounce units` for the same input.

If the label prints both forms, enter either one. The tool reads the label independently of what you typed, so it will still see both printed declarations — and because they normalize to two slightly different values, it reports net contents as **Review** rather than choosing one for you.

### "The CSV contains N rows; the maximum batch size is 300"

Split the work into batches of 300 rows or fewer.

### One batch item fails but the others succeed

That is the intended behavior. Each label is verified independently, so one bad row or one failed request does not stop the rest. Rows that failed to process show **Processing failed** and can be retried with **Retry failed items**; rows that failed validation show **Invalid** and need the CSV corrected.

### The exported CSV looks odd in Excel

The export is a standard CSV. Leading `=`, `+`, `-`, and `@` characters in text values are prefixed with an apostrophe so spreadsheet software does not interpret a company name as a formula — that apostrophe is a deliberate safety measure, not corruption. If columns do not split, use your spreadsheet's *Import from text/CSV* option and select comma as the delimiter rather than double-clicking the file.

---

## Development

### `docker compose --profile dev up` causes a port conflict

**Symptom.** Starting the development profile fails to bind port 8000.

**Cause.** The production `app` service has no profile, so it is always included. Running `docker compose --profile dev up` with no service names starts `app` **and** the dev `backend`, and both publish port 8000.

**Resolution.** Name the two development services explicitly:

```sh
docker compose --profile dev up --build backend frontend
```

That starts only those two — the frontend on `http://localhost:5173` and the backend on `http://localhost:8000`. Do not use the bare `docker compose --profile dev up` form.

### Native setup: `tesseract` not found

Running the backend outside Docker requires Tesseract with English language data on your `PATH`:

```sh
tesseract --version
```

If it is installed somewhere else, set `TTB_TESSERACT_COMMAND` to its full path in a repository-root `.env` file. None of this applies when running via Docker — the image already contains Tesseract and its English data.

### Useful log and inspection commands

```sh
docker compose ps                     # status and published ports
docker compose logs app               # application logs
docker compose logs -f app            # follow logs live (Ctrl+C to stop)
docker inspect ttb-takehome-app-1 --format '{{json .State.Health}}'   # health probe history
```

Image bytes and extracted label text are never written to the logs.

---

## Still stuck

- Confirm the behavior against the hosted demo at [https://ttb.markwightman.org](https://ttb.markwightman.org). If the demo behaves differently from your local build, the problem is local.
- Re-read [`docker compose logs app`](#container-starts-but-the-app-will-not-load) — application-level failures almost always report a specific cause there.
- For anything about *why* a result was produced, see [VERIFICATION_LOGIC.md](VERIFICATION_LOGIC.md).
