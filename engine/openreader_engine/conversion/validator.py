from __future__ import annotations

import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path, PurePosixPath

from openreader_engine.models import ValidationIssue, ValidationReport

XTEINK_MAX_IMAGE_BYTES = 2 * 1024 * 1024
XTEINK_MAX_IMAGE_DIMENSION = 1000


def _issue(issues: list[ValidationIssue], level: str, code: str, message: str) -> None:
    issues.append(ValidationIssue(level=level, code=code, message=message))


def _resolve(base: str, target: str) -> str:
    clean = target.split("#", 1)[0].split("?", 1)[0]
    return str(PurePosixPath(base).parent.joinpath(clean))


def _jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        return None
    offset = 2
    while offset + 9 < len(data):
        if data[offset] != 0xFF:
            offset += 1
            continue
        marker = data[offset + 1]
        offset += 2
        if marker in (0xD9, 0xDA) or offset + 2 > len(data):
            break
        length = int.from_bytes(data[offset : offset + 2], "big")
        if length < 2 or offset + length > len(data):
            break
        if marker in {*range(0xC0, 0xC4), *range(0xC5, 0xC8), *range(0xC9, 0xCC), *range(0xCD, 0xD0)}:
            height = int.from_bytes(data[offset + 3 : offset + 5], "big")
            width = int.from_bytes(data[offset + 5 : offset + 7], "big")
            return width, height
        offset += length
    return None


def validate_epub(path: Path, profile: str = "xteink") -> ValidationReport:
    epub_path = path.expanduser().resolve()
    issues: list[ValidationIssue] = []
    chapters = 0
    images = 0
    package_version: str | None = None

    try:
        archive = zipfile.ZipFile(epub_path)
    except (OSError, zipfile.BadZipFile) as error:
        return ValidationReport(str(epub_path), False, profile, None, 0, 0, [ValidationIssue("error", "zip.unreadable", str(error))])

    with archive:
        entries = set(archive.namelist())
        if not archive.infolist() or archive.infolist()[0].filename != "mimetype":
            _issue(issues, "error", "zip.mimetype_order", "mimetype must be the first ZIP entry")
        if "mimetype" not in entries or archive.read("mimetype") != b"application/epub+zip":
            _issue(issues, "error", "zip.mimetype", "mimetype is missing or incorrect")
        elif archive.getinfo("mimetype").compress_type != zipfile.ZIP_STORED:
            _issue(issues, "error", "zip.mimetype_compression", "mimetype must be stored without compression")

        container_path = "META-INF/container.xml"
        if container_path not in entries:
            _issue(issues, "error", "container.missing", "META-INF/container.xml is missing")
            return ValidationReport(str(epub_path), False, profile, None, chapters, images, issues)

        try:
            container = ET.fromstring(archive.read(container_path))
            rootfile = container.find(".//{*}rootfile")
            opf_path = rootfile.attrib.get("full-path", "") if rootfile is not None else ""
        except ET.ParseError as error:
            _issue(issues, "error", "container.xml", f"container.xml is invalid: {error}")
            opf_path = ""

        if not opf_path or opf_path not in entries:
            _issue(issues, "error", "opf.missing", f"Package document is missing: {opf_path or '(not declared)'}")
            return ValidationReport(str(epub_path), False, profile, None, chapters, images, issues)

        try:
            opf = ET.fromstring(archive.read(opf_path))
        except ET.ParseError as error:
            _issue(issues, "error", "opf.xml", f"Package document is invalid: {error}")
            return ValidationReport(str(epub_path), False, profile, None, chapters, images, issues)

        package_version = opf.attrib.get("version")
        if profile == "xteink" and package_version != "2.0":
            _issue(issues, "warning", "profile.package_version", f"Xteink profile expects EPUB 2.0; found {package_version or 'unknown'}")

        manifest: dict[str, tuple[str, str]] = {}
        for item in opf.findall(".//{*}manifest/{*}item"):
            item_id = item.attrib.get("id", "")
            href = item.attrib.get("href", "")
            media_type = item.attrib.get("media-type", "")
            if not item_id or not href:
                _issue(issues, "error", "manifest.item", "Manifest item is missing id or href")
                continue
            target = _resolve(opf_path, href)
            manifest[item_id] = (target, media_type)
            if target not in entries:
                _issue(issues, "error", "manifest.target", f"Manifest target is missing: {target}")
            if media_type == "application/xhtml+xml" and not target.endswith("nav.xhtml"):
                chapters += 1
            if media_type.startswith("image/"):
                images += 1

        ncx_items = [(item_id, target) for item_id, (target, media) in manifest.items() if media == "application/x-dtbncx+xml"]
        if not ncx_items:
            _issue(issues, "error", "navigation.ncx", "EPUB 2 NCX navigation is missing")
        for _, ncx_path in ncx_items:
            if ncx_path not in entries:
                continue
            try:
                ncx = ET.fromstring(archive.read(ncx_path))
                nav_points = ncx.findall(".//{*}navPoint")
                if not nav_points:
                    _issue(issues, "error", "navigation.empty", "NCX contains no navigation points")
                for content in ncx.findall(".//{*}content"):
                    src = content.attrib.get("src", "")
                    if src and _resolve(ncx_path, src) not in entries:
                        _issue(issues, "error", "navigation.target", f"Broken NCX reference: {src}")
            except ET.ParseError as error:
                _issue(issues, "error", "navigation.xml", f"NCX is invalid: {error}")

        spine = opf.find(".//{*}spine")
        if spine is None:
            _issue(issues, "error", "spine.missing", "Package spine is missing")
        else:
            toc = spine.attrib.get("toc")
            if toc and toc not in manifest:
                _issue(issues, "error", "spine.toc", f"Spine references unknown NCX id: {toc}")
            for itemref in spine.findall("{*}itemref"):
                idref = itemref.attrib.get("idref", "")
                if idref not in manifest:
                    _issue(issues, "error", "spine.itemref", f"Spine references missing manifest id: {idref}")

        for _, (target, media_type) in manifest.items():
            if target not in entries:
                continue
            if media_type == "application/xhtml+xml":
                data = archive.read(target)
                lowered = data.lower()
                if any(marker in lowered for marker in (b"<script", b"<svg", b"<video", b"<audio", b"@font-face")):
                    _issue(issues, "error", "profile.embedded_feature", f"Xteink-unsafe embedded feature in {target}")
                try:
                    ET.fromstring(data)
                except ET.ParseError as error:
                    _issue(issues, "error", "xhtml.xml", f"Invalid XHTML in {target}: {error}")
            if media_type == "image/jpeg" and profile == "xteink":
                data = archive.read(target)
                if len(data) >= XTEINK_MAX_IMAGE_BYTES:
                    _issue(issues, "error", "profile.image_bytes", f"JPEG exceeds 2 MB: {target}")
                dimensions = _jpeg_dimensions(data)
                if dimensions and max(dimensions) > XTEINK_MAX_IMAGE_DIMENSION:
                    _issue(issues, "error", "profile.image_dimensions", f"JPEG exceeds 1000 px: {target} ({dimensions[0]}x{dimensions[1]})")

    epubcheck_used = False
    epubcheck = shutil.which("epubcheck")
    if epubcheck:
        epubcheck_used = True
        completed = subprocess.run([epubcheck, str(epub_path)], capture_output=True, text=True)
        if completed.returncode:
            detail = (completed.stderr or completed.stdout).strip().splitlines()[-1:]
            _issue(issues, "error", "epubcheck.failed", detail[0] if detail else "EPUBCheck failed")

    valid = not any(issue.level == "error" for issue in issues)
    return ValidationReport(str(epub_path), valid, profile, package_version, chapters, images, issues, epubcheck_used)
