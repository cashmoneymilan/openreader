from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pymupdf

from openreader_engine.conversion import PDFToEpubProcessor, validate_epub
from openreader_engine.models import ConversionMode, SupportTier
from openreader_engine.utils import normalize_reader_text


def test_pdf_vertical_slice_creates_valid_versioned_derivative(text_pdf: Path, tmp_path: Path) -> None:
    root = tmp_path / "library"
    report = PDFToEpubProcessor().convert(text_pdf, root)

    assert report.mode == ConversionMode.REFLOW
    assert report.support_tier == SupportTier.A
    assert report.normalized_text_retention is not None
    assert report.normalized_text_retention >= 0.98
    assert report.validation.valid
    assert report.validation.package_version == "2.0"
    assert Path(report.immutable_original).is_file()
    assert Path(report.output).is_file()
    assert Path(report.preview).is_file()
    assert Path(report.structure_manifest).is_file()

    structure = json.loads(Path(report.structure_manifest).read_text())
    assert structure["source_sha256"] == report.source_sha256
    assert structure["output_sha256"] == report.output_sha256
    assert structure["sections"][0]["id"]
    assert structure["sections"][0]["xhtml_path"] == "text-1.xhtml"

    with zipfile.ZipFile(report.output) as archive:
        assert archive.infolist()[0].filename == "mimetype"
        assert archive.getinfo("mimetype").compress_type == zipfile.ZIP_STORED
        assert "META-INF/openreader-structure.json" in archive.namelist()
        assert "OEBPS/toc.ncx" in archive.namelist()

    second = PDFToEpubProcessor().convert(text_pdf, root)
    assert second.immutable_original == report.immutable_original


def test_converter_is_self_contained_without_poppler(text_pdf: Path, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    report = PDFToEpubProcessor().convert(text_pdf, tmp_path / "bundled-fallback")

    assert report.mode == ConversionMode.REFLOW
    assert report.validation.valid
    assert report.normalized_text_retention is not None
    assert report.normalized_text_retention >= 0.98


def test_reflow_removes_running_margins_and_preserves_semantics(tmp_path: Path) -> None:
    source = tmp_path / "styled-book.pdf"
    with pymupdf.open() as document:
        for page_number in range(1, 5):
            page = document.new_page(width=612, height=792)
            page.insert_text((72, 32), "Quarterly Reader Header", fontsize=9, fontname="helv")
            page.insert_text((72, 770), f"Page {page_number}", fontsize=9, fontname="helv")
            page.insert_text((72, 112), f"CHAPTER {page_number}", fontsize=20, fontname="hebo")
            page.insert_text(
                (72, 156),
                "A complete paragraph should remain readable after reconstruction.",
                fontsize=11,
                fontname="helv",
            )
            page.insert_text(
                (72, 180),
                "Disciplined execution matters.",
                fontsize=11,
                fontname="hebo",
            )
            page.insert_text(
                (72, 204),
                "Patient observation improves judgment.",
                fontsize=11,
                fontname="heit",
            )
        document.save(source)

    report = PDFToEpubProcessor().convert(source, tmp_path / "library")

    assert report.validation.valid
    assert any("Removed 8" in reason for reason in report.tier_reasons)
    with zipfile.ZipFile(report.output) as archive:
        content = archive.read("OEBPS/text-1.xhtml").decode("utf-8")
        nav = archive.read("OEBPS/nav.xhtml").decode("utf-8")
        ncx = archive.read("OEBPS/toc.ncx").decode("utf-8")

    assert "Quarterly Reader Header" not in content
    assert "Page 1" not in content
    assert "page-kicker" not in content
    assert "<strong>Disciplined execution matters.</strong>" in content
    assert "<em>Patient observation improves judgment.</em>" in content
    assert "CHAPTER 1" in nav
    assert "CHAPTER 4" in ncx
    assert nav.count("<li>") == 4


def test_reader_text_removes_xml_forbidden_controls() -> None:
    assert normalize_reader_text("before\x07after\x1f") == "beforeafter"


def test_validator_rejects_archive_without_epub_mimetype(tmp_path: Path) -> None:
    broken = tmp_path / "broken.epub"
    with zipfile.ZipFile(broken, "w") as archive:
        archive.writestr("hello.txt", "not an epub")
    report = validate_epub(broken)
    assert not report.valid
    assert any(issue.code.startswith("zip.") or issue.code.startswith("container.") for issue in report.issues)
