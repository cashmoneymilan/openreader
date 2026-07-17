from __future__ import annotations

import base64
import hashlib
import html
import json
import re
import shutil
import tempfile
import uuid
import zipfile
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import pymupdf

from openreader_engine.conversion.validator import XTEINK_MAX_IMAGE_DIMENSION, validate_epub
from openreader_engine.models import ConversionMode, ConversionReport, StructureSection, SupportTier
from openreader_engine.utils import (
    atomic_write,
    normalize_for_comparison,
    normalize_reader_text,
    run_command,
    safe_filename,
    sha256_file,
)

PAGE_CHUNK_SIZE = 8


def _inspect_pdf(source: Path) -> tuple[int, list[str], str | None]:
    """Use Poppler when present, with a bundled PyMuPDF path for clean Macs."""
    pdfinfo = shutil.which("pdfinfo")
    pdftotext = shutil.which("pdftotext")
    pdftoppm = shutil.which("pdftoppm")
    if pdfinfo and pdftotext and pdftoppm:
        info = run_command([pdfinfo, str(source)])
        page_match = re.search(r"^Pages:\s+(\d+)", info.stdout, re.M)
        if not page_match:
            raise RuntimeError("Could not determine PDF page count")
        pages = int(page_match.group(1))
        extracted = run_command([pdftotext, "-layout", str(source), "-"])
        page_texts = extracted.stdout.replace("\r", "").split("\f")
        if len(page_texts) > pages:
            page_texts = page_texts[:pages]
        page_texts.extend([""] * max(0, pages - len(page_texts)))
        return pages, page_texts, pdftoppm

    with pymupdf.open(source) as document:
        if document.needs_pass:
            raise RuntimeError("Password-protected PDFs are not supported in Milestone 0")
        page_texts = [page.get_text("text", sort=True) for page in document]
        return len(document), page_texts, None


def _render_pdf_pages(source: Path, temporary: Path, pages: int, pdftoppm: str | None) -> list[Path]:
    if pdftoppm:
        prefix = temporary / "page"
        run_command(
            [
                pdftoppm,
                "-jpeg",
                "-scale-to",
                str(XTEINK_MAX_IMAGE_DIMENSION),
                "-jpegopt",
                "quality=80,optimize=y",
                str(source),
                str(prefix),
            ]
        )
        rendered = sorted(temporary.glob("page-*.jpg"), key=lambda value: int(re.search(r"(\d+)$", value.stem).group(1)))
    else:
        rendered = []
        with pymupdf.open(source) as document:
            for index, page in enumerate(document, 1):
                scale = XTEINK_MAX_IMAGE_DIMENSION / max(page.rect.width, page.rect.height)
                pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), colorspace=pymupdf.csRGB, alpha=False)
                target = temporary / f"page-{index}.jpg"
                pixmap.save(target, jpg_quality=80)
                rendered.append(target)
    if len(rendered) < pages:
        raise RuntimeError(f"Rendered only {len(rendered)} of {pages} pages")
    return rendered


def _clean_line(value: str) -> str:
    value = normalize_reader_text(value)
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"\s+([,.;:!?])", r"\1", value)
    return value.strip()


def _is_heading(value: str) -> bool:
    return bool(
        re.match(r"^(chapter|part|appendix|contents|preface|introduction|conclusion|references|bibliography|acknowledg)", value, re.I)
        or (len(value) < 70 and value == value.upper() and re.search(r"[A-Z]", value))
    )


def _paragraphs(lines: list[str]) -> list[str]:
    output: list[str] = []
    current = ""
    for source_line in lines:
        line = _clean_line(source_line)
        if not line:
            if current:
                output.append(current)
                current = ""
            continue
        if not current:
            current = line
        elif _is_heading(line) or (len(line) < 88 and re.search(r"[.!?:]$", current)):
            output.append(current)
            current = line
        else:
            current += f" {line}"
    if current:
        output.append(current)
    return [value for value in output if len(value) > 1]


def _text_retention(source: str, output: str) -> float | None:
    source_tokens = Counter(re.findall(r"[\w']+", normalize_reader_text(source).casefold()))
    if not source_tokens:
        return None
    output_tokens = Counter(re.findall(r"[\w']+", normalize_reader_text(output).casefold()))
    retained = sum(min(count, output_tokens[token]) for token, count in source_tokens.items())
    return round(retained / sum(source_tokens.values()), 4)


def _xhtml(title: str, body: str) -> str:
    escaped_title = html.escape(title, quote=True)
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">'
        '<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en">'
        f'<head><title>{escaped_title}</title><meta http-equiv="Content-Type" content="text/html; charset=utf-8" />'
        '<style>body{font-family:serif;line-height:1.45;margin:0;padding:0;font-size:100%;}'
        '.page{margin:0;}h1{font-size:1.7em;line-height:1.1;margin:0 0 .8em;}'
        'h2{font-size:1.2em;line-height:1.2;margin:1.2em 0 .45em;page-break-before:always;}'
        'p{margin:0 0 .65em;text-indent:0}.cover-subtitle{font-style:italic;margin-bottom:2em}'
        '.page-kicker{font-size:.7em;color:#666;margin:1em 0 .5em;border-bottom:1px solid #aaa;padding-bottom:.35em}'
        '.image-page{page-break-before:always;text-align:center}.image-page img{max-width:100%;height:auto;display:block;margin:auto}'
        '</style></head>'
        f"<body>{body}</body></html>"
    )


class PDFToEpubProcessor:
    """Deterministic Milestone 0 PDF processor with a conservative Xteink profile."""

    processor_version = "openreader-pdf/0.0.1"

    def convert(self, source: Path, output_dir: Path, profile: str = "xteink") -> ConversionReport:
        if profile != "xteink":
            raise ValueError("Milestone 0 currently implements only the xteink profile")
        source = source.expanduser().resolve()
        if source.suffix.casefold() != ".pdf" or not source.is_file():
            raise ValueError(f"Expected an existing PDF: {source}")

        root = output_dir.expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)

        source_sha = sha256_file(source)
        original = root / "originals" / source_sha[:2] / f"{source_sha}.pdf"
        if not original.exists():
            atomic_write(original, source.read_bytes())

        pages, page_texts, pdftoppm = _inspect_pdf(source)
        source_text = "\n".join(page_texts)
        source_characters = len(normalize_for_comparison(source_text))
        mode = ConversionMode.PAGE_IMAGES if source_characters < max(400, pages * 20) else ConversionMode.REFLOW
        if mode == ConversionMode.PAGE_IMAGES:
            support_tier = SupportTier.B
            tier_reasons = ["No dependable text layer was detected", "Page-image preservation selected for review"]
        else:
            support_tier = SupportTier.A
            tier_reasons = ["Dependable text layer detected", "Single-flow reconstruction selected"]

        title = safe_filename(normalize_reader_text(source.stem.replace("_", "-").replace("-", " ")))
        stem = safe_filename(source.stem)
        output = root / "derivatives" / f"{stem}.epub"
        preview = root / "previews" / f"{stem}.html"
        structure_path = root / "manifests" / f"{stem}.openreader.json"
        output.parent.mkdir(parents=True, exist_ok=True)

        page_files: list[str] = []
        image_files: list[str] = []
        rendered_images: list[Path] = []
        sections: list[StructureSection] = []
        xhtml_documents: dict[str, str] = {}
        reconstructed_text_parts: list[str] = []
        text_offset = 0

        with tempfile.TemporaryDirectory(prefix="openreader-m0-") as temporary_name:
            temporary = Path(temporary_name)
            if mode == ConversionMode.PAGE_IMAGES:
                rendered_images = _render_pdf_pages(source, temporary, pages, pdftoppm)
                image_files = [f"images/page-{index}.jpg" for index in range(1, pages + 1)]

            for start in range(0, pages, PAGE_CHUNK_SIZE):
                end = min(pages, start + PAGE_CHUNK_SIZE)
                chunk_number = start // PAGE_CHUNK_SIZE + 1
                xhtml_path = f"text-{chunk_number}.xhtml"
                page_files.append(xhtml_path)
                body_parts: list[str] = []
                chunk_text: list[str] = []
                if start == 0 and mode == ConversionMode.REFLOW:
                    body_parts.append(
                        f"<div><h1>{html.escape(title)}</h1><p class=\"cover-subtitle\">Converted locally from PDF - {pages} pages</p></div>"
                    )
                for page_index in range(start, end):
                    page_number = page_index + 1
                    if mode == ConversionMode.PAGE_IMAGES:
                        body_parts.append(
                            f'<div class="image-page" id="page-{page_number}"><img src="images/page-{page_number}.jpg" alt="PDF page {page_number}" /></div>'
                        )
                    else:
                        paragraphs = _paragraphs(page_texts[page_index].splitlines())
                        chunk_text.extend(paragraphs)
                        markup = "\n".join(
                            f"<h2>{html.escape(paragraph)}</h2>" if _is_heading(paragraph) else f"<p>{html.escape(paragraph)}</p>"
                            for paragraph in paragraphs
                        )
                        body_parts.append(
                            f'<div class="page" id="page-{page_number}"><div class="page-kicker">Page {page_number}</div>{markup or "<p>[No extractable text on this page]</p>"}</div>'
                        )
                reconstructed = "\n".join(chunk_text)
                reconstructed_text_parts.append(reconstructed)
                fingerprint = hashlib.sha256(normalize_for_comparison(reconstructed).encode()).hexdigest()
                section_id = hashlib.sha256(f"{source_sha}:{start + 1}:{end}:{fingerprint}".encode()).hexdigest()[:20]
                sections.append(
                    StructureSection(
                        id=section_id,
                        parent_id=None,
                        heading=f"Pages {start + 1}-{end}",
                        order=chunk_number,
                        source_page_start=start + 1,
                        source_page_end=end,
                        source_text_start=text_offset,
                        source_text_end=text_offset + len(reconstructed),
                        xhtml_path=xhtml_path,
                        fragment_id=f"page-{start + 1}",
                        content_fingerprint=fingerprint,
                    )
                )
                text_offset += len(reconstructed)
                xhtml_documents[xhtml_path] = _xhtml(title, "\n".join(body_parts))

            identifier = f"urn:uuid:{uuid.uuid4()}"
            structure_payload = {
                "schema": "openreader.document-structure.v1",
                "source_sha256": source_sha,
                "processor": self.processor_version,
                "profile": profile,
                "sections": [asdict(section) for section in sections],
            }
            package = self._package_epub(
                title=title,
                identifier=identifier,
                pages=pages,
                page_files=page_files,
                xhtml_documents=xhtml_documents,
                image_files=image_files,
                rendered_images=rendered_images,
                structure_payload=structure_payload,
            )
            atomic_write(output, package)

        output_sha = sha256_file(output)
        validation = validate_epub(output, profile=profile)
        if not validation.valid:
            messages = "; ".join(issue.message for issue in validation.issues if issue.level == "error")
            raise RuntimeError(f"Generated EPUB failed validation: {messages}")

        structure_payload["output_sha256"] = output_sha
        structure_payload["immutable_original"] = str(original)
        atomic_write(structure_path, json.dumps(structure_payload, indent=2, ensure_ascii=False).encode("utf-8"))
        self._write_preview(output, preview, title, mode)

        reconstructed_text = "\n".join(reconstructed_text_parts)
        output_characters = len(normalize_for_comparison(reconstructed_text))
        return ConversionReport(
            source=str(source),
            immutable_original=str(original),
            output=str(output),
            preview=str(preview),
            structure_manifest=str(structure_path),
            source_sha256=source_sha,
            output_sha256=output_sha,
            pages=pages,
            mode=mode,
            support_tier=support_tier,
            tier_reasons=tier_reasons,
            source_characters=source_characters,
            output_characters=output_characters,
            normalized_text_retention=_text_retention(source_text, reconstructed_text) if mode == ConversionMode.REFLOW else None,
            validation=validation,
        )

    def _package_epub(
        self,
        *,
        title: str,
        identifier: str,
        pages: int,
        page_files: list[str],
        xhtml_documents: dict[str, str],
        image_files: list[str],
        rendered_images: list[Path],
        structure_payload: dict,
    ) -> bytes:
        with tempfile.SpooledTemporaryFile(max_size=32 * 1024 * 1024) as stream:
            with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=8) as archive:
                mimetype = zipfile.ZipInfo("mimetype")
                mimetype.compress_type = zipfile.ZIP_STORED
                archive.writestr(mimetype, b"application/epub+zip")
                archive.writestr(
                    "META-INF/container.xml",
                    '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml" /></rootfiles></container>',
                )
                archive.writestr("META-INF/openreader-structure.json", json.dumps(structure_payload, ensure_ascii=False, separators=(",", ":")))
                for path, document in xhtml_documents.items():
                    archive.writestr(f"OEBPS/{path}", document)
                for path, rendered in zip(image_files, rendered_images, strict=True):
                    archive.writestr(f"OEBPS/{path}", rendered.read_bytes())
                archive.writestr("OEBPS/content.opf", self._opf(title, identifier, page_files, image_files))
                archive.writestr("OEBPS/nav.xhtml", self._nav(title, page_files, pages))
                archive.writestr("OEBPS/toc.ncx", self._ncx(title, identifier, page_files, pages))
            stream.seek(0)
            return stream.read()

    @staticmethod
    def _opf(title: str, identifier: str, page_files: list[str], image_files: list[str]) -> str:
        manifest_pages = "".join(
            f'<item id="page-{index}" href="{path}" media-type="application/xhtml+xml" />'
            for index, path in enumerate(page_files, 1)
        )
        manifest_images = "".join(
            f'<item id="image-{index}" href="{path}" media-type="image/jpeg" />'
            for index, path in enumerate(image_files, 1)
        )
        spine = "".join(f'<itemref idref="page-{index}" />' for index in range(1, len(page_files) + 1))
        return (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="book-id" version="2.0">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
            f'<dc:identifier id="book-id">{html.escape(identifier)}</dc:identifier><dc:title>{html.escape(title)}</dc:title><dc:language>en</dc:language>'
            '</metadata><manifest><item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml" />'
            f'<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" />{manifest_pages}{manifest_images}'
            f'</manifest><spine toc="ncx">{spine}</spine></package>'
        )

    @staticmethod
    def _nav(title: str, page_files: list[str], pages: int) -> str:
        links = "".join(
            f'<li><a href="{path}#page-{(index - 1) * PAGE_CHUNK_SIZE + 1}">Pages {(index - 1) * PAGE_CHUNK_SIZE + 1}-{min(index * PAGE_CHUNK_SIZE, pages)}</a></li>'
            for index, path in enumerate(page_files, 1)
        )
        return _xhtml("Contents", f"<h1>{html.escape(title)}</h1><ol>{links}</ol>")

    @staticmethod
    def _ncx(title: str, identifier: str, page_files: list[str], pages: int) -> str:
        points = "".join(
            f'<navPoint id="navpoint-{index}" playOrder="{index}"><navLabel><text>Pages {(index - 1) * PAGE_CHUNK_SIZE + 1}-{min(index * PAGE_CHUNK_SIZE, pages)}</text></navLabel><content src="{path}#page-{(index - 1) * PAGE_CHUNK_SIZE + 1}" /></navPoint>'
            for index, path in enumerate(page_files, 1)
        )
        return (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx" version="2005-1">'
            f'<head><meta name="dtb:uid" content="{html.escape(identifier)}" /><meta name="dtb:depth" content="1" /></head>'
            f'<docTitle><text>{html.escape(title)}</text></docTitle><navMap>{points}</navMap></ncx>'
        )

    @staticmethod
    def _write_preview(epub: Path, preview: Path, title: str, mode: ConversionMode) -> None:
        with zipfile.ZipFile(epub) as archive:
            document = archive.read("OEBPS/text-1.xhtml").decode("utf-8")
            if mode == ConversionMode.PAGE_IMAGES and "OEBPS/images/page-1.jpg" in archive.namelist():
                encoded = base64.b64encode(archive.read("OEBPS/images/page-1.jpg")).decode("ascii")
                document = document.replace("images/page-1.jpg", f"data:image/jpeg;base64,{encoded}", 1)
            banner = (
                '<div style="position:sticky;top:0;padding:10px 14px;background:#17231f;color:#fff;font:12px sans-serif">'
                f'OpenReader approximate Xteink preview - {html.escape(title)}</div>'
            )
            document = document.replace("<body>", f"<body>{banner}", 1)
            atomic_write(preview, document.encode("utf-8"))
