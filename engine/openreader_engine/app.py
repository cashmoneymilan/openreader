from __future__ import annotations

import os
import uuid
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from openreader_engine import __version__
from openreader_engine.conversion import PDFToEpubProcessor, validate_epub
from openreader_engine.devices import CrossPointAdapter, StockXteinkAdapter
from openreader_engine.utils import atomic_write, safe_filename


class DeviceProbeRequest(BaseModel):
    adapter: str = Field(pattern="^(stock|crosspoint)$")
    base_url: str


class DeviceSendRequest(BaseModel):
    adapter: str = Field(pattern="^(stock|crosspoint)$")
    base_url: str
    report_id: str
    folder: str = "/Books"
    verify_readback: bool = False


def _default_data_root() -> Path:
    return Path.home() / "Library" / "Application Support" / "OpenReader" / "M0"


def _adapter(kind: str, base_url: str):
    if kind == "stock":
        return StockXteinkAdapter(base_url)
    if kind == "crosspoint":
        return CrossPointAdapter(base_url)
    raise ValueError(f"Unknown adapter: {kind}")


def create_app(token: str | None = None, data_root: Path | None = None) -> FastAPI:
    expected_token = token or os.environ.get("OPENREADER_CONTROL_TOKEN", "")
    root = (data_root or _default_data_root()).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    reports: dict[str, dict] = {}
    app = FastAPI(title="OpenReader Engine", version=__version__, docs_url=None, redoc_url=None)

    @app.middleware("http")
    async def authenticate(request: Request, call_next):
        if request.url.path.startswith("/v1/"):
            supplied = request.headers.get("authorization", "")
            if not expected_token or supplied != f"Bearer {expected_token}":
                return JSONResponse({"detail": "Invalid or missing local control token"}, status_code=401)
        return await call_next(request)

    @app.get("/health")
    async def health():
        return {"status": "ok", "version": __version__, "listener": "loopback-control"}

    @app.post("/v1/convert")
    async def convert(file: UploadFile):
        filename = safe_filename(file.filename or "document.pdf")
        if not filename.casefold().endswith(".pdf"):
            raise HTTPException(415, "Milestone 0 accepts PDF uploads")
        source = root / "uploads" / f"{uuid.uuid4()}-{filename}"
        atomic_write(source, await file.read())
        try:
            report = await run_in_threadpool(PDFToEpubProcessor().convert, source, root, "xteink")
        except Exception as error:
            raise HTTPException(422, str(error)) from error
        report_id = report.output_sha256[:20]
        reports[report_id] = report.to_dict()
        return {"report_id": report_id, "report": reports[report_id]}

    @app.post("/v1/validate")
    async def validate(file: UploadFile):
        filename = safe_filename(file.filename or "publication.epub")
        if not filename.casefold().endswith(".epub"):
            raise HTTPException(415, "Expected an EPUB upload")
        target = root / "validation" / f"{uuid.uuid4()}-{filename}"
        atomic_write(target, await file.read())
        report = await run_in_threadpool(validate_epub, target, "xteink")
        return report.to_dict()

    @app.get("/v1/reports")
    async def list_reports():
        return [{"report_id": report_id, "report": report} for report_id, report in reports.items()]

    @app.post("/v1/devices/probe")
    async def probe_device(payload: DeviceProbeRequest):
        try:
            with _adapter(payload.adapter, payload.base_url) as adapter:
                return await run_in_threadpool(adapter.probe)
        except Exception as error:
            raise HTTPException(502, f"Device probe failed: {error}") from error

    @app.post("/v1/devices/send")
    async def send_to_device(payload: DeviceSendRequest):
        report = reports.get(payload.report_id)
        if not report:
            raise HTTPException(404, "Conversion report is not available in this engine session")
        epub = Path(report["output"])
        if not epub.is_file():
            raise HTTPException(410, "The derivative is no longer available")
        try:
            with _adapter(payload.adapter, payload.base_url) as adapter:
                result = await run_in_threadpool(adapter.upload, epub, payload.folder, payload.verify_readback)
            return result.to_dict()
        except Exception as error:
            raise HTTPException(502, f"Device transfer failed: {error}") from error

    return app


app = create_app()
