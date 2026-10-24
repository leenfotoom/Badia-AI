from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.main import create_app  # noqa: E402
from app.daily.store import Paths as DailyPaths  # noqa: E402


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _client(tmp_path: Path) -> TestClient:
    cells_16 = {
        "snapshot_date": "2025-12-19",
        "snapshot_label": "Historical / latest available demo",
        "cells": [
            {
                "cell_id": "JOR,001",
                "lat": 31.95,
                "lon": 35.91,
                "predicted_anomaly": -0.012,
                "risk_score": 82.5,
                "risk_level": "High",
                "top_factors": ["current vegetation anomaly", "90-day rainfall"],
                "data_quality": "Good",
                "horizon_days": 16,
            },
            {
                "cell_id": "JOR-002",
                "lat": 30.2,
                "lon": 36.4,
                "predicted_anomaly": None,
                "risk_score": None,
                "risk_level": "N/A",
                "top_factors": [],
                "data_quality": "Limited",
                "horizon_days": 16,
            },
        ],
    }
    cells_32 = {
        "type": "FeatureCollection",
        "snapshot_date": "2025-12-19",
        "features": [
            {
                "type": "Feature",
                "id": "JOR,001",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [35.8, 31.8],
                            [36.0, 31.8],
                            [36.0, 32.0],
                            [35.8, 32.0],
                            [35.8, 31.8],
                        ]
                    ],
                },
                "properties": {
                    "lat": 31.9,
                    "lon": 35.9,
                    "predicted_anomaly": -0.016,
                    "risk_score": 91.0,
                    "level": "high",
                    "top_factors": ["current vegetation anomaly"],
                    "data_quality": {"status": "Good"},
                    "horizon_days": 32,
                },
            }
        ],
    }
    _write_json(tmp_path / "cells_16.json", cells_16)
    _write_json(tmp_path / "cells_32.geojson", cells_32)
    _write_json(tmp_path / "metadata.json", {"project": "BADIA AI", "year": 2025})
    _write_json(tmp_path / "metrics.json", {"metric": "MAE", "verified": True})
    _write_json(
        tmp_path / "national_summary.json",
        {"scope": "Jordan", "headline": "Saved demo summary"},
    )
    daily_paths = DailyPaths(tmp_path / "daily-data", tmp_path / "daily-models").ensure()
    return TestClient(create_app(tmp_path, daily_paths=daily_paths))


def test_health_and_cors(tmp_path: Path) -> None:
    client = _client(tmp_path)
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "degraded"  # daily is the main product and is not initialised
    assert payload["ready"] is False
    assert payload["available_horizons"] == [16, 32]
    assert payload["data_ready"] is True  # legacy field continues to describe +16/+32
    assert payload["medium_term"]["status"] == "ok"
    assert payload["daily"]["status"] == "unavailable"
    assert payload["daily"]["model_ready"] is False
    assert payload["daily"]["snapshot_ready"] is False
    assert payload["is_live"] is False

    preflight = client.options(
        "/api/cells?horizon=16",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cells_json_and_geojson(tmp_path: Path) -> None:
    client = _client(tmp_path)

    response = client.get("/api/cells", params={"horizon": 16})
    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "CellCollection"
    assert payload["count"] == 2
    assert payload["snapshot_date"] == "2025-12-19"
    assert payload["is_live"] is False
    assert payload["cells"][0]["cell_id"] == "JOR,001"

    response = client.get(
        "/api/cells", params={"horizon": 32, "format": "geojson"}
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "FeatureCollection"
    assert payload["features"][0]["geometry"]["type"] == "Polygon"
    assert payload["features"][0]["geometry"]["coordinates"][0][0] == [35.8, 31.8]
    assert payload["features"][0]["properties"]["risk_level"] == "High"


def test_missing_risk_level_uses_canonical_40_70_thresholds(tmp_path: Path) -> None:
    scores = [0.0, 39.9, 40.0, 69.9, 70.0, 100.0, None]
    _write_json(
        tmp_path / "cells_16.json",
        {
            "cells": [
                {"cell_id": f"cell-{index}", "risk_score": score}
                for index, score in enumerate(scores)
            ]
        },
    )
    client = TestClient(create_app(tmp_path))

    response = client.get("/api/cells", params={"horizon": 16})
    assert response.status_code == 200
    assert [cell["risk_level"] for cell in response.json()["cells"]] == [
        "Low",
        "Low",
        "Moderate",
        "Moderate",
        "High",
        "High",
        "N/A",
    ]


def test_geojson_uses_canonical_values_and_matches_geometry_by_id(tmp_path: Path) -> None:
    client = _client(tmp_path)

    # Add a reversed GeoJSON file with deliberately stale scientific values.
    # JSON remains the canonical cell source, while GeoJSON contributes only
    # geometry. This guards both API consistency and cell-id matching.
    _write_json(
        tmp_path / "cells_16.geojson",
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "JOR-002",
                    "geometry": {"type": "Point", "coordinates": [36.4, 30.2]},
                    "properties": {"risk_score": 99.0, "horizon_days": 16},
                },
                {
                    "type": "Feature",
                    "id": "JOR,001",
                    "geometry": {"type": "Point", "coordinates": [35.91, 31.95]},
                    "properties": {"risk_score": 1.0, "horizon_days": 16},
                },
            ],
        },
    )

    cells = client.get("/api/cells", params={"horizon": 16}).json()["cells"]
    features = client.get(
        "/api/cells", params={"horizon": 16, "format": "geojson"}
    ).json()["features"]
    by_id = {feature["id"]: feature for feature in features}

    assert [feature["id"] for feature in features] == [cell["cell_id"] for cell in cells]
    for cell in cells:
        properties = by_id[cell["cell_id"]]["properties"]
        assert properties["risk_score"] == cell["risk_score"]
        assert properties["national_priority_rank"] == cell["national_priority_rank"]
    assert by_id["JOR,001"]["geometry"]["coordinates"] == [35.91, 31.95]
    assert by_id["JOR-002"]["geometry"]["coordinates"] == [36.4, 30.2]


def test_cell_detail_and_not_found(tmp_path: Path) -> None:
    client = _client(tmp_path)
    response = client.get("/api/cells/JOR%2C001", params={"horizon": 32})
    assert response.status_code == 200
    assert response.json()["cell_id"] == "JOR,001"
    assert response.json()["is_live"] is False

    response = client.get("/api/cells/no-such-cell", params={"horizon": 16})
    assert response.status_code == 404


def test_validation_and_science_endpoints(tmp_path: Path) -> None:
    client = _client(tmp_path)
    assert client.get("/api/cells?horizon=7").status_code == 422
    assert client.get("/api/cells?horizon=16&format=kml").status_code == 422

    metrics = client.get("/api/metrics")
    assert metrics.status_code == 200
    assert metrics.json()["metric"] == "MAE"
    assert metrics.json()["is_live"] is False

    metadata = client.get("/api/metadata")
    assert metadata.status_code == 200
    assert metadata.json()["serving_mode"] == "saved_local_snapshot"
    assert metadata.json()["is_live"] is False

    areas = client.get("/api/areas")
    alias = client.get("/api/national-summary")
    assert areas.status_code == 200
    assert alias.status_code == 200
    assert areas.json() == alias.json()
    assert areas.json()["scope"] == "Jordan"


def test_missing_cell_data_returns_clear_503(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))
    response = client.get("/api/cells?horizon=16")
    assert response.status_code == 503
    assert response.json()["error"] == "local_data_unavailable"
    assert response.json()["is_live"] is False


def test_summary_falls_back_to_cell_data(tmp_path: Path) -> None:
    client = _client(tmp_path)
    (tmp_path / "national_summary.json").unlink()
    response = client.get("/api/areas")
    assert response.status_code == 200
    summary = response.json()
    assert summary["horizons"]["16"]["risk_level_counts"]["High"] == 1
    assert summary["horizons"]["32"]["cell_count"] == 1
