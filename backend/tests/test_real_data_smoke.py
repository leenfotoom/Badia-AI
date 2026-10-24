"""Smoke checks against the immutable data shipped with the MVP."""

import sys
from pathlib import Path

from fastapi.testclient import TestClient


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.main import app


client = TestClient(app)


def test_real_snapshot_contract() -> None:
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["data_ready"] is True
    assert health.json()["available_horizons"] == [16, 32]

    for horizon in (16, 32):
        cells = client.get(
            "/api/cells", params={"horizon": horizon, "format": "geojson"}
        )
        assert cells.status_code == 200
        payload = cells.json()
        assert payload["is_live"] is False
        assert payload["snapshot_date"] == "2025-12-02"
        assert len(payload["features"]) == 968
        assert payload["features"][0]["geometry"]["type"] == "Polygon"
        published = [
            feature["properties"]["risk_score"]
            for feature in payload["features"]
            if feature["properties"]["risk_score"] is not None
        ]
        assert published
        assert min(published) >= 0
        assert max(published) <= 100

        summary = client.get("/api/areas", params={"horizon": horizon})
        assert summary.status_code == 200
        assert summary.json()["summary"]["total_cells"] == 968


def test_real_science_and_detail_contract() -> None:
    detail = client.get("/api/cells/11%2C325", params={"horizon": 16})
    assert detail.status_code == 200
    assert detail.json()["cell_id"] == "11,325"

    metrics = client.get("/api/metrics").json()
    assert metrics["horizons"]["16"]["validation"]["model_mae"] == 0.005072
    assert metrics["horizons"]["32"]["test"]["baseline_mae"] == 0.006193

    metadata = client.get("/api/metadata").json()
    assert metadata["is_live"] is False
    assert "not a field-verified" in metadata["disclaimer"]
