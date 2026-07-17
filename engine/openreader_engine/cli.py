from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from pathlib import Path

import uvicorn

from openreader_engine.app import create_app
from openreader_engine.conversion import PDFToEpubProcessor, validate_epub
from openreader_engine.devices import CrossPointAdapter, StockXteinkAdapter
from openreader_engine.utils import atomic_write


def _json(value: object) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, default=str))


def _make_adapter(kind: str, base_url: str):
    return StockXteinkAdapter(base_url) if kind == "stock" else CrossPointAdapter(base_url)


def _serve(args: argparse.Namespace) -> int:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", args.port))
    listener.listen(128)
    actual_port = int(listener.getsockname()[1])
    handshake = Path(args.handshake).expanduser().resolve() if args.handshake else None
    if handshake:
        atomic_write(
            handshake,
            json.dumps({"port": actual_port, "pid": os.getpid(), "listener": "127.0.0.1"}).encode("utf-8"),
        )
    app = create_app(token=args.token, data_root=Path(args.data_root) if args.data_root else None)
    config = uvicorn.Config(app, host="127.0.0.1", port=actual_port, log_level=args.log_level)
    server = uvicorn.Server(config)
    try:
        server.run(sockets=[listener])
    finally:
        if handshake:
            handshake.unlink(missing_ok=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="openreader", description="OpenReader private Milestone 0 engine")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="run the token-authenticated loopback control API")
    serve.add_argument("--port", type=int, default=0)
    serve.add_argument("--token", required=True)
    serve.add_argument("--handshake")
    serve.add_argument("--data-root")
    serve.add_argument("--log-level", default="warning")

    convert = subparsers.add_parser("convert", help="convert a PDF into an Xteink-profile EPUB")
    convert.add_argument("source")
    convert.add_argument("--output-dir", default="build/m0")

    validate = subparsers.add_parser("validate", help="validate an EPUB against the Xteink profile")
    validate.add_argument("epub")

    probe = subparsers.add_parser("probe", help="probe stock or CrossPoint firmware")
    probe.add_argument("adapter", choices=("stock", "crosspoint"))
    probe.add_argument("base_url")

    send = subparsers.add_parser("send", help="upload an EPUB and report transfer evidence")
    send.add_argument("adapter", choices=("stock", "crosspoint"))
    send.add_argument("base_url")
    send.add_argument("epub")
    send.add_argument("--folder", default="/Books")
    send.add_argument("--verify-readback", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        if args.command == "serve":
            raise SystemExit(_serve(args))
        if args.command == "convert":
            report = PDFToEpubProcessor().convert(Path(args.source), Path(args.output_dir), "xteink")
            _json(report.to_dict())
            return
        if args.command == "validate":
            report = validate_epub(Path(args.epub), "xteink")
            _json(report.to_dict())
            raise SystemExit(0 if report.valid else 1)
        if args.command == "probe":
            with _make_adapter(args.adapter, args.base_url) as adapter:
                _json(adapter.probe())
            return
        if args.command == "send":
            with _make_adapter(args.adapter, args.base_url) as adapter:
                result = adapter.upload(Path(args.epub), args.folder, args.verify_readback)
            _json(result.to_dict())
            return
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    except Exception as error:
        print(f"openreader: {error}", file=sys.stderr)
        raise SystemExit(1) from error
