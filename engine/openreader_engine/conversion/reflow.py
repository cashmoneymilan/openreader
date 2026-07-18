from __future__ import annotations

import html
import math
import re
import statistics
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from openreader_engine.utils import normalize_reader_text


@dataclass(frozen=True)
class RichSpan:
    text: str
    bold: bool
    italic: bool
    size: float

    def markup(self) -> str:
        value = html.escape(self.text)
        if self.bold:
            value = f"<strong>{value}</strong>"
        if self.italic:
            value = f"<em>{value}</em>"
        return value


@dataclass(frozen=True)
class RichLine:
    page: int
    block: int
    bbox: tuple[float, float, float, float]
    spans: tuple[RichSpan, ...]

    @property
    def text(self) -> str:
        return normalize_reader_text("".join(span.text for span in self.spans)).strip()

    @property
    def markup(self) -> str:
        return "".join(span.markup() for span in self.spans).strip()

    @property
    def max_size(self) -> float:
        return max((span.size for span in self.spans), default=0.0)

    @property
    def typical_size(self) -> float:
        weighted = [
            span.size
            for span in self.spans
            for _ in range(max(1, min(len(span.text.strip()), 80)))
        ]
        return statistics.median(weighted) if weighted else 0.0

    @property
    def bold_ratio(self) -> float:
        characters = sum(len(span.text.strip()) for span in self.spans)
        if not characters:
            return 0.0
        bold = sum(len(span.text.strip()) for span in self.spans if span.bold)
        return bold / characters


@dataclass(frozen=True)
class ReflowBlock:
    page: int
    kind: str
    text: str
    markup: str
    anchor: str | None = None


@dataclass(frozen=True)
class RenderedVisual:
    page: int
    path: Path


@dataclass(frozen=True)
class ReflowDocument:
    pages: int
    blocks: tuple[ReflowBlock, ...]
    source_text: str
    removed_running_lines: int
    visuals: tuple[RenderedVisual, ...]


def _line_signature(value: str) -> str:
    value = normalize_reader_text(value).casefold()
    value = re.sub(r"\d+", "#", value)
    value = re.sub(r"[^\w#]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _is_page_number(value: str) -> bool:
    return bool(re.fullmatch(r"(?:page\s+)?(?:\d{1,4}|[ivxlcdm]{1,8})", value.strip(), re.I))


def _is_vendor_footer(value: str) -> bool:
    return bool(
        re.search(r"EBSCO\s+Publishing.*(?:EBSCOhost|printed on|Account:)", value, re.I)
    )


def _join_text(left: str, right: str) -> str:
    right = right.strip()
    if not left:
        return right
    if left.endswith("-") and right[:1].islower():
        return left[:-1] + right
    return f"{left.rstrip()} {right}"


def _join_markup(left: str, right: str, left_text: str, right_text: str) -> str:
    if not left:
        return right
    if left_text.endswith("-") and right_text[:1].islower():
        return re.sub(r"-(?=(?:</(?:strong|em)>)*$)", "", left) + right
    return f"{left.rstrip()} {right.lstrip()}"


def _heading_kind(line: RichLine, body_size: float) -> str | None:
    value = line.text
    if not value or len(value) > 140:
        return None
    if re.match(r"^(?:chapter\s+\d+|part\s+(?:\d+|[ivxlcdm]+)|book\s+(?:\d+|[ivxlcdm]+))(?:\s*[:.\-–—]\s*.*)?$", value, re.I):
        return "h2"
    if re.match(
        r"^(?:appendix|preface|introduction|conclusion|epilogue|prologue|contents|references|bibliography|acknowledgments?)(?:\s*[:.\-–—•]\s*.*|\s+\d+)?$",
        value,
        re.I,
    ):
        return "h2"
    if (
        re.match(r"^(?:[1-9]\d?|[IVXLCDM]{1,6})[.)]\s+[A-Z]", value)
        and len(value) < 90
        and not value.endswith(".")
        and (line.typical_size >= body_size * 1.12 or line.bold_ratio >= 0.6)
    ):
        return "h2"
    if line.typical_size >= body_size * 1.45:
        return "h2"
    if line.typical_size >= body_size * 1.12 and line.bold_ratio >= 0.6 and not value.endswith("."):
        return "h3"
    if len(value) < 90 and value == value.upper() and re.search(r"[A-Z]", value):
        return "h3"
    return None


def _extract_lines(document: pymupdf.Document) -> tuple[list[RichLine], float, dict[int, bool]]:
    lines: list[RichLine] = []
    weighted_sizes: list[float] = []
    complex_pages: dict[int, bool] = {}
    for page_index, page in enumerate(document, 1):
        payload = page.get_text("dict", sort=True)
        page_area = max(page.rect.width * page.rect.height, 1.0)
        meaningful_image = any(
            block.get("type") == 1
            and pymupdf.Rect(block.get("bbox", (0, 0, 0, 0))).get_area() / page_area >= 0.03
            for block in payload.get("blocks", [])
        )
        complex_pages[page_index] = meaningful_image or len(page.get_drawings()) >= 6
        for block_index, block in enumerate(payload.get("blocks", [])):
            if block.get("type") != 0:
                continue
            for source_line in block.get("lines", []):
                spans: list[RichSpan] = []
                for source_span in source_line.get("spans", []):
                    text = normalize_reader_text(source_span.get("text", ""))
                    if not text:
                        continue
                    flags = int(source_span.get("flags", 0))
                    font_name = str(source_span.get("font", "")).casefold()
                    bold = bool(flags & 16) or "bold" in font_name or "black" in font_name
                    italic = bool(flags & 2) or "italic" in font_name or "oblique" in font_name
                    size = float(source_span.get("size", 0.0))
                    spans.append(RichSpan(text=text, bold=bold, italic=italic, size=size))
                    weighted_sizes.extend([size] * max(1, min(len(text.strip()), 80)))
                if spans:
                    lines.append(
                        RichLine(
                            page=page_index,
                            block=block_index,
                            bbox=tuple(float(value) for value in source_line.get("bbox", (0, 0, 0, 0))),
                            spans=tuple(spans),
                        )
                    )
    body_size = statistics.median(weighted_sizes) if weighted_sizes else 10.0
    return lines, body_size, complex_pages


def _running_signatures(lines: list[RichLine], document: pymupdf.Document, body_size: float) -> set[str]:
    occurrences: dict[str, set[int]] = defaultdict(set)
    for line in lines:
        page = document[line.page - 1]
        top = line.bbox[1] <= page.rect.height * 0.13
        bottom = line.bbox[3] >= page.rect.height * 0.87
        signature = _line_signature(line.text)
        header_sized = line.typical_size <= body_size * 1.08
        if (top or bottom) and header_sized and signature and len(signature) <= 180:
            occurrences[signature].add(line.page)
    threshold = max(3, math.ceil(len(document) * 0.18))
    return {signature for signature, pages in occurrences.items() if len(pages) >= threshold}


def _render_complex_pages(
    document: pymupdf.Document,
    complex_pages: dict[int, bool],
    output_dir: Path,
    max_dimension: int,
) -> tuple[RenderedVisual, ...]:
    output_dir.mkdir(parents=True, exist_ok=True)
    output: list[RenderedVisual] = []
    for page_number, should_render in complex_pages.items():
        if not should_render:
            continue
        page = document[page_number - 1]
        scale = max_dimension / max(page.rect.width, page.rect.height)
        pixmap = page.get_pixmap(
            matrix=pymupdf.Matrix(scale, scale),
            colorspace=pymupdf.csRGB,
            alpha=False,
        )
        target = output_dir / f"figure-page-{page_number}.jpg"
        pixmap.save(target, jpg_quality=78)
        output.append(RenderedVisual(page=page_number, path=target))
    return tuple(output)


def extract_reflow_document(source: Path, image_dir: Path, max_image_dimension: int) -> ReflowDocument:
    with pymupdf.open(source) as document:
        if document.needs_pass:
            raise RuntimeError("Password-protected PDFs are not supported")
        lines, body_size, complex_pages = _extract_lines(document)
        running = _running_signatures(lines, document, body_size)
        filtered: list[RichLine] = []
        removed = 0
        for line in lines:
            page = document[line.page - 1]
            in_margin = line.bbox[1] <= page.rect.height * 0.13 or line.bbox[3] >= page.rect.height * 0.87
            if (
                _line_signature(line.text) in running
                or (in_margin and _is_page_number(line.text))
                or (in_margin and _is_vendor_footer(line.text))
            ):
                removed += 1
                continue
            filtered.append(line)

        blocks: list[ReflowBlock] = []
        heading_counter = 0
        current_page = 0
        current_block = -1
        current_text = ""
        current_markup = ""
        previous_text = ""

        def flush_paragraph() -> None:
            nonlocal current_text, current_markup, previous_text
            if current_text.strip():
                blocks.append(
                    ReflowBlock(
                        page=current_page,
                        kind="p",
                        text=current_text.strip(),
                        markup=current_markup.strip(),
                    )
                )
            current_text = ""
            current_markup = ""
            previous_text = ""

        for line in filtered:
            heading_kind = _heading_kind(line, body_size)
            if heading_kind:
                flush_paragraph()
                heading_counter += 1
                blocks.append(
                    ReflowBlock(
                        page=line.page,
                        kind=heading_kind,
                        text=line.text,
                        markup=line.markup,
                        anchor=f"section-{line.page}-{heading_counter}",
                    )
                )
                current_page = line.page
                current_block = line.block
                continue

            if current_text and (line.page != current_page or line.block != current_block):
                flush_paragraph()
            current_page = line.page
            current_block = line.block
            current_markup = _join_markup(current_markup, line.markup, previous_text, line.text)
            current_text = _join_text(current_text, line.text)
            previous_text = line.text
        flush_paragraph()

        visuals = _render_complex_pages(document, complex_pages, image_dir, max_image_dimension)
        source_text = "\n".join(block.text for block in blocks)
        return ReflowDocument(
            pages=len(document),
            blocks=tuple(blocks),
            source_text=source_text,
            removed_running_lines=removed,
            visuals=visuals,
        )
