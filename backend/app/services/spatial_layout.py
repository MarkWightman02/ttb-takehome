from collections import OrderedDict
from dataclasses import dataclass, replace
from statistics import fmean, median

from app.services.ocr import BoundingBox, OcrResult, TextRegion


@dataclass(frozen=True, slots=True)
class OcrLine:
    """A spatially coherent line reconstructed from Tesseract word evidence."""

    text: str
    words: tuple[TextRegion, ...]
    bounding_box: BoundingBox | None
    mean_confidence: float | None
    page_id: int | None
    block_id: int | None
    paragraph_id: int | None
    line_id: int | None
    approximate_line_height: float | None
    panel_id: int = 0
    sequence_number: int = 1

    @property
    def left(self) -> int | None:
        return self.bounding_box.left if self.bounding_box else None

    @property
    def top(self) -> int | None:
        return self.bounding_box.top if self.bounding_box else None

    @property
    def width(self) -> int | None:
        return self.bounding_box.width if self.bounding_box else None

    @property
    def height(self) -> int | None:
        return self.bounding_box.height if self.bounding_box else None


def reconstruct_ocr_lines(ocr_result: OcrResult) -> list[OcrLine]:
    """Rebuild lines and split Tesseract rows that span distinct columns."""

    visible = tuple(region for region in ocr_result.regions if region.text.strip())
    if not visible:
        return _raw_text_lines(ocr_result.text)

    groups: OrderedDict[tuple[int | None, ...], list[TextRegion]] = OrderedDict()
    for index, region in enumerate(visible):
        key = (region.page_id, region.block_id, region.paragraph_id, region.line_id)
        if all(value is None for value in key):
            key = (index,)
        groups.setdefault(key, []).append(region)

    reconstructed: list[OcrLine] = []
    for words in groups.values():
        reconstructed.extend(_split_tesseract_line(words, ocr_result.image_width))

    reconstructed = _assign_panels(reconstructed, ocr_result.image_width)
    reconstructed.sort(
        key=lambda line: (
            line.panel_id,
            line.top if line.top is not None else 10**9,
            line.left if line.left is not None else 10**9,
        )
    )
    return [replace(line, sequence_number=index) for index, line in enumerate(reconstructed, 1)]


def overlaps_box(line: OcrLine, excluded: BoundingBox, *, threshold: float = 0.35) -> bool:
    """Return true when a line is inside or substantially overlaps an excluded region."""

    box = line.bounding_box
    if box is None:
        return False
    intersection_width = max(
        0,
        min(box.left + box.width, excluded.left + excluded.width) - max(box.left, excluded.left),
    )
    intersection_height = max(
        0,
        min(box.top + box.height, excluded.top + excluded.height) - max(box.top, excluded.top),
    )
    intersection = intersection_width * intersection_height
    line_area = box.width * box.height
    center_x = box.left + box.width / 2
    center_y = box.top + box.height / 2
    center_inside = (
        excluded.left <= center_x <= excluded.left + excluded.width
        and excluded.top <= center_y <= excluded.top + excluded.height
    )
    return center_inside or bool(line_area and intersection / line_area >= threshold)


def union_boxes(boxes: list[BoundingBox | None]) -> BoundingBox | None:
    present = [box for box in boxes if box is not None]
    if not present:
        return None
    left = min(box.left for box in present)
    top = min(box.top for box in present)
    right = max(box.left + box.width for box in present)
    bottom = max(box.top + box.height for box in present)
    return BoundingBox(left=left, top=top, width=right - left, height=bottom - top)


def _split_tesseract_line(words: list[TextRegion], image_width: int) -> list[OcrLine]:
    boxed = [word for word in words if word.bounding_box is not None]
    if len(boxed) != len(words):
        return [_make_line(words)]

    ordered = sorted(boxed, key=lambda word: word.bounding_box.left)  # type: ignore[union-attr]
    line_height = median(word.bounding_box.height for word in ordered if word.bounding_box)
    gap_threshold = max(line_height * 3.5, image_width * 0.08)
    segments: list[list[TextRegion]] = [[]]
    previous_right: int | None = None
    for word in ordered:
        box = word.bounding_box
        if box is None:
            continue
        gap = box.left - previous_right if previous_right is not None else 0
        if segments[-1] and gap > gap_threshold:
            segments.append([])
        segments[-1].append(word)
        previous_right = box.left + box.width
    return [_make_line(segment) for segment in segments if segment]


def _make_line(words: list[TextRegion]) -> OcrLine:
    first = words[0]
    confidences = [word.confidence for word in words if word.confidence is not None]
    heights = [word.bounding_box.height for word in words if word.bounding_box is not None]
    return OcrLine(
        text=" ".join(word.text for word in words),
        words=tuple(words),
        bounding_box=union_boxes([word.bounding_box for word in words]),
        mean_confidence=fmean(confidences) if confidences else None,
        page_id=first.page_id,
        block_id=first.block_id,
        paragraph_id=first.paragraph_id,
        line_id=first.line_id,
        approximate_line_height=median(heights) if heights else None,
    )


def _assign_panels(lines: list[OcrLine], image_width: int) -> list[OcrLine]:
    boxed = [line for line in lines if line.bounding_box is not None]
    if len(boxed) < 4:
        return lines

    ordered = sorted(boxed, key=lambda line: line.left or 0)
    minimum_gap = image_width * 0.12
    boundaries: list[float] = []
    for index in range(2, len(ordered) - 1):
        left_value = ordered[index - 1].left
        right_value = ordered[index].left
        if left_value is None or right_value is None or right_value - left_value < minimum_gap:
            continue
        before = ordered[:index]
        after = ordered[index:]
        before_rights = [
            line.bounding_box.left + line.bounding_box.width
            for line in before
            if line.bounding_box is not None
        ]
        after_lefts = [line.left for line in after if line.left is not None]
        if not before_rights or not after_lefts:
            continue
        if median(before_rights) > median(after_lefts) + image_width * 0.05:
            continue
        boundaries.append((left_value + right_value) / 2)

    if not boundaries:
        return lines
    boundaries = sorted(boundaries)
    assigned: list[OcrLine] = []
    for line in lines:
        left = line.left
        panel = sum(left is not None and left > boundary for boundary in boundaries)
        assigned.append(replace(line, panel_id=panel))
    return assigned


def _raw_text_lines(raw_text: str) -> list[OcrLine]:
    return [
        OcrLine(
            text=" ".join(line.split()),
            words=(),
            bounding_box=None,
            mean_confidence=None,
            page_id=None,
            block_id=None,
            paragraph_id=None,
            line_id=None,
            approximate_line_height=None,
            sequence_number=number,
        )
        for number, line in enumerate(raw_text.splitlines(), 1)
        if line.strip()
    ]
