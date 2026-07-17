from __future__ import annotations

import json
import zipfile
from pathlib import Path

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


def test_reader_text_removes_xml_forbidden_controls() -> None:
    assert normalize_reader_text("before\x07after\x1f") == "beforeafter"


def test_validator_rejects_archive_without_epub_mimetype(tmp_path: Path) -> None:
    broken = tmp_path / "broken.epub"
    with zipfile.ZipFile(broken, "w") as archive:
        archive.writestr("hello.txt", "not an epub")
    report = validate_epub(broken)
    assert not report.valid
    assert any(issue.code.startswith("zip.") or issue.code.startswith("container.") for issue in report.issues)
