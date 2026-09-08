from io import BytesIO

import pytest
from PIL import Image

from app.core.config import Settings
from app.core.errors import ApiError
from app.services.image_preprocessing import prepare_image


def encoded_image(
    image_format: str = "PNG",
    size: tuple[int, int] = (500, 250),
    *,
    exif: Image.Exif | None = None,
) -> bytes:
    output = BytesIO()
    save_options = {"exif": exif} if exif is not None else {}
    Image.new("RGB", size, "white").save(output, format=image_format, **save_options)
    return output.getvalue()


def test_preprocessing_normalizes_orientation_grayscale_and_small_image(settings: Settings):
    exif = Image.Exif()
    exif[274] = 6
    prepared = prepare_image(
        encoded_image("JPEG", (500, 250), exif=exif),
        content_type="image/jpeg",
        settings=settings,
    )

    assert (prepared.original_width, prepared.original_height) == (250, 500)
    assert prepared.original_format == "JPEG"
    assert prepared.warnings == ("The image is low resolution; extracted text may be incomplete.",)
    with Image.open(BytesIO(prepared.data)) as image:
        assert image.format == "PNG"
        assert image.mode == "L"
        assert image.size == (500, 1000)


def test_preprocessing_rejects_mime_content_mismatch(settings: Settings):
    with pytest.raises(ApiError) as error:
        prepare_image(
            encoded_image("JPEG"),
            content_type="image/png",
            settings=settings,
        )

    assert error.value.status_code == 415
    assert error.value.code == "unsupported_file_type"


def test_preprocessing_rejects_excessive_dimensions(settings: Settings):
    settings.max_image_pixels = 10_000
    with pytest.raises(ApiError) as error:
        prepare_image(
            encoded_image(size=(101, 100)),
            content_type="image/png",
            settings=settings,
        )

    assert error.value.code == "invalid_image_dimensions"
