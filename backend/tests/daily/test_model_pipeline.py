import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend.app.daily import modeling as M, pipeline as P, providers
from backend.app.daily.config import FEATURES_V1, LEADS, SCHEMA_VERSION
from backend.app.daily.features import feature_matrix
from backend.app.daily.http import ProviderError
from backend.app.daily.retrain import snapshot_climatology
from backend.app.daily.store import Paths, write_csv_atomic, write_json_atomic

SP = M.Splits(pd.Timestamp("2025-03-31"), pd.Timestamp("2025-07-31"))


@pytest.fixture(scope="module")
def trained(panel):
    return M.train_candidate(panel["df"], SP, panel["esi"], with_spatial=True)


def test_time_split_is_purged_and_ordered(panel):
    parts = M.split_by_time(panel["df"].dropna(subset=["esi_target"]), SP)
    tr, va, te = parts["train"], parts["val"], parts["test"]
    assert tr["target_date"].max() <= SP.train_end                       # no label from the future in train
    assert va["issue_day"].min() > SP.train_end + pd.Timedelta(days=7)    # embargo
    assert te["issue_day"].min() > SP.val_end + pd.Timedelta(days=7)
    assert tr["issue_day"].max() < va["issue_day"].min() < te["issue_day"].min()


def test_metrics_cover_baselines_every_lead_and_spatial_cv(trained):
    t = trained.metrics["test"]
    for k in ("mae", "rmse", "r2", "spearman", "mae_persistence", "mae_climatology", "auc_high_stress",
              "skill_vs_persistence", "skill_vs_climatology"):
        assert np.isfinite(t["overall"][k]), k
    assert set(t["by_lead"]) == {str(l) for l in LEADS}
    assert set(t["by_season"]) == set(M.SEASON_MONTHS)
    assert sum(season["n"] for season in t["by_season"].values()) == t["overall"]["n"]
    assert all(np.isfinite(season["r2"]) for season in t["by_season"].values() if season["available"])
    assert trained.metrics["spatial_cv_train_window"]["folds"] >= 2


def test_baseline_skill_uses_identical_rows():
    y = np.array([0.0, 1.0, 0.5])
    pred = np.array([0.1, 0.9, 0.5])
    persistence = np.array([np.nan, 0.7, 0.2])
    climatology = np.array([0.4, 0.4, 0.4])
    m = M._metrics(y, pred, persistence, climatology, 0.7)
    assert m["n_persistence_common"] == 2
    assert m["mae_model_on_persistence_rows"] == pytest.approx(0.05)
    assert m["mae_persistence"] == pytest.approx(0.3)
    assert m["skill_vs_persistence"] == pytest.approx(1 - 0.05 / 0.3)


def test_auc_is_null_when_holdout_has_only_one_class():
    assert M._auc(np.ones(4, dtype=int), np.linspace(0.1, 0.4, 4)) is None


def test_r2_is_standard_allows_negative_and_is_null_for_constant_target():
    y = np.array([1.0, 2.0, 3.0])
    assert M._r2(y, y) == pytest.approx(1.0)
    assert M._r2(y, np.array([3.0, 3.0, 3.0])) == pytest.approx(-1.5)
    assert M._r2(np.ones(3), np.ones(3)) is None


def test_seasons_use_target_date_not_issue_date(trained, panel):
    labelled = panel["df"].dropna(subset=["esi_target"])
    parts = M.split_by_time(labelled, SP)
    lookup = panel["esi"].set_index(["cell_id", "date"])["esi"]
    threshold = float(parts["train"]["esi_target"].quantile(0.70))
    result = M.evaluate(trained.model, parts["test"], parts["train"], lookup, threshold)
    expected_jja = int(parts["test"]["target_date"].dt.month.isin(M.SEASON_MONTHS["JJA"]).sum())
    assert result["by_season"]["JJA"]["n"] == expected_jja
    assert all(s["date_basis"] == "target_date" for s in result["by_season"].values())


def test_calibrated_score_is_bounded_monotonic_relative_index(trained):
    s = trained.calibrator.score(np.linspace(-1, 2, 200))
    assert s.min() >= 0 and s.max() <= 100 and (np.diff(s) >= 0).all()
    cal2 = M.Calibrator.from_json(trained.calibrator.to_json())
    assert abs(cal2.score(np.array([0.4]))[0] - trained.calibrator.score(np.array([0.4]))[0]) < 2.0


def test_group_contributions_additive(trained, panel):
    X = feature_matrix(panel["df"].dropna(subset=["esi_target"]).head(300))
    import xgboost as xgb
    raw = trained.model.get_booster().predict(xgb.DMatrix(X), pred_contribs=True, iteration_range=M._tree_range(trained.model))
    grp = M.group_contributions(trained.model, X)
    ctx = [f for f in FEATURES_V1 if f not in sum(M.GROUPS.values(), [])]
    ctx_sum = raw[:, [FEATURES_V1.index(f) for f in ctx]].sum(axis=1)
    np.testing.assert_allclose(grp.sum(axis=1) + ctx_sum + raw[:, -1], trained.model.predict(X), atol=1e-4)


def test_bundle_roundtrip_identical_predictions_and_explanations(trained, panel, tmp_path):
    M.save_bundle(tmp_path / "v1", trained)
    m, cal, meta = M.load_bundle(tmp_path / "v1")
    X = feature_matrix(panel["df"].dropna(subset=["esi_target"]).head(200))
    np.testing.assert_allclose(m.predict(X), trained.model.predict(X), atol=1e-6)
    np.testing.assert_allclose(M.group_contributions(m, X).to_numpy(), M.group_contributions(trained.model, X).to_numpy(), atol=1e-6)
    assert meta["info"]["features"] == FEATURES_V1


def test_training_is_deterministic(panel):
    a = M.train_candidate(panel["df"], SP, panel["esi"], with_spatial=False)
    b = M.train_candidate(panel["df"], SP, panel["esi"], with_spatial=False)
    X = feature_matrix(panel["df"].dropna(subset=["esi_target"]).head(100))
    np.testing.assert_allclose(a.model.predict(X), b.model.predict(X), atol=1e-9)


# ------------------------------------------------------------------ pipeline
ISSUE = pd.Timestamp("2025-12-20").date()
NOW = datetime(2025, 12, 21, 6, 0, tzinfo=timezone.utc)


def _setup(tmp_path, panel, trained, monkeypatch, fail=False):
    paths = Paths(tmp_path / "data", tmp_path / "models").ensure()
    panel["clim"].save(paths.climatology)
    mapping = panel["cells"][["cell_id", "latitude", "longitude"]].copy()
    mapping["climatology_anchor_cell_id"] = mapping["cell_id"]
    mapping["distance_km"] = 0.0
    write_csv_atomic(mapping, paths.climatology_mapping, index=False)
    write_json_atomic(paths.climatology_metadata, {
        "schema_version": SCHEMA_VERSION,
        "method": "test_cell_specific_climatology",
    })
    version_dir = paths.versions / "vtest"
    climate_artifacts = snapshot_climatology(paths, version_dir)
    M.save_bundle(version_dir, trained, {"climatology_artifacts": climate_artifacts})
    write_json_atomic(paths.champion_file, {"version": "vtest", "promoted_at": "2025-12-01T00:00:00+00:00"})
    obs, fc, cells = panel["obs"], panel["fc"], panel["cells"]
    def fake_archive(client, c, s, e):
        if fail:
            raise ProviderError("archive down")
        o = obs[(obs.date >= pd.Timestamp(s)) & (obs.date <= pd.Timestamp(e)) & obs.cell_id.isin(c.cell_id)]
        return o, panel["static"], {"fetched_at": NOW.isoformat()}

    def fake_live(client, c, issue):
        if fail:
            raise ProviderError("forecast down")
        f = fc[(fc.valid_date - pd.to_timedelta(fc.lead_days, unit="D")).dt.date == issue]
        return f, pd.DataFrame(), {"fetched_at": (NOW - timedelta(hours=1)).isoformat()}
    monkeypatch.setattr(providers, "fetch_archive", fake_archive)
    monkeypatch.setattr(providers, "fetch_live", fake_live)
    monkeypatch.setattr(P, "amman_today", lambda now=None: ISSUE)
    return paths, cells


def test_champion_loads_immutable_versioned_climatology(tmp_path, panel, trained, monkeypatch):
    paths, _ = _setup(tmp_path, panel, trained, monkeypatch)
    expected = P.load_champion(paths)["climatology"].nodes.copy()
    paths.climatology.write_bytes(b"acquisition replaced the mutable workspace climatology")
    np.testing.assert_array_equal(P.load_champion(paths)["climatology"].nodes, expected)


def test_champion_rejects_tampered_versioned_climatology(tmp_path, panel, trained, monkeypatch):
    paths, _ = _setup(tmp_path, panel, trained, monkeypatch)
    artifact = paths.versions / "vtest" / "climatology.npz"
    artifact.write_bytes(artifact.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="climatology checksum mismatch"):
        P.load_champion(paths)


def test_update_reports_corrupt_champion_without_crashing(tmp_path, panel, trained, monkeypatch):
    paths, cells = _setup(tmp_path, panel, trained, monkeypatch)
    artifact = paths.versions / "vtest" / "climatology_mapping.csv"
    artifact.write_bytes(artifact.read_bytes() + b"tampered")
    result = P.run_update(paths, cells, now=NOW, project_data=tmp_path)
    assert result["state"] == "unavailable"
    assert "climatology checksum mismatch" in result["error"]


def test_update_writes_snapshot_with_all_required_fields(tmp_path, panel, trained, monkeypatch):
    paths, cells = _setup(tmp_path, panel, trained, monkeypatch)
    out = P.run_update(paths, cells, now=NOW, project_data=tmp_path)
    assert out["state"] == "fresh"
    s = P.serve_snapshot(paths, NOW)
    assert s["state"] == "fresh" and s["is_synthetic"] is False and "NOT a probability" in s["score_definition"]
    assert s["covers"][0] == str(ISSUE) and len(s["covers"]) == 8
    c = next(iter(s["cells"].values()))
    d = c["days"][0]
    for k in ("score", "level", "change_vs_today", "drivers", "offsets", "confidence", "date", "lead_days"):
        assert k in d
    assert 0 <= d["score"] <= 100 and d["change_vs_today"] == 0.0
    assert {"forecast_retrieved_at", "latest_observation_date", "latest_satellite_date", "observation_source"} <= set(s["freshness"])
    assert all([d["lead_days"] for d in c["days"]] == list(LEADS) for c in s["cells"].values())
    assert s["generated_at"] and s["forecast_reference_date"] == str(ISSUE)
    assert s["issued_at"] is None and s["freshness"]["forecast_issue_time_status"] == "not_provided_by_provider"
    assert (paths.snapshots / "last_good.json").exists()


def test_deterministic_rerun(tmp_path, panel, trained, monkeypatch):
    paths, cells = _setup(tmp_path, panel, trained, monkeypatch)
    P.run_update(paths, cells, now=NOW, project_data=tmp_path)
    a = json.loads((paths.snapshots / "latest.json").read_text())["cells"]
    P.run_update(paths, cells, now=NOW, project_data=tmp_path)
    assert json.loads((paths.snapshots / "latest.json").read_text())["cells"] == a


def test_provider_outage_serves_last_good_and_marks_stale(tmp_path, panel, trained, monkeypatch):
    paths, cells = _setup(tmp_path, panel, trained, monkeypatch)
    P.run_update(paths, cells, now=NOW, project_data=tmp_path)
    monkeypatch.setattr(providers, "fetch_live", lambda *a, **k: (_ for _ in ()).throw(ProviderError("down")))
    out = P.run_update(paths, cells, now=NOW + timedelta(hours=30), project_data=tmp_path)
    assert out["state"] == "fallback"
    s = P.serve_snapshot(paths, NOW + timedelta(hours=30))
    assert s["state"] == "fallback" and s["provider_status"] == "unavailable" and s["cells"]
    assert P.serve_snapshot(paths, NOW + timedelta(hours=100))["state"] == "expired"


def test_outage_without_any_snapshot_is_explicit(tmp_path, panel, trained, monkeypatch):
    paths, cells = _setup(tmp_path, panel, trained, monkeypatch, fail=True)
    assert P.run_update(paths, cells, now=NOW)["state"] == "unavailable"
    assert P.serve_snapshot(paths, NOW)["state"] == "unavailable"


def test_not_initialized_without_champion(tmp_path, panel):
    paths = Paths(tmp_path / "d", tmp_path / "m").ensure()
    assert P.run_update(paths, panel["cells"], now=NOW)["state"] == "not_initialized"


def test_missing_cell_data_lowers_confidence_and_drops_absent_cells(tmp_path, panel, trained, monkeypatch):
    paths, cells = _setup(tmp_path, panel, trained, monkeypatch)
    gone, degraded = cells.cell_id.iloc[0], cells.cell_id.iloc[1]
    real_archive = providers.fetch_archive

    def partial(client, c, s, e):
        o, st, m = real_archive(client, c, s, e)
        o = o[o.cell_id != degraded]
        return o, st, m
    monkeypatch.setattr(providers, "fetch_archive", partial)
    real_live = providers.fetch_live

    def partial_live(client, c, issue):
        f, r, m = real_live(client, c, issue)
        return f[f.cell_id != gone], r, m
    monkeypatch.setattr(providers, "fetch_live", partial_live)
    P.run_update(paths, cells, now=NOW, project_data=tmp_path)
    s = P.serve_snapshot(paths, NOW)
    assert gone not in s["cells"]                                           # no forecast -> no fabricated value
    ok = s["cells"][cells.cell_id.iloc[2]]["days"][0]["confidence"]["value"]
    bad = s["cells"][degraded]["days"][0]["confidence"]["value"]
    assert bad < ok


def test_confidence_decreases_with_age_and_missing_inputs():
    m = {"spearman": 0.8}
    fresh = P._confidence(m, 1.0, 1, 6)["value"]
    assert P._confidence(m, 1.0, 40, 6)["value"] < fresh
    assert P._confidence(m, 0.4, 1, 6)["value"] < fresh
    assert P._confidence(m, 1.0, 1, 20)["value"] < fresh


def test_reasons_are_associations_not_causes_and_thresholded():
    row = pd.Series({"obs_sm_pct_last": 0.1, "obs_rain_30d_pct": 0.2, "obs_dry_spell_days": 40, "fc_precip_cum_mm": 0.0,
                     "fc_tmax_pct": 0.9, "fc_vpd_pct": 0.9})
    contrib = pd.Series({"soil_moisture": 0.08, "recent_rain": 0.004, "forecast_rain": 0.05, "heat": -0.03, "dryness": 0.0})
    r = P._reasons(row, contrib)
    assert [d["key"] for d in r["drivers"]] == ["soil_moisture_below_normal", "forecast_rain_low"]
    assert [d["key"] for d in r["offsets"]] == ["heat_elevated"] or r["offsets"][0]["group"] == "heat"
    assert all(abs(d["effect"]) >= 0.01 for d in r["drivers"] + r["offsets"])


def test_vegetation_context_shown_separately_with_dates(tmp_path):
    d = tmp_path / "near_real_time_x"
    d.mkdir()
    pd.DataFrame({"cell_id": ["27,328", "1,1"], "ndvi_anomaly_current": [-0.02, 0.001], "modis_period_start": ["2026-08-13"] * 2,
                  "risk_level": ["High", "Low"]}).to_csv(d / "BADIA_968_16d_scored.csv", index=False)
    v = P.vegetation_context(tmp_path)
    assert v["27,328"]["state"] == "below_normal" and v["1,1"]["state"] == "near_normal"
    assert v["27,328"]["composite_end"] == "2026-08-28"
