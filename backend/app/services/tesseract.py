import asyncio
import contextlib
import logging
from io import BytesIO
from time import perf_counter

from PIL import Image

from app.services.ocr import OcrProcessingError, OcrResult, OcrUnavailableError

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
                "6",
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

        text = stdout.decode("utf-8", errors="replace").strip()
        duration_ms = (perf_counter() - started) * 1_000
        result_warnings: tuple[str, ...] = ()
        if not text:
            result_warnings = (
                "No text was detected. Try a clearer image with the label filling the frame.",
            )

        return OcrResult(
            text=text,
            regions=(),
            image_width=width,
            image_height=height,
            engine_name="tesseract-cli",
            duration_ms=duration_ms,
            warnings=result_warnings,
        )
