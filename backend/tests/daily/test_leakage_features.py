import numpy as np
import pandas as pd
import pytest

from backend.app.daily.config import FEATURES_V1, LEADS, OBS_LAG_DAYS
from backend.app.daily.features import build_features, feature_matrix, completeness
from backend.app.daily.climatology import Climatology
from backend.app.daily.target import compute_esi


def test_target_never_in_features():
    assert not any("esi" in f or "target" in f for f in FEATURES_V1)


def test_schema_complete_and_ordered(panel):
    X = feature_matrix(panel["df"])
    assert list(X.columns) == FEATURES_V1 and X.shape[0] > 1000


def test_observations_after_obs_end_cannot_change_features(panel):
    """Core leakage test: corrupt every observation newer than issue_day-5d; features must not move."""
    cells, obs, fc, clim, static = (panel[k] for k in ("cells", "obs", "fc", "clim", "static"))
    T = pd.Timestamp("2025-06-15")
    base = build_features(cells, obs, fc, clim, static=static, issue_days=[T])
    poisoned = obs.copy()
    m = poisoned["date"] > T - pd.Timedelta(days=OBS_LAG_DAYS)
    poisoned.loc[m, ["precip_mm", "sm_0_7", "tmax_c", "vpd_max_kpa"]] = 9999.0
    alt = build_features(cells, poisoned, fc, clim, static=static, issue_days=[T])
    cols = [c for c in FEATURES_V1 if c.startswith("obs_")]
    pd.testing.assert_frame_equal(base[["cell_id", "lead_days"] + cols].reset_index(drop=True),
                                  alt[["cell_id", "lead_days"] + cols].reset_index(drop=True))
    assert len(base) > 0


def test_cumulative_forecast_rain_uses_each_lead_series(panel):
    cells, obs, fc, clim = (panel[k] for k in ("cells", "obs", "fc", "clim"))
    T = pd.Timestamp("2025-03-10")
    cid = cells.cell_id.iloc[0]
    row = build_features(cells, obs, fc, clim, issue_days=[T])
    row = row[(row.cell_id == cid) & (row.lead_days == 4)].iloc[0]
    expected = sum(fc[(fc.cell_id == cid) & (fc.lead_days == k) & (fc.valid_date == T + pd.Timedelta(days=k))]["precip_mm"].iloc[0]
                   for k in range(0, 5))
    assert row["fc_precip_cum_mm"] == pytest.approx(expected)
    assert row["target_date"] == T + pd.Timedelta(days=4)


def test_changing_other_leads_forecast_for_later_dates_does_not_leak(panel):
    cells, obs, fc, clim = (panel[k] for k in ("cells", "obs", "fc", "clim"))
    T = pd.Timestamp("2025-03-10")
    base = build_features(cells, obs, fc, clim, issue_days=[T])
    f2 = fc.copy()
    f2.loc[f2["valid_date"] > T + pd.Timedelta(days=7), ["precip_mm", "tmax_c"]] = 777.0
    alt = build_features(cells, obs, f2, clim, issue_days=[T])
    pd.testing.assert_frame_equal(base.reset_index(drop=True), alt.reset_index(drop=True))


def test_feature_builder_drops_whole_incomplete_issue_cohort(panel):
    cells, obs, fc, clim = (panel[k] for k in ("cells", "obs", "fc", "clim"))
    issue = pd.Timestamp("2025-03-10")
    other_issue = issue + pd.Timedelta(days=1)
    cell_id = cells.cell_id.iloc[0]
    damaged = fc.copy()
    missing = (
        (damaged["cell_id"] == cell_id)
        & (damaged["lead_days"] == max(LEADS))
        & (damaged["valid_date"] == issue + pd.Timedelta(days=max(LEADS)))
    )
    assert missing.sum() == 1
    damaged = damaged.loc[~missing]

    result = build_features(cells, obs, damaged, clim, issue_days=[issue, other_issue])
    grouped = result.groupby(["cell_id", "issue_day"])["lead_days"].agg(["size", "nunique", "min", "max"])
    assert not ((result["cell_id"] == cell_id) & (result["issue_day"] == issue)).any()
    assert ((result["cell_id"] == cell_id) & (result["issue_day"] == other_issue)).sum() == len(LEADS)
    assert grouped["size"].eq(len(LEADS)).all()
    assert grouped["nunique"].eq(len(LEADS)).all()
    assert grouped["min"].eq(min(LEADS)).all() and grouped["max"].eq(max(LEADS)).all()


def test_climatology_uses_only_reference_years(panel):
    obs = panel["obs"]
    ref_only = obs[(obs.date.dt.year >= 2015) & (obs.date.dt.year <= 2023)]
    c1, c2 = Climatology.fit(obs), Climatology.fit(ref_only)
    np.testing.assert_allclose(c1.nodes, c2.nodes, equal_nan=True)  # 2024-25 data must not alter it


def test_percentiles_bounded_monotonic_and_nan_safe(panel):
    clim = panel["clim"]
    cid = panel["cells"].cell_id.iloc[0]
    vals = np.linspace(0, 0.5, 50)
    p = clim.percentile("sm", [cid] * 50, [180] * 50, vals)
    assert np.nanmin(p) >= 0 and np.nanmax(p) <= 1 and (np.diff(p) >= -1e-9).all()
    assert np.isnan(clim.percentile("sm", ["unknown"], [180], [0.1])[0])
    assert np.isnan(clim.percentile("sm", [cid], [180], [np.nan])[0])


def test_esi_bounded_and_requires_all_components(panel):
    esi = panel["esi"]["esi"].dropna()
    assert esi.between(0, 1).all()
    obs = panel["obs"].copy()
    obs.loc[obs.index[-50:], "sm_0_7"] = np.nan
    e = compute_esi(obs, panel["clim"])
    assert e["esi"].isna().sum() >= 50


def test_no_data_cell_yields_low_completeness_not_crash(panel):
    cells, obs, fc, clim, static = (panel[k] for k in ("cells", "obs", "fc", "clim", "static"))
    cid = cells.cell_id.iloc[0]
    o2 = obs[obs.cell_id != cid]
    df = build_features(cells, o2, fc, clim, static=static, issue_days=[pd.Timestamp("2025-06-15")])
    c = completeness(df)
    assert c[df.cell_id == cid].max() < c[df.cell_id != cid].min()
