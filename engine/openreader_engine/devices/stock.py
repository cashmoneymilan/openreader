from __future__ import annotations

from pathlib import Path

import httpx

from openreader_engine.devices.base import DeviceAdapter, device_path
from openreader_engine.models import AdapterCapabilities, DeviceFile, EvidenceLevel, TransferResult
from openreader_engine.utils import sha256_file


class StockXteinkAdapter(DeviceAdapter):
    name = "xteink-stock"
    capabilities = AdapterCapabilities(
        list_content=True,
        upload=True,
        delete=True,
        replace=True,
        rename=False,
        move=False,
        readback=False,
        reports_size=False,
    )

    def __init__(self, base_url: str = "http://192.168.3.3", client: httpx.Client | None = None) -> None:
        super().__init__(base_url, client)

    def probe(self) -> dict:
        response = self.client.get(f"{self.base_url}/list", params={"dir": "/"})
        response.raise_for_status()
        return {
            "adapter": self.name,
            "reachable": True,
            "capabilities": self.capabilities.__dict__,
            "status": {"endpoint": "/list", "entries": len(response.json())},
        }

    def list_content(self, folder: str = "/") -> list[DeviceFile]:
        normalized_folder = device_path(folder)
        response = self.client.get(f"{self.base_url}/list", params={"dir": normalized_folder})
        response.raise_for_status()
        output: list[DeviceFile] = []
        for item in response.json():
            name = str(item.get("name", ""))
            item_type = str(item.get("type", ""))
            if not name:
                continue
            is_directory = item_type == "dir"
            output.append(
                DeviceFile(
                    name=name,
                    path=device_path(normalized_folder, name),
                    size=None,
                    is_directory=is_directory,
                    is_epub=not is_directory and name.casefold().endswith(".epub"),
                )
            )
        return output

    def upload(self, epub: Path, folder: str = "/Books", verify_readback: bool = False) -> TransferResult:
        if verify_readback:
            raise ValueError("Stock Xteink firmware does not expose file readback")
        epub = epub.expanduser().resolve()
        data = epub.read_bytes()
        normalized_folder = device_path(folder)
        destination = device_path(normalized_folder, epub.name)
        response = self.client.post(
            f"{self.base_url}/edit",
            files={"data": (destination, data, "application/epub+zip")},
        )
        response.raise_for_status()
        observations = ["Stock firmware acknowledged the multipart upload"]
        listing = self.list_content(normalized_folder)
        if any(item.name == epub.name and not item.is_directory for item in listing):
            observations.append("A subsequent stock listing contained the filename; stock firmware does not report size")
        else:
            observations.append("Stock listing did not contain the filename after upload")
        return TransferResult(
            adapter=self.name,
            destination=destination,
            evidence=EvidenceLevel.UPLOAD_ACKNOWLEDGED,
            expected_sha256=sha256_file(epub),
            observed_sha256=None,
            expected_size=len(data),
            observed_size=None,
            observations=observations,
        )

    def delete(self, path: str) -> None:
        response = self.client.request("DELETE", f"{self.base_url}/edit", files={"path": (None, device_path(path))})
        response.raise_for_status()

    def create_folder(self, path: str) -> None:
        normalized = device_path(path).rstrip("/") + "/"
        response = self.client.request("PUT", f"{self.base_url}/edit", files={"path": (None, normalized)})
        if response.status_code != 409:
            response.raise_for_status()
