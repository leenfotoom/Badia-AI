import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.app.daily import modeling as M, pipeline as P, providers
from backend.app.daily.config import CLIMATOLOGY_BUNDLE_FILES, FORECAST_MODEL, LEADS, SCHEMA_VERSION
from backend.app.daily.retrain import (Gates, Registry, augment_saved_version_metrics,
                                       check_gates, run_retrain, should_retrain)
from backend.app.daily.store import Paths, read_json, sha256_file, write_csv_atomic, write_json_atomic
from backend.app.main import create_app


def metrics(mae=0.07, rho=0.7, n=5000, sp=0.3, sc=0.3, leads=None):
    base = {"n": n, "mae": mae, "rmse": mae * 1.3, "spearman": rho, "mae_persistence": 0.1, "mae_climatology": 0.1,
            "auc_high_stress": 0.8, "skill_vs_persistence": sp, "skill_vs_climatology": sc}
    return {"overall": base, "by_lead": {str(l): dict(base) for l in LEADS} if leads is None else leads,
            "spatial_cv_train_window": {"folds": 4, "mae_mean": mae, "spearman_mean": rho}}


# ------------------------------------------------------------------ gates
def test_gates_first_champion_needs_clear_skill_over_baselines():
    assert check_gates(metrics(), None)[0]
    ok, why = check_gates(metrics(sp=0.01), None)
    assert not ok and "persistence" in why[0]


def test_gates_promote_only_when_meaningfully_better():
    champ = metrics(mae=0.08)
    assert check_gates(metrics(mae=0.07), champ)[0]
    ok, why = check_gates(metrics(mae=0.0795), champ)               # <1% better
    assert not ok and any("better than champion" in w for w in why)
    assert not check_gates(metrics(mae=0.07, rho=0.6), champ)[0]    # rank skill dropped
    assert not check_gates(metrics(mae=0.07, n=100), champ)[0]      # holdout too small


def test_gates_block_single_lead_regression_and_nan():
    champ = metrics(mae=0.08)
    cand = metrics(mae=0.07)
    cand["by_lead"]["7"]["mae"] = 0.09                              # lead 7 worse than 0.08*1.05
    ok, why = check_gates(cand, champ)
    assert not ok and any("lead 7" in w for w in why)
    bad = metrics()
    bad["overall"]["mae"] = float("nan")
    assert check_gates(bad, champ) == (False, ["non-finite candidate metrics"])


def test_gates_allow_undefined_optional_auc_but_not_critical_metrics():
    candidate = metrics()
    candidate["overall"]["auc_high_stress"] = None
    for lead in candidate["by_lead"].values():
        lead["auc_high_stress"] = float("nan")
    assert check_gates(candidate, None)[0]
    candidate["by_lead"]["3"]["rmse"] = float("nan")
    ok, why = check_gates(candidate, None)
    assert not ok and "lead 3 has non-finite metrics" in why


def test_registry_promote_rollback_keeps_previous(tmp_path):
    p = Paths(tmp_path / "d", tmp_path / "m").ensure()
    for v in ("v1", "v2"):
        (p.versions / v).mkdir()
        (p.versions / v / "model.json").write_text("{}")
    r = Registry(p)
    r.promote("v1", "first", {})
    r.promote("v2", "better", {})
    assert r.champion()["version"] == "v2" and r.champion()["previous"] == "v1"
    assert r.rollback() == "v1" and r.champion()["version"] == "v1"
    with pytest.raises(RuntimeError):
        r.rollback()
    assert r.versions() == ["v1", "v2"]                              # nothing deleted


def test_retrain_cadence_is_evidence_based():
    now = datetime(2026, 3, 1, tzinfo=timezone.utc)
    champ = {"promoted_at": "2026-02-20T00:00:00+00:00", "gate_report": {"data_end": "2026-02-10"}}
    assert should_retrain({"data_end": "2026-02-28"}, champ, now)[0] is False        # too soon
    old = {"promoted_at": "2026-01-01T00:00:00+00:00", "gate_report": {"data_end": "2026-02-20"}}
    assert should_retrain({"data_end": "2026-03-01"}, old, now)[0] is False          # too few new labels
    assert should_retrain({"data_end": "2026-03-20"}, old, now)[0] is True
    assert should_retrain({"data_end": "2026-03-20"}, None, now)[0] is True


# ------------------------------------------------------------------ end-to-end candidate vs champion (synthetic)
def _write_dataset(paths, panel):
    d = paths.dataset
    panel["obs"].to_csv(d / "obs_daily.csv.gz", index=False)
    panel["fc"].to_csv(d / "forecast_prev.csv.gz", index=False)
    panel["static"].to_csv(d / "static.csv", index=False)
    panel["cells"][["cell_id", "latitude", "longitude"]].to_csv(d / "cells.csv", index=False)
    files = ("obs_daily.csv.gz", "forecast_prev.csv.gz", "static.csv", "cells.csv")
    write_json_atomic(d / "manifest.json", {
        "data_start": str(pd.Timestamp(panel["fc"]["valid_date"].min()).date()),
        "data_end": "2025-12-31",
        "observation_preload_start": str(pd.Timestamp(panel["obs"]["date"].min()).date()),
        "excluded_forecast_valid_dates": [],
        "provider_fetch_metadata": {"previous_runs": {"excluded_forecast_valid_dates": []}},
        "schema_version": SCHEMA_VERSION,
        "forecast_model": FORECAST_MODEL, "leads": list(LEADS),
        "sha256": {name: sha256_file(d / name) for name in files},
    })
    panel["clim"].save(paths.climatology)
    mapping = panel["cells"][["cell_id", "latitude", "longitude"]].copy()
    mapping["climatology_anchor_cell_id"] = mapping["cell_id"]
    mapping["distance_km"] = 0.0
    write_csv_atomic(mapping, paths.climatology_mapping, index=False)
    write_json_atomic(paths.climatology_metadata, {
        "schema_version": SCHEMA_VERSION,
        "method": "test_cell_specific_climatology",
        "n_anchor_cells": int(len(mapping)),
        "n_target_cells": int(len(mapping)),
    })


def test_candidate_vs_champion_end_to_end(tmp_path, panel, monkeypatch):
    paths = Paths(tmp_path / "d", tmp_path / "m").ensure()
    _write_dataset(paths, panel)
    # A deterministic test-only bar separates the intentionally tiny four-tree
    # candidate from the normal model after complete issue-day cohorts made the
    # synthetic panel slightly easier. Production keeps the configured 5% gate.
    gates = Gates(min_test_rows=500, first_champion_min_skill=0.20)
    weak = {**M.PARAMS, "n_estimators": 4, "early_stopping_rounds": None}
    monkeypatch.setattr(M, "PARAMS", weak)
    first = run_retrain(paths, gates, holdout_days=120, val_days=90, force=True, tag="v_weak")
    # The intentionally weak first candidate must not bypass the first-champion
    # per-horizon baseline gates merely to make the registry non-null.
    assert first["action"] == "rejected_kept_champion" and Registry(paths).champion() is None
    monkeypatch.undo()
    better = run_retrain(paths, gates, holdout_days=120, val_days=90, force=True, tag="v_strong")
    assert better["action"] == "promoted", better["failures"]
    ch = Registry(paths).champion()
    assert ch["version"] == "v_strong" and ch["previous"] is None
    assert set(better["candidate_by_season"]) == {"DJF", "MAM", "JJA", "SON"}
    strong_dir = paths.versions / "v_strong"
    metadata = read_json(strong_dir / "metrics.json")
    climate_files = metadata["climatology_artifacts"]["files"]
    assert set(climate_files) == set(CLIMATOLOGY_BUNDLE_FILES)
    for name in CLIMATOLOGY_BUNDLE_FILES:
        assert sha256_file(strong_dir / name) == climate_files[name]["sha256"]
    model_hash = sha256_file(strong_dir / "model.json")
    summary = augment_saved_version_metrics(paths, "v_strong")
    assert summary["gate_decision_preserved"] == {"passed": True, "failures": []}
    assert summary["overall"]["r2"] == metadata["metrics"]["test"]["overall"]["r2"]
    assert set(summary["by_season"]) == {"DJF", "MAM", "JJA", "SON"}
    assert sha256_file(strong_dir / "model.json") == model_hash
    assert (strong_dir / "backtest_summary.json").is_file()
    # identical retrain must NOT replace the champion (no >=1% improvement) and must keep it live
    same = run_retrain(paths, gates, holdout_days=120, val_days=90, force=True, tag="v_same")
    assert same["action"] == "rejected_kept_champion" and Registry(paths).champion()["version"] == "v_strong"
    assert "v_same" in Registry(paths).versions()                                    # candidate kept for audit, not live
    assert Registry(paths).champion()["previous"] is None


def test_retrain_skipped_when_cadence_not_met(tmp_path, panel):
    paths = Paths(tmp_path / "d", tmp_path / "m").ensure()
    _write_dataset(paths, panel)
    write_json_atomic(paths.champion_file, {"version": "x", "promoted_at": datetime.now(timezone.utc).isoformat(),
                                            "gate_report": {"data_end": "2025-12-30"}})
    assert run_retrain(paths, force=False)["action"] == "skipped"


# ------------------------------------------------------------------ API
def _snapshot(state_age_h=1.0):
    generated = datetime.now(timezone.utc) - timedelta(hours=state_age_h)
    generated_iso = generated.isoformat(timespec="seconds")
    reference = pd.Timestamp("2026-10-01")
    days = [{"lead_days": l, "date": str((reference + pd.Timedelta(days=l)).date()), "score": 40.0 + l,
             "level": "Moderate", "change_vs_today": float(l),
             "predicted_esi": 0.4, "drivers": [{"key": "soil_moisture_below_normal", "group": "soil_moisture", "effect": 0.05}],
             "offsets": [], "change_drivers": None,
             "confidence": {"value": 0.6, "level": "medium", "components": {}}} for l in range(8)]
    return {"schema_version": "daily-v2", "is_synthetic": False, "state": "fresh",
            "generated_at": generated_iso, "issued_at": None,
            "forecast_reference_date": "2026-10-01", "issue_day": "2026-10-01",
            "covers": [d["date"] for d in days],
            "score_definition": "0-100 relative severity index ... NOT a probability.",
            "freshness": {"forecast_retrieved_at": generated_iso, "forecast_fetched_at": generated_iso,
                          "forecast_issue_time": None, "forecast_issue_time_status": "not_provided_by_provider",
                          "forecast_reference_date": "2026-10-01", "forecast_age_hours": 0.0,
                          "latest_observation_date": "2026-09-25", "observation_retrieved_at": generated_iso,
                          "latest_satellite_date": "2026-08-28", "source_stale": False,
                          "observation_source": "ERA5-Land", "satellite_source": "MODIS",
                          "last_successful_update": generated_iso},
            "source_state": "fresh", "quality": {"complete_cells": 1, "expected_cells": 1},
            "provider_status": "ok", "last_update_error": None,
            "last_successful_update": generated_iso,
            "model": {"version": "vt", "promoted_at": None, "test_window": {}},
            "cells": {"27,328": {"latitude": 30.0, "longitude": 36.0, "vegetation": {"state": "below_normal"}, "days": days}}}


@pytest.fixture
def client(tmp_path):
    paths = Paths(tmp_path / "d", tmp_path / "m").ensure()
    return TestClient(create_app(daily_paths=paths)), paths


def test_api_not_initialized_is_explicit_not_fake(client):
    c, _ = client
    s = c.get("/api/daily/status").json()
    assert s["state"] == "not_initialized" and s["is_synthetic"] is False
    assert c.get("/api/daily/forecast").json()["cells"] == {}
    assert c.get("/api/daily/cells/27%2C328").status_code == 503


def test_api_serves_snapshot_comma_ids_and_states(client):
    c, paths = client
    write_json_atomic(paths.snapshots / "latest.json", _snapshot())
    st = c.get("/api/daily/status").json()
    assert st["state"] == "fresh" and len(st["covers"]) == 8 and "NOT a probability" in st["score_definition"]
    assert st["forecast_reference_date"] == "2026-10-01" and st["issued_at"] is None
    assert st["freshness"]["forecast_retrieved_at"] == st["generated_at"]
    r = c.get("/api/daily/cells/27%2C328").json()
    assert r["days"][0]["lead_days"] == 0 and r["days"][-1]["lead_days"] == 7
    assert r["freshness"]["latest_satellite_date"] == "2026-08-28"
    assert c.get("/api/daily/cells/nope").status_code == 404
    f = c.get("/api/daily/forecast", params={"lead": 0}).json()
    assert [d["lead_days"] for d in f["cells"]["27,328"]["days"]] == [0]
    assert c.get("/api/daily/forecast", params={"lead": -1}).status_code == 422
    assert c.get("/api/daily/forecast", params={"lead": 8}).status_code == 422
    sm = c.get("/api/daily/summary").json()
    assert sm["leads"]["0"]["Moderate"] == 1 and len(sm["leads"]) == 8


def test_api_marks_stale_and_expired(client):
    c, paths = client
    write_json_atomic(paths.snapshots / "latest.json", _snapshot(state_age_h=30))
    assert c.get("/api/daily/status").json()["state"] == "stale"
    write_json_atomic(paths.snapshots / "latest.json", _snapshot(state_age_h=100))
    assert c.get("/api/daily/status").json()["state"] == "expired"


def test_existing_medium_term_endpoints_unchanged(client):
    c, _ = client
    assert c.get("/api/cells", params={"horizon": 16}).status_code == 200
    assert c.get("/api/cells", params={"horizon": 32}).status_code == 200
