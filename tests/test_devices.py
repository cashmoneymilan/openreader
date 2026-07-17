from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import parse_qs

import httpx

from openreader_engine.devices import CrossPointAdapter, StockXteinkAdapter
from openreader_engine.models import EvidenceLevel


def _multipart(request: httpx.Request) -> list[dict[str, object]]:
    content_type = request.headers.get("content-type", "")
    match = re.search(r"boundary=([^;]+)", content_type)
    assert match, content_type
    boundary = ("--" + match.group(1)).encode()
    output: list[dict[str, object]] = []
    for raw_part in request.content.split(boundary)[1:-1]:
        part = raw_part.strip(b"\r\n")
        headers, body = part.split(b"\r\n\r\n", 1)
        disposition = re.search(rb'content-disposition:\s*form-data;\s*name="([^"]+)"(?:;\s*filename="([^"]*)")?', headers, re.I)
        assert disposition
        output.append(
            {
                "name": disposition.group(1).decode(),
                "filename": disposition.group(2).decode() if disposition.group(2) else None,
                "body": body.rstrip(b"\r\n"),
            }
        )
    return output


def test_crosspoint_upload_listing_readback_replace_and_delete(tmp_path: Path) -> None:
    storage: dict[str, bytes] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/api/status":
            return httpx.Response(200, json={"version": "m0", "ip": "127.0.0.1", "mode": "AP", "rssi": 0, "freeHeap": 1, "uptime": 1, "device": "X4"})
        if request.method == "GET" and request.url.path == "/api/files":
            folder = request.url.params.get("path", "/").rstrip("/") or "/"
            prefix = folder.rstrip("/") + "/"
            files = [
                {"name": path.removeprefix(prefix), "size": len(data), "isDirectory": False, "isEpub": path.endswith(".epub")}
                for path, data in storage.items()
                if path.startswith(prefix) and "/" not in path.removeprefix(prefix)
            ]
            return httpx.Response(200, json=files)
        if request.method == "POST" and request.url.path == "/upload":
            part = next(value for value in _multipart(request) if value["name"] == "file")
            folder = request.url.params.get("path", "/").rstrip("/")
            storage[f"{folder}/{part['filename']}"] = part["body"]
            return httpx.Response(200, text="File uploaded successfully")
        if request.method == "GET" and request.url.path == "/download":
            return httpx.Response(200, content=storage[request.url.params["path"]])
        if request.method == "POST" and request.url.path == "/delete":
            path = parse_qs(request.content.decode())["path"][0]
            storage.pop(path, None)
            return httpx.Response(200, text="Deleted")
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = CrossPointAdapter("http://crosspoint.test", client)
    epub = tmp_path / "proof.epub"
    epub.write_bytes(b"first-version")

    result = adapter.upload(epub, "/Books", verify_readback=True)
    assert result.evidence == EvidenceLevel.VERIFIED_READBACK
    assert adapter.probe()["status"]["device"] == "X4"
    assert adapter.list_content("/Books")[0].size == len(b"first-version")

    epub.write_bytes(b"replacement-version")
    replacement = adapter.upload(epub, "/Books", verify_readback=True)
    assert replacement.evidence == EvidenceLevel.VERIFIED_READBACK
    assert replacement.observed_size == len(b"replacement-version")

    adapter.delete("/Books/proof.epub")
    assert adapter.list_content("/Books") == []


def test_stock_upload_listing_replace_and_delete_use_acknowledged_evidence(tmp_path: Path) -> None:
    storage: dict[str, bytes] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/list":
            folder = request.url.params.get("dir", "/").rstrip("/")
            prefix = folder + "/"
            entries = [
                {"name": path.removeprefix(prefix), "type": "file"}
                for path in storage
                if path.startswith(prefix) and "/" not in path.removeprefix(prefix)
            ]
            return httpx.Response(200, json=entries)
        if request.method == "POST" and request.url.path == "/edit":
            part = next(value for value in _multipart(request) if value["name"] == "data")
            storage[str(part["filename"])] = part["body"]
            return httpx.Response(200, text="OK")
        if request.method == "DELETE" and request.url.path == "/edit":
            part = next(value for value in _multipart(request) if value["name"] == "path")
            storage.pop(part["body"].decode(), None)
            return httpx.Response(200, text="OK")
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = StockXteinkAdapter("http://stock.test", client)
    epub = tmp_path / "proof.epub"
    epub.write_bytes(b"stock-one")

    first = adapter.upload(epub, "/Books")
    assert first.evidence == EvidenceLevel.UPLOAD_ACKNOWLEDGED
    assert adapter.probe()["reachable"]
    assert adapter.list_content("/Books")[0].size is None

    epub.write_bytes(b"stock-replacement")
    replacement = adapter.upload(epub, "/Books")
    assert replacement.evidence == EvidenceLevel.UPLOAD_ACKNOWLEDGED
    assert storage["/Books/proof.epub"] == b"stock-replacement"

    adapter.delete("/Books/proof.epub")
    assert adapter.list_content("/Books") == []
