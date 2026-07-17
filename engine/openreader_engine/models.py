from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class SupportTier(StrEnum):
    A = "A"
    B = "B"
    C = "C"


class ConversionMode(StrEnum):
    REFLOW = "reflow"
    PAGE_IMAGES = "page_images"


class EvidenceLevel(StrEnum):
    VERIFIED_READBACK = "verified_readback"
    LISTED_ON_DEVICE = "listed_on_device"
    UPLOAD_ACKNOWLEDGED = "upload_acknowledged"
    SENT_UNVERIFIED = "sent_unverified"
    STAGED = "staged"
    UNKNOWN = "unknown"
    FAILED = "failed"


@dataclass(frozen=True)
class StructureSection:
    id: str
    parent_id: str | None
    heading: str
    order: int
    source_page_start: int
    source_page_end: int
    source_text_start: int
    source_text_end: int
    xhtml_path: str
    fragment_id: str
    content_fingerprint: str


@dataclass(frozen=True)
class ValidationIssue:
    level: str
    code: str
    message: str


@dataclass
class ValidationReport:
    file: str
    valid: bool
    profile: str
    package_version: str | None
    chapters: int
    images: int
    issues: list[ValidationIssue] = field(default_factory=list)
    epubcheck_used: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ConversionReport:
    source: str
    immutable_original: str
    output: str
    preview: str
    structure_manifest: str
    source_sha256: str
    output_sha256: str
    pages: int
    mode: ConversionMode
    support_tier: SupportTier
    tier_reasons: list[str]
    source_characters: int
    output_characters: int
    normalized_text_retention: float | None
    validation: ValidationReport

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DeviceFile:
    name: str
    path: str
    size: int | None
    is_directory: bool
    is_epub: bool


@dataclass(frozen=True)
class AdapterCapabilities:
    list_content: bool
    upload: bool
    delete: bool
    replace: bool
    rename: bool
    move: bool
    readback: bool
    reports_size: bool


@dataclass
class TransferResult:
    adapter: str
    destination: str
    evidence: EvidenceLevel
    expected_sha256: str
    observed_sha256: str | None
    expected_size: int
    observed_size: int | None
    observations: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def path_string(path: Path) -> str:
    return str(path.expanduser().resolve())
