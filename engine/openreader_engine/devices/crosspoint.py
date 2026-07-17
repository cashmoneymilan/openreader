from __future__ import annotations

from pathlib import Path

import httpx

from openreader_engine.devices.base import DeviceAdapter, device_path
from openreader_engine.models import AdapterCapabilities, DeviceFile, EvidenceLevel, TransferResult
from openreader_engine.utils import sha256_bytes, sha256_file


class CrossPointAdapter(DeviceAdapter):
    name = "crosspoint"
    capabilities = AdapterCapabilities(
        list_content=True,
        upload=True,
        delete=True,
        replace=True,
        rename=True,
        move=True,
        readback=True,
        reports_size=True,
    )

    def __init__(self, base_url: str = "http://crosspoint.local", client: httpx.Client | None = None) -> None:
        super().__init__(base_url, client)

    def probe(self) -> dict:
        response = self.client.get(f"{self.base_url}/api/status")
        response.raise_for_status()
        payload = response.json()
        return {"adapter": self.name, "reachable": True, "capabilities": self.capabilities.__dict__, "status": payload}

    def list_content(self, folder: str = "/") -> list[DeviceFile]:
        normalized_folder = device_path(folder)
        response = self.client.get(f"{self.base_url}/api/files", params={"path": normalized_folder})
        response.raise_for_status()
        output: list[DeviceFile] = []
        for item in response.json():
            name = str(item.get("name", ""))
            if not name:
                continue
            output.append(
                DeviceFile(
                    name=name,
                    path=device_path(normalized_folder, name),
                    size=int(item.get("size", 0)),
                    is_directory=bool(item.get("isDirectory", False)),
                    is_epub=bool(item.get("isEpub", False)),
                )
            )
        return output

    def upload(self, epub: Path, folder: str = "/Books", verify_readback: bool = False) -> TransferResult:
        epub = epub.expanduser().resolve()
        data = epub.read_bytes()
        expected_hash = sha256_file(epub)
        normalized_folder = device_path(folder)
        destination = device_path(normalized_folder, epub.name)
        response = self.client.post(
            f"{self.base_url}/upload",
            params={"path": normalized_folder},
            files={"file": (epub.name, data, "application/epub+zip")},
        )
        response.raise_for_status()
        evidence = EvidenceLevel.UPLOAD_ACKNOWLEDGED
        observations = ["CrossPoint acknowledged the multipart upload"]
        observed_size: int | None = None
        observed_hash: str | None = None

        matching = next((item for item in self.list_content(normalized_folder) if item.name == epub.name and not item.is_directory), None)
        if matching and matching.size == len(data):
            evidence = EvidenceLevel.LISTED_ON_DEVICE
            observed_size = matching.size
            observations.append("Device listing matched path, filename, and byte size")
        elif matching:
            observed_size = matching.size
            observations.append(f"Device listed the filename with unexpected size {matching.size}")
        else:
            observations.append("Upload completed but the file was absent from the next listing")

        if verify_readback and matching:
            readback = self.client.get(f"{self.base_url}/download", params={"path": destination})
            readback.raise_for_status()
            observed_hash = sha256_bytes(readback.content)
            if observed_hash == expected_hash:
                evidence = EvidenceLevel.VERIFIED_READBACK
                observations.append("Downloaded bytes matched the expected SHA-256")
            else:
                evidence = EvidenceLevel.FAILED
                observations.append("Downloaded bytes did not match the expected SHA-256")

        return TransferResult(
            adapter=self.name,
            destination=destination,
            evidence=evidence,
            expected_sha256=expected_hash,
            observed_sha256=observed_hash,
            expected_size=len(data),
            observed_size=observed_size,
            observations=observations,
        )

    def delete(self, path: str) -> None:
        response = self.client.post(f"{self.base_url}/delete", data={"path": device_path(path)})
        response.raise_for_status()

    def rename(self, path: str, new_name: str) -> None:
        response = self.client.post(f"{self.base_url}/rename", data={"path": device_path(path), "name": new_name})
        response.raise_for_status()

    def move(self, path: str, destination: str) -> None:
        response = self.client.post(
            f"{self.base_url}/move",
            data={"path": device_path(path), "dest": device_path(destination)},
        )
        response.raise_for_status()
