import json
from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient

from backend.app.daily.config import CLIMATOLOGY_BUNDLE_FILES
from backend.app.daily.store import Paths, write_json_atomic
from backend.app.main import create_app


def _medium_data(path):
    for lead in (16, 32):
        (path / f"cells_{lead}.json").write_text(
            json.dumps({"snapshot_date": "2025-12-02", "cells": []}),
            encoding="utf-8",
        )


def _model_bundle(paths: Paths) -> None:
    version = "v-real"
    bundle = paths.versions / version
    bundle.mkdir(parents=True, exist_ok=True)
    for name in ("model.json", "calibration.json", "metrics.json", *CLIMATOLOGY_BUNDLE_FILES):
        (bundle / name).write_text("{}", encoding="utf-8")
    write_json_atomic(
        paths.champion_file,
        {
            "version": version,
            "promoted_at": "2026-10-05T00:00:00+00:00",
            "previous": None,
        },
    )


def _snapshot(state="fresh"):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    reference = date(2026, 10, 6)
    days = [
        {
            "lead_days": lead,
            "date": str(reference + timedelta(days=lead)),
            "score": 40.0 + lead,
            "level": "Moderate",
            "change_vs_today": float(lead),
            "predicted_esi": 0.4,
            "drivers": [],
            "offsets": [],
            "change_drivers": None,
            "confidence": {"value": 0.7, "level": "high", "components": {}},
        }
        for lead in range(8)
    ]
    return {
        "schema_version": "daily-v2",
        "is_synthetic": False,
        "state": state,
        "generated_at": now.isoformat(),
        "issued_at": None,
        "forecast_reference_date": str(reference),
        "issue_day": str(reference),
        "covers": [day["date"] for day in days],
        "score_definition": "0-100 relative severity index; NOT a probability.",
        "freshness": {
            "forecast_retrieved_at": now.isoformat(),
            "forecast_fetched_at": now.isoformat(),
            "forecast_issue_time": None,
            "forecast_issue_time_status": "not_provided_by_provider",
            "forecast_reference_date": str(reference),
            "forecast_age_hours": 0.0,
            "forecast_model": "ECMWF IFS 0.25 deg",
            "latest_observation_date": "2026-10-01",
            "observation_retrieved_at": now.isoformat(),
            "observation_source": "ERA5-Land reanalysis",
            "source_stale": state != "fresh",
            "latest_satellite_date": "2026-08-28",
            "satellite_source": "MODIS MOD13Q1",
            "last_successful_update": now.isoformat(),
        },
        "source_state": "fresh" if state == "fresh" else "fallback",
        "quality": {"complete_cells": 1, "expected_cells": 1},
        "provider_status": "ok" if state == "fresh" else "unavailable",
        "last_update_error": None if state == "fresh" else "ProviderError: forecast down",
        "last_successful_update": now.isoformat(),
        "served_from": "latest.json" if state == "fresh" else "last_good.json",
        "snapshot_age_hours": 0.0,
        "model": {"version": "v-real", "promoted_at": "2026-10-05T00:00:00+00:00"},
        "cells": {
            "27,328": {
                "latitude": 30.0,
                "longitude": 36.0,
                "vegetation": {"state": "below_normal"},
                "days": days,
            }
        },
    }


def _client(tmp_path, monkeypatch, snapshot):
    _medium_data(tmp_path)
    paths = Paths(tmp_path / "daily-data", tmp_path / "daily-models").ensure()
    _model_bundle(paths)
    monkeypatch.setattr("backend.app.daily_api.serve_snapshot", lambda _: snapshot)
    return TestClient(create_app(tmp_path, daily_paths=paths))


def test_health_and_daily_endpoints_expose_eight_day_provenance(tmp_path, monkeypatch):
    snapshot = _snapshot()
    client = _client(tmp_path, monkeypatch, snapshot)

    health = client.get("/api/health").json()
    assert health["status"] == "ok" and health["ready"] is True
    assert health["medium_term"]["available_horizons"] == [16, 32]
    assert health["daily"]["model_ready"] is True
    assert health["daily"]["snapshot_ready"] is True
    assert health["daily"]["forecast_reference_date"] == "2026-10-06"
    assert health["daily"]["issued_at"] is None

    status = client.get("/api/daily/status").json()
    assert status["generated_at"] == snapshot["generated_at"]
    assert status["issued_at"] is None
    assert status["forecast_reference_date"] == "2026-10-06"
    assert status["freshness"]["forecast_retrieved_at"] == snapshot["generated_at"]
    assert status["freshness"]["forecast_issue_time_status"] == "not_provided_by_provider"
    assert status["provider_status"] == "ok"
    assert status["quality"] == snapshot["quality"]
    assert len(status["covers"]) == 8

    for lead in (0, 7):
        forecast = client.get("/api/daily/forecast", params={"lead": lead})
        assert forecast.status_code == 200
        body = forecast.json()
        assert [d["lead_days"] for d in body["cells"]["27,328"]["days"]] == [lead]
        assert body["forecast_reference_date"] == "2026-10-06"
        assert body["generated_at"] == snapshot["generated_at"]
        assert body["freshness"]["forecast_issue_time"] is None
    assert client.get("/api/daily/forecast", params={"lead": -1}).status_code == 422
    assert client.get("/api/daily/forecast", params={"lead": 8}).status_code == 422

    cell = client.get("/api/daily/cells/27%2C328").json()
    assert len(cell["days"]) == 8
    assert cell["forecast_reference_date"] == "2026-10-06"
    summary = client.get("/api/daily/summary").json()
    assert set(summary["leads"]) == {str(lead) for lead in range(8)}
    assert summary["forecast_reference_date"] == "2026-10-06"


def test_fallback_is_usable_but_health_is_degraded(tmp_path, monkeypatch):
    snapshot = _snapshot("fallback")
    client = _client(tmp_path, monkeypatch, snapshot)
    health = client.get("/api/health").json()
    assert health["status"] == "degraded"
    assert health["daily"]["ready"] is True
    assert health["daily"]["using_fallback"] is True
    assert health["daily"]["provider_status"] == "unavailable"
    status = client.get("/api/daily/status").json()
    assert status["state"] == "fallback"
    assert status["using_fallback"] is True
    assert status["last_update_error"].startswith("ProviderError")
