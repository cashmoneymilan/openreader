#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from openreader_engine.conversion import validate_epub


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative(path: Path, root: Path) -> str:
    return str(path.relative_to(root))


def audit(root: Path) -> dict:
    library = root / "Library"
    queue = root / "Queue" / "Next Reads"
    pdfs = sorted(library.rglob("*.pdf"))
    epubs = sorted(library.rglob("*.epub"))
    queue_epubs = sorted(queue.glob("*.epub")) if queue.is_dir() else []

    pdf_by_stem = {path.stem.casefold(): path for path in pdfs}
    epub_by_stem = {path.stem.casefold(): path for path in epubs}
    orphan_pdfs = [relative(path, root) for key, path in pdf_by_stem.items() if key not in epub_by_stem]
    orphan_epubs = [relative(path, root) for key, path in epub_by_stem.items() if key not in pdf_by_stem]

    validations = []
    for path in epubs:
        result = validate_epub(path, profile="xteink")
        validations.append(
            {
                "file": relative(path, root),
                "valid": result.valid,
                "package_version": result.package_version,
                "chapters": result.chapters,
                "images": result.images,
                "issues": [issue.model_dump() for issue in result.issues],
            }
        )

    all_pdfs = sorted(root.rglob("*.pdf"))
    hashes: dict[str, list[Path]] = defaultdict(list)
    for path in all_pdfs:
        hashes[sha256(path)].append(path)
    duplicates = [
        {"sha256": digest, "files": [relative(path, root) for path in paths]}
        for digest, paths in hashes.items()
        if len(paths) > 1
    ]

    canonical_inodes = {path.stat().st_ino: path for path in epubs}
    queue_rows = []
    for path in queue_epubs:
        canonical = canonical_inodes.get(path.stat().st_ino)
        queue_rows.append(
            {
                "file": relative(path, root),
                "canonical": relative(canonical, root) if canonical else None,
                "hard_linked": canonical is not None,
                "valid": validate_epub(path, profile="xteink").valid,
            }
        )

    issues = []
    issues.extend(f"PDF has no matching EPUB: {path}" for path in orphan_pdfs)
    issues.extend(f"EPUB has no matching PDF: {path}" for path in orphan_epubs)
    issues.extend(f"Invalid EPUB: {row['file']}" for row in validations if not row["valid"])
    issues.extend(f"Queue item is not linked to its canonical EPUB: {row['file']}" for row in queue_rows if not row["hard_linked"])
    issues.extend(f"Invalid queue EPUB: {row['file']}" for row in queue_rows if not row["valid"])

    return {
        "schema": "openreader.library-audit.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "root": str(root),
        "counts": {
            "canonical_pdfs": len(pdfs),
            "canonical_epubs": len(epubs),
            "queue_items": len(queue_epubs),
            "duplicate_pdf_groups": len(duplicates),
            "issues": len(issues),
        },
        "orphan_pdfs": orphan_pdfs,
        "orphan_epubs": orphan_epubs,
        "duplicates": duplicates,
        "epub_validation": validations,
        "queue": queue_rows,
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit an OpenReader books folder without changing it.")
    parser.add_argument("root", type=Path, help="Books folder containing Library and Queue")
    parser.add_argument("--output", type=Path, help="Optional JSON report path")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when issues are found")
    args = parser.parse_args()

    report = audit(args.root.expanduser().resolve())
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.expanduser().resolve().write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 1 if args.strict and report["issues"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
