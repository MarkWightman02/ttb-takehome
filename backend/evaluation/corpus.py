from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Literal

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from app.models.verification import ApplicationData

REGULAR_FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
BOLD_FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")

WARNING_LINES = (
    "(1) According to the Surgeon General, women should not drink alcoholic beverages",
    "during pregnancy because of the risk of birth defects.",
    "(2) Consumption of alcoholic beverages impairs your ability to drive a car or",
    "operate machinery, and may cause health problems.",
)


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    name: str
    beverage_style: str
    application: ApplicationData
    label_lines: tuple[str, ...]
    expected: dict[str, str]
    warning_heading: str = "GOVERNMENT WARNING:"
    warning_lines: tuple[str, ...] = WARNING_LINES
    warning_heading_bold: bool = True
    degradation: str | None = None
    panel_layout: Literal["single", "product_left", "product_right"] = "single"
    notes: str = ""


@dataclass(frozen=True, slots=True)
class RenderedCase:
    data: bytes
    media_type: str


def evaluation_cases() -> tuple[EvaluationCase, ...]:
    cases = [
        _case(
            "spirits_clean_domestic",
            "distilled spirits",
            brand="Old Tom Distillery",
            class_type="Kentucky Straight Bourbon Whiskey",
            abv=45,
            volume="750 mL",
            producer="Old Tom Distillery LLC",
            address="Louisville, Kentucky",
            producer_lines=("BOTTLED BY OLD TOM DISTILLERY LLC", "LOUISVILLE, KY"),
        ),
        _case(
            "wine_clean_imported",
            "wine",
            brand="River House",
            class_type="Cabernet Sauvignon Wine",
            abv=13.5,
            volume="750 mL",
            producer="River House Imports LLC",
            address="New York, New York",
            producer_lines=("IMPORTED BY RIVER HOUSE IMPORTS LLC", "NEW YORK, NY"),
            imported=True,
            country="France",
            origin_line="PRODUCT OF FRANCE",
        ),
        _case(
            "two_panel_product_left_warning_right",
            "distilled spirits",
            brand="12345 Imports",
            class_type="Rum with Coconut Liqueur",
            abv=18,
            volume="200 mL",
            producer="12345 Imports",
            address="Miami, Florida",
            label_brand="12345 IMPORTS",
            label_class="RUM WITH\nCOCONUT LIQUEUR",
            label_abv="18% ALC./VOL.",
            label_volume="200 ML",
            producer_lines=("IMPORTED BY: 12345 IMPORTS", "MIAMI, FL"),
            imported=True,
            country="Canada",
            origin_line="PRODUCED IN CANADA",
            panel_layout="product_left",
            notes="Front product panel and back warning/importer panel share TSV rows.",
        ),
        _case(
            "two_panel_warning_left_product_right",
            "distilled spirits",
            brand="North Star",
            class_type="Canadian Whisky",
            abv=40,
            volume="750 mL",
            producer="North Star Imports",
            address="Boston, Massachusetts",
            producer_lines=("IMPORTED BY NORTH STAR IMPORTS", "BOSTON, MA"),
            imported=True,
            country="Canada",
            origin_line="PRODUCED IN CANADA",
            panel_layout="product_right",
            notes="Warning/importer panel precedes the product panel spatially.",
        ),
        _case(
            "beer_wrapped_producer",
            "malt beverage",
            brand="Harbor Light",
            class_type="India Pale Ale",
            abv=6.2,
            volume="355 mL",
            producer="Harbor Light Brewing Company",
            address="Portland, Oregon",
            producer_lines=(
                "BREWED BY",
                "HARBOR LIGHT BREWING COMPANY",
                "PORTLAND, OR",
            ),
        ),
        _case(
            "formatting_variation",
            "distilled spirits",
            brand="Stone's Throw",
            class_type="Straight Bourbon Whiskey",
            abv=40,
            volume="1 L",
            producer="Stone's Throw Spirits LLC",
            address="Nashville, Tennessee",
            label_brand="STONE’S THROW",
            label_class="STRAIGHT BOURBON-WHISKEY",
            label_abv="40.0% Alc./Vol.",
            label_volume="1000ml",
            producer_lines=("Produced by Stone’s Throw Spirits, LLC.", "NASHVILLE TN"),
        ),
        _case(
            "wrong_brand",
            "distilled spirits",
            brand="River Bend",
            class_type="Bourbon Whiskey",
            abv=45,
            volume="750 mL",
            producer="Old Tom Distillery LLC",
            address="Louisville, Kentucky",
            label_brand="OLD TOM DISTILLERY",
            producer_lines=("BOTTLED BY OLD TOM DISTILLERY LLC", "LOUISVILLE, KY"),
            overrides={"results.brand_name": "mismatch"},
        ),
        _case(
            "wrong_abv_and_volume",
            "distilled spirits",
            brand="Old Tom Distillery",
            class_type="Bourbon Whiskey",
            abv=40,
            volume="750 mL",
            producer="Old Tom Distillery LLC",
            address="Louisville, Kentucky",
            label_abv="45% ABV",
            label_volume="375 mL",
            producer_lines=("BOTTLED BY OLD TOM DISTILLERY LLC", "LOUISVILLE, KY"),
            overrides={"results.abv": "mismatch", "results.net_contents": "mismatch"},
        ),
        _case(
            "wrong_country",
            "wine",
            brand="Casa Verde",
            class_type="Red Wine",
            abv=13,
            volume="750 mL",
            producer="Casa Verde Imports",
            address="Miami, Florida",
            producer_lines=("IMPORTED BY CASA VERDE IMPORTS", "MIAMI, FL"),
            imported=True,
            country="Italy",
            origin_line="PRODUCT OF SPAIN",
            overrides={"results.country_origin": "mismatch"},
        ),
        _case(
            "altered_warning_wording",
            "malt beverage",
            brand="Harbor Light",
            class_type="Lager Beer",
            abv=5,
            volume="355 mL",
            producer="Harbor Light Brewing Company",
            address="Portland, Oregon",
            producer_lines=("BREWED BY HARBOR LIGHT BREWING COMPANY", "PORTLAND, OR"),
            warning_lines=WARNING_LINES[:-1]
            + ("operate machinery, and may cause health benefits.",),
            overrides={
                "warning.wording": "mismatch",
            },
        ),
        _case(
            "warning_heading_case",
            "wine",
            brand="North Valley",
            class_type="Chardonnay Wine",
            abv=12.5,
            volume="750 mL",
            producer="North Valley Cellars",
            address="Napa, California",
            producer_lines=("VINTED BY NORTH VALLEY CELLARS", "NAPA, CA"),
            warning_heading="Government Warning:",
            overrides={"warning.heading_capitalization": "mismatch"},
        ),
        _case(
            "missing_abv",
            "malt beverage",
            brand="Harbor Light",
            class_type="Lager Beer",
            abv=5,
            volume="355 mL",
            producer="Harbor Light Brewing Company",
            address="Portland, Oregon",
            producer_lines=("BREWED BY HARBOR LIGHT BREWING COMPANY", "PORTLAND, OR"),
            label_abv=None,
            overrides={"results.abv": "not_found"},
        ),
        _case(
            "missing_import_origin",
            "wine",
            brand="Casa Verde",
            class_type="Red Wine",
            abv=13,
            volume="750 mL",
            producer="Casa Verde Imports",
            address="Miami, Florida",
            producer_lines=("IMPORTED BY CASA VERDE IMPORTS", "MIAMI, FL"),
            imported=True,
            country="Spain",
            overrides={"results.country_origin": "not_found"},
        ),
        _case(
            "missing_warning",
            "distilled spirits",
            brand="Old Tom Distillery",
            class_type="Bourbon Whiskey",
            abv=45,
            volume="750 mL",
            producer="Old Tom Distillery LLC",
            address="Louisville, Kentucky",
            producer_lines=("BOTTLED BY OLD TOM DISTILLERY LLC", "LOUISVILLE, KY"),
            warning_lines=(),
            overrides={
                "warning.presence": "not_found",
                "warning.wording": "not_found",
                "warning.heading_capitalization": "not_found",
                "warning.heading_boldness": "not_found",
                "warning.body_not_bold": "not_found",
                "warning.continuous_statement": "not_found",
                "warning.separation": "not_found",
                "warning.legibility_contrast": "not_found",
            },
        ),
        _case(
            "partial_producer_address",
            "distilled spirits",
            brand="Old Tom Distillery",
            class_type="Bourbon Whiskey",
            abv=45,
            volume="750 mL",
            producer="Old Tom Distillery LLC",
            address="123 Main Street, Louisville, Kentucky",
            producer_lines=("BOTTLED BY OLD TOM DISTILLERY LLC", "LOUISVILLE, KY"),
            overrides={"results.producer_address": "review"},
        ),
        _case(
            "multiple_responsible_entities",
            "wine",
            brand="North Valley",
            class_type="Red Wine",
            abv=13,
            volume="750 mL",
            producer="North Valley Cellars",
            address="Napa, California",
            producer_lines=(
                "PRODUCED BY NORTH VALLEY CELLARS",
                "NAPA, CA",
                "BOTTLED BY CENTRAL COAST BOTTLING",
                "FRESNO, CA",
            ),
            overrides={
                "results.producer_name": "review",
                "results.producer_address": "review",
            },
            notes="Two distinct cue-backed responsible entities require reviewer selection.",
        ),
        _case(
            "degraded_imported_wine",
            "wine",
            brand="River House",
            class_type="Cabernet Sauvignon Wine",
            abv=13.5,
            volume="750 mL",
            producer="River House Imports LLC",
            address="New York, New York",
            producer_lines=("IMPORTED BY RIVER HOUSE IMPORTS LLC", "NEW YORK, NY"),
            imported=True,
            country="France",
            origin_line="MADE IN FRANCE",
            degradation="mild_photo",
            notes="Mild rotation, blur, contrast loss, downsampling, and JPEG artifacts.",
        ),
        _case(
            "ambiguous_warning_weight",
            "malt beverage",
            brand="Harbor Light",
            class_type="India Pale Ale",
            abv=6.2,
            volume="355 mL",
            producer="Harbor Light Brewing Company",
            address="Portland, Oregon",
            producer_lines=("BREWED BY HARBOR LIGHT BREWING COMPANY", "PORTLAND, OR"),
            warning_heading_bold=False,
            overrides={
                "warning.heading_boldness": "review",
                "warning.body_not_bold": "review",
            },
        ),
    ]
    return tuple(cases)


def render_case(case: EvaluationCase) -> RenderedCase:
    if not REGULAR_FONT.is_file() or not BOLD_FONT.is_file():
        raise RuntimeError("The evaluation corpus requires DejaVu Sans fonts.")
    image = Image.new("RGB", (2800 if case.panel_layout != "single" else 2600, 1800), "white")
    draw = ImageDraw.Draw(image)
    title_font = ImageFont.truetype(BOLD_FONT, 56)
    body_font = ImageFont.truetype(REGULAR_FONT, 34)
    heading_font = ImageFont.truetype(BOLD_FONT if case.warning_heading_bold else REGULAR_FONT, 36)
    if case.panel_layout == "single":
        draw.multiline_text(
            (100, 55),
            "\n".join(case.label_lines),
            fill="black",
            font=title_font,
            spacing=18,
        )
        if case.warning_lines:
            warning_y = 850
            draw.text((100, warning_y), case.warning_heading, fill="black", font=heading_font)
            for index, line in enumerate(case.warning_lines, 1):
                draw.text((100, warning_y + index * 58), line, fill="black", font=body_font)
    else:
        _draw_multi_panel(image, case)

    media_type = "image/png"
    save_format = "PNG"
    save_options: dict[str, int] = {}
    if case.degradation == "mild_photo":
        image = image.rotate(1.1, resample=Image.Resampling.BICUBIC, fillcolor="white")
        image = ImageEnhance.Contrast(image).enhance(0.7)
        image = image.filter(ImageFilter.GaussianBlur(radius=0.55))
        image = image.resize((1820, 1260), Image.Resampling.LANCZOS)
        media_type = "image/jpeg"
        save_format = "JPEG"
        save_options = {"quality": 55}

    output = BytesIO()
    image.save(output, format=save_format, **save_options)
    image.close()
    return RenderedCase(data=output.getvalue(), media_type=media_type)


def _case(
    name: str,
    beverage_style: str,
    *,
    brand: str,
    class_type: str,
    abv: float,
    volume: str,
    producer: str,
    address: str,
    producer_lines: tuple[str, ...],
    imported: bool = False,
    country: str | None = None,
    origin_line: str | None = None,
    label_brand: str | None = None,
    label_class: str | None = None,
    label_abv: str | None | object = ...,
    label_volume: str | None = None,
    warning_heading: str = "GOVERNMENT WARNING:",
    warning_lines: tuple[str, ...] = WARNING_LINES,
    warning_heading_bold: bool = True,
    degradation: str | None = None,
    panel_layout: Literal["single", "product_left", "product_right"] = "single",
    notes: str = "",
    overrides: dict[str, str] | None = None,
) -> EvaluationCase:
    abv_line = f"{abv:g}% ABV" if label_abv is ... else label_abv
    lines = [
        label_brand or brand.upper(),
        label_class or class_type,
        abv_line,
        label_volume or volume,
    ]
    lines.extend(producer_lines)
    if origin_line:
        lines.append(origin_line)
    expected = _matching_expectations(imported)
    expected.update(overrides or {})
    return EvaluationCase(
        name=name,
        beverage_style=beverage_style,
        application=ApplicationData(
            brand_name=brand,
            class_type=class_type,
            abv=abv,
            net_contents=volume,
            producer_name=producer,
            producer_address=address,
            imported_product=imported,
            country_origin=country,
        ),
        label_lines=tuple(line for line in lines if isinstance(line, str)),
        expected=expected,
        warning_heading=warning_heading,
        warning_lines=warning_lines,
        warning_heading_bold=warning_heading_bold,
        degradation=degradation,
        panel_layout=panel_layout,
        notes=notes,
    )


def _matching_expectations(imported: bool) -> dict[str, str]:
    return {
        "results.brand_name": "match",
        "results.class_type": "match",
        "results.abv": "match",
        "results.net_contents": "match",
        "results.producer_name": "match",
        "results.producer_address": "match",
        "results.country_origin": "match" if imported else "not_applicable",
        "warning.presence": "match",
        "warning.wording": "match",
        "warning.heading_capitalization": "match",
        "warning.heading_boldness": "match",
        "warning.body_not_bold": "match",
        "warning.continuous_statement": "review",
        "warning.separation": "match",
        "warning.legibility_contrast": "match",
        "warning.type_size": "review",
        "warning.characters_per_inch": "review",
    }


def _draw_multi_panel(image: Image.Image, case: EvaluationCase) -> None:
    draw = ImageDraw.Draw(image)
    product_x, secondary_x = (120, 1500) if case.panel_layout == "product_left" else (1500, 120)
    draw.rectangle((50, 40, 1300, 1720), outline="black", width=3)
    draw.rectangle((1450, 40, 2750, 1720), outline="black", width=3)

    brand_font = ImageFont.truetype(BOLD_FONT, 58)
    class_font = ImageFont.truetype(BOLD_FONT, 50)
    field_font = ImageFont.truetype(BOLD_FONT, 42)
    secondary_font = ImageFont.truetype(BOLD_FONT, 32)
    warning_heading_font = ImageFont.truetype(
        BOLD_FONT if case.warning_heading_bold else REGULAR_FONT, 32
    )
    warning_body_font = ImageFont.truetype(REGULAR_FONT, 24)

    product_lines = case.label_lines[:4]
    secondary_lines = case.label_lines[4:]
    draw.text((product_x, 100), product_lines[0], fill="black", font=brand_font)
    draw.multiline_text(
        (product_x, 475), product_lines[1], fill="black", font=class_font, spacing=18
    )
    draw.text((product_x, 690), product_lines[2], fill="black", font=field_font)
    draw.text((product_x, 765), product_lines[3], fill="black", font=field_font)
    if case.application.imported_product:
        draw.text((product_x, 910), "IMPORTED", fill="black", font=field_font)

    for index, line in enumerate(secondary_lines):
        draw.text((secondary_x, 100 + index * 70), line, fill="black", font=secondary_font)
    if case.warning_lines:
        warning_y = 405
        draw.text(
            (secondary_x, warning_y), case.warning_heading, fill="black", font=warning_heading_font
        )
        for index, line in enumerate(case.warning_lines, 1):
            draw.text(
                (secondary_x, warning_y + index * 62),
                line,
                fill="black",
                font=warning_body_font,
            )
