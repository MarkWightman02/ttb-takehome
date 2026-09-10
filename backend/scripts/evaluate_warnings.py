#!/usr/bin/env python3
"""Warning-only real-engine diagnostics; not a field-accuracy benchmark."""

import argparse
import asyncio
import json
import re
import sys
from collections import Counter, defaultdict
from io import BytesIO
from pathlib import Path
from time import perf_counter
from urllib.parse import urlparse

from PIL import Image

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import Settings  # noqa: E402
from app.services.government_warning import analyze_government_warning  # noqa: E402
from app.services.image_preprocessing import FORMAT_MEDIA_TYPES, prepare_image  # noqa: E402
from app.services.normalization import normalize_volume  # noqa: E402
from app.services.tesseract import TesseractOcrService  # noqa: E402


def warning_volume(value: str) -> tuple[float, str | None]:
    """Use an explicit parenthesized metric value only for the physical tier."""
    try:
        return normalize_volume(value), None
    except ValueError:
        metric = re.search(r"\((\d+(?:\.\d+)?\s*m?l)\)", value, re.IGNORECASE)
        if metric is None:
            raise
        return normalize_volume(metric[1]), (
            "Warning-only evaluation uses the explicit metric component for the physical tier; "
            "the compound application input is not supported by the existing form normalizer."
        )


async def evaluate(args: argparse.Namespace) -> dict:
    inputs = []
    for image_path in sorted(args.examples_dir.iterdir()):
        if image_path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
            continue
        metadata_path = image_path.with_suffix(".json")
        group = "original"
        if not metadata_path.is_file():
            # Companion IDs in the supplied synthetic manifest are filename prefixes.
            metadata_path = image_path.with_name(image_path.stem.split("_")[0] + ".json")
            group = "new_synthetic"
        metadata = json.loads(metadata_path.read_text())
        volume, note = warning_volume(metadata["net_contents"])
        inputs.append((group, image_path.name, image_path.read_bytes(), volume, note))

    if args.heldout_images_dir:
        for case in json.loads(args.heldout_evidence.read_text())["heldout"]:
            source_path = args.heldout_images_dir / Path(urlparse(case["source"]).path).name
            with Image.open(source_path) as source:
                output = BytesIO()
                source.crop(tuple(case["crop"])).save(output, format="PNG")
            # No trusted container size is available on some front/back-only crops.
            # A diagnostic tier placeholder never makes either physical check match.
            inputs.append(
                (
                    "heldout",
                    case["name"],
                    output.getvalue(),
                    750,
                    "Diagnostic physical tier only; no trusted scale.",
                )
            )

    service = TesseractOcrService(command="tesseract", language="eng", timeout_seconds=5)
    reports = []
    counts = defaultdict(lambda: defaultdict(Counter))
    for group, name, data, volume, note in inputs:
        started = perf_counter()
        with Image.open(BytesIO(data)) as source:
            media_type = FORMAT_MEDIA_TYPES[source.format]
        prepared = prepare_image(data, content_type=media_type, settings=Settings())
        ocr = await service.extract(prepared.data, media_type="image/png")
        warning = analyze_government_warning(
            ocr,
            preprocessed_image=prepared.visual_evidence_data,
            container_volume_ml=volume,
        )
        reports.append(
            {
                "group": group,
                "name": name,
                "note": note,
                "ocr_text": ocr.text,
                "ocr_duration_ms": ocr.duration_ms,
                "ocr_invocations": 1,
                "total_ms": (perf_counter() - started) * 1000,
                "warning": warning.model_dump(),
            }
        )
        for name, check in warning.checks.model_dump().items():
            counts[group][name][check["status"]] += 1
        counts[group]["overall"][warning.overall_status] += 1
    return {"counts": counts, "cases": reports}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--examples-dir", type=Path, default=BACKEND_ROOT.parent / "examples")
    parser.add_argument("--heldout-images-dir", type=Path)
    parser.add_argument(
        "--heldout-evidence",
        type=Path,
        default=BACKEND_ROOT.parent / "docs/ocr-accuracy-pass2-evidence.json",
    )
    print(json.dumps(asyncio.run(evaluate(parser.parse_args())), indent=2))


if __name__ == "__main__":
    main()
