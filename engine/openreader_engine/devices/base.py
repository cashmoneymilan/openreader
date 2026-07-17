from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path, PurePosixPath

import httpx

from openreader_engine.models import AdapterCapabilities, DeviceFile, TransferResult


def device_path(folder: str, name: str | None = None) -> str:
    clean_folder = "/" + folder.strip("/") if folder.strip("/") else "/"
    if name is None:
        return clean_folder
    return str(PurePosixPath(clean_folder) / name)


class DeviceAdapter(ABC):
    name: str
    capabilities: AdapterCapabilities

    def __init__(self, base_url: str, client: httpx.Client | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self._owns_client = client is None
        self.client = client or httpx.Client(timeout=httpx.Timeout(120, connect=4))

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self) -> DeviceAdapter:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @abstractmethod
    def probe(self) -> dict:
        raise NotImplementedError

    @abstractmethod
    def list_content(self, folder: str = "/") -> list[DeviceFile]:
        raise NotImplementedError

    @abstractmethod
    def upload(self, epub: Path, folder: str = "/Books", verify_readback: bool = False) -> TransferResult:
        raise NotImplementedError

    @abstractmethod
    def delete(self, path: str) -> None:
        raise NotImplementedError
