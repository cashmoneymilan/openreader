from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from openreader_engine.app import create_app


def test_control_api_requires_token_and_runs_conversion(text_pdf: Path, tmp_path: Path) -> None:
    client = TestClient(create_app(token="proof-token", data_root=tmp_path / "data"))
    with text_pdf.open("rb") as handle:
        unauthorized = client.post("/v1/convert", files={"file": (text_pdf.name, handle, "application/pdf")})
    assert unauthorized.status_code == 401

    with text_pdf.open("rb") as handle:
        converted = client.post(
            "/v1/convert",
            headers={"Authorization": "Bearer proof-token"},
            files={"file": (text_pdf.name, handle, "application/pdf")},
        )
    assert converted.status_code == 200, converted.text
    payload = converted.json()
    assert payload["report"]["validation"]["valid"] is True
    assert payload["report"]["support_tier"] == "A"
    assert Path(payload["report"]["output"]).is_file()

    reports = client.get("/v1/reports", headers={"Authorization": "Bearer proof-token"})
    assert reports.status_code == 200
    assert reports.json()[0]["report_id"] == payload["report_id"]
