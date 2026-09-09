import warnings
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageFilter, ImageOps, UnidentifiedImageError

from app.core.config import Settings
from app.core.errors import ApiError

ALLOWED_MEDIA_TYPES = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}
FORMAT_MEDIA_TYPES = {
    image_format: media_type for media_type, image_format in ALLOWED_MEDIA_TYPES.items()
}
TARGET_LONG_EDGE = 2_400
MAX_UPSCALE = 4.0


@dataclass(frozen=True, slots=True)
class PreparedImage:
    data: bytes
    visual_evidence_data: bytes
    original_width: int
    original_height: int
    original_format: str
    warnings: tuple[str, ...]


def normalize_media_type(content_type: str | None) -> str:
    media_type = (content_type or "").partition(";")[0].strip().lower()
    if media_type not in ALLOWED_MEDIA_TYPES:
        raise ApiError(415, "unsupported_file_type", "Choose a PNG, JPEG, or WebP image.")
    return media_type


def prepare_image(data: bytes, *, content_type: str | None, settings: Settings) -> PreparedImage:
    """Decode, validate, orient, and conservatively normalize an in-memory image."""

    declared_media_type = normalize_media_type(content_type)
    if not data:
        raise ApiError(400, "invalid_image", "The selected image is empty or cannot be decoded.")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as source:
                image_format = (source.format or "").upper()
                if image_format not in FORMAT_MEDIA_TYPES:
                    raise ApiError(
                        415,
                        "unsupported_file_type",
                        "Choose a PNG, JPEG, or WebP image.",
                    )
                if FORMAT_MEDIA_TYPES[image_format] != declared_media_type:
                    raise ApiError(
                        415,
                        "unsupported_file_type",
                        "The file contents do not match the reported image type.",
                    )
                if getattr(source, "n_frames", 1) != 1:
                    raise ApiError(400, "invalid_image", "Animated images are not supported.")

                width, height = source.size
                _validate_dimensions(width, height, settings)
                source.load()
                oriented = ImageOps.exif_transpose(source)
                visual_evidence = oriented.convert("RGB")
                processed = ImageOps.autocontrast(oriented.convert("L"))
                original_width, original_height = oriented.size
    except ApiError:
        raise
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        ValueError,
    ) as exc:
        raise ApiError(
            400,
            "invalid_image",
            "The selected file is not a valid, readable image.",
        ) from exc

    processing_warnings: list[str] = []
    long_edge = max(processed.size)
    if long_edge < TARGET_LONG_EDGE:
        scale = min(MAX_UPSCALE, TARGET_LONG_EDGE / long_edge)
        resized = tuple(max(1, round(dimension * scale)) for dimension in processed.size)
        processed = processed.resize(resized, Image.Resampling.LANCZOS)
        visual_evidence = visual_evidence.resize(resized, Image.Resampling.BILINEAR)
        if min(original_width, original_height) < 300:
            processing_warnings.append(
                "The image is low resolution; extracted text may be incomplete."
            )

    processed = processed.filter(ImageFilter.UnsharpMask(radius=1, percent=125, threshold=3))
    output = BytesIO()
    processed.save(output, format="PNG")
    processed.close()
    visual_output = BytesIO()
    visual_evidence.save(visual_output, format="PNG")
    visual_evidence.close()

    return PreparedImage(
        data=output.getvalue(),
        visual_evidence_data=visual_output.getvalue(),
        original_width=original_width,
        original_height=original_height,
        original_format=image_format,
        warnings=tuple(processing_warnings),
    )


def _validate_dimensions(width: int, height: int, settings: Settings) -> None:
    if width <= 0 or height <= 0:
        raise ApiError(400, "invalid_image", "The image has invalid dimensions.")
    if (
        width > settings.max_image_width
        or height > settings.max_image_height
        or width * height > settings.max_image_pixels
    ):
        raise ApiError(
            400,
            "invalid_image_dimensions",
            "The image dimensions are too large. Choose a smaller image.",
        )
