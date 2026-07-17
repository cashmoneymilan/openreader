from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path


PUNCTUATION_TRANSLATION = str.maketrans(
    {
        "“": '"',
        "”": '"',
        "„": '"',
        "‟": '"',
        "‘": "'",
        "’": "'",
        "‚": "'",
        "‛": "'",
        "–": "-",
        "—": "-",
        "‑": "-",
        "…": "...",
        "\u00a0": " ",
        "\u00ad": "",
    }
)


def normalize_reader_text(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value).translate(PUNCTUATION_TRANSLATION)
    return "".join(
        character
        for character in normalized
        if character in "\t\n\r"
        or (
            ord(character) >= 0x20
            and not 0x7F <= ord(character) <= 0x9F
            and not 0xD800 <= ord(character) <= 0xDFFF
            and ord(character) <= 0x10FFFF
        )
    )


def normalize_for_comparison(value: str) -> str:
    return re.sub(r"\s+", "", normalize_reader_text(value)).casefold()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def require_command(name: str) -> str:
    command = shutil.which(name)
    if not command:
        raise RuntimeError(f"Required command is unavailable: {name}")
    return command


def run_command(args: list[str], *, text: bool = True) -> subprocess.CompletedProcess[str] | subprocess.CompletedProcess[bytes]:
    return subprocess.run(args, check=True, capture_output=True, text=text)


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_bytes(data)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def safe_filename(value: str) -> str:
    cleaned = re.sub(r"[\x00-\x1f\x7f/\\:*?\"<>|]", " ", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned[:180] or "Untitled"
