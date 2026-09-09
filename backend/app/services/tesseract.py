import asyncio
import contextlib
import csv
import logging
from collections import OrderedDict
from io import BytesIO, StringIO
from time import perf_counter

from PIL import Image

from app.services.ocr import (
    BoundingBox,
    OcrProcessingError,
    OcrResult,
    OcrUnavailableError,
    TextRegion,
)

logger = logging.getLogger(__name__)


class TesseractOcrService:
    """Run local Tesseract with image bytes on stdin and no retained label files."""

    def __init__(self, *, command: str, language: str, timeout_seconds: float) -> None:
        self.command = command
        self.language = language
        self.timeout_seconds = timeout_seconds

    async def extract(self, image: bytes, *, media_type: str) -> OcrResult:
        del media_type  # The pipeline always supplies a decoded, normalized PNG.
        with Image.open(BytesIO(image)) as prepared:
            width, height = prepared.size

        started = perf_counter()
        try:
            process = await asyncio.create_subprocess_exec(
                self.command,
                "stdin",
                "stdout",
                "-l",
                self.language,
                "--psm",
                "11",
                "tsv",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except (FileNotFoundError, OSError) as exc:
            raise OcrUnavailableError("Tesseract could not be started.") from exc

        try:
            stdout, _stderr = await asyncio.wait_for(
                process.communicate(image), timeout=self.timeout_seconds
            )
        except TimeoutError as exc:
            process.kill()
            with contextlib.suppress(Exception):
                await process.wait()
            raise OcrProcessingError("Tesseract timed out.") from exc

        if process.returncode != 0:
            logger.error("Tesseract failed returncode=%s", process.returncode)
            raise OcrProcessingError("Tesseract could not process the image.")

        try:
            text, regions = _parse_tsv(stdout.decode("utf-8", errors="replace"))
        except (KeyError, TypeError, ValueError) as exc:
            raise OcrProcessingError("Tesseract returned invalid structured output.") from exc
        duration_ms = (perf_counter() - started) * 1_000
        result_warnings: tuple[str, ...] = ()
        if not text:
            result_warnings = (
                "No text was detected. Try a clearer image with the label filling the frame.",
            )

        return OcrResult(
            text=text,
            regions=regions,
            image_width=width,
            image_height=height,
            engine_name="tesseract-cli",
            duration_ms=duration_ms,
            warnings=result_warnings,
        )


def _parse_tsv(output: str) -> tuple[str, tuple[TextRegion, ...]]:
    reader = csv.DictReader(StringIO(output), delimiter="\t")
    if reader.fieldnames is None or "text" not in reader.fieldnames:
        raise ValueError("Missing Tesseract TSV header")

    regions: list[TextRegion] = []
    lines: OrderedDict[tuple[int, int, int, int], list[str]] = OrderedDict()
    for row in reader:
        if row.get("level") != "5":
            continue
        word = (row.get("text") or "").strip()
        if not word:
            continue
        page_id = int(row["page_num"])
        block_id = int(row["block_num"])
        paragraph_id = int(row["par_num"])
        line_id = int(row["line_num"])
        confidence_value = float(row["conf"])
        confidence = confidence_value / 100 if confidence_value >= 0 else None
        region = TextRegion(
            text=word,
            bounding_box=BoundingBox(
                left=int(row["left"]),
                top=int(row["top"]),
                width=int(row["width"]),
                height=int(row["height"]),
            ),
            confidence=confidence,
            page_id=page_id,
            block_id=block_id,
            paragraph_id=paragraph_id,
            line_id=line_id,
            word_id=int(row["word_num"]),
        )
        regions.append(region)
        lines.setdefault((page_id, block_id, paragraph_id, line_id), []).append(word)

    text = "\n".join(" ".join(words) for words in lines.values()).strip()
    return text, tuple(regions)
