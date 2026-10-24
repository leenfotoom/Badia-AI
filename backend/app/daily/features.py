"""Leakage-safe feature builder shared by training and serving.

Rules enforced here (and tested):
  * observed inputs for issue day T end at T - OBS_LAG_DAYS (archive availability);
  * forecast inputs for target D = T + L come from the forecast issued for lead L
    (training: archived `previous_day{L}`; serving: the current run) - never reanalysis;
  * cumulative forecast rain = sum_k=0..L precip_forecast(T+k, lead=k);
  * the target (esi at D) is attached only when requested and never used as an input.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .climatology import Climatology
from .config import FEATURES_V1, LEADS, OBS_LAG_DAYS


def _observed_state(obs: pd.DataFrame, clim: Climatology) -> pd.DataFrame:
    """Trailing (past-only) antecedent features keyed by (cell_id, obs_end_date)."""
    parts = []
    for cell, g in obs.sort_values("date").groupby("cell_id"):
        g = g.set_index("date").asfreq("D")
        pr = g["precip_mm"]
        last_wet = pr.where(pr >= 1.0).index.to_series().where(pr >= 1.0).ffill()
        dry = (g.index.to_series() - last_wet).dt.days.fillna(120).clip(upper=120)
        f = pd.DataFrame({
            "obs_sm_last": g["sm_0_7"],
            "obs_sm_change_7d": g["sm_0_7"] - g["sm_0_7"].shift(7),
            "obs_rain_7d_mm": pr.rolling(7, min_periods=6).sum(),
            "obs_rain_30d_mm": pr.rolling(30, min_periods=27).sum(),
            "obs_rain_90d_mm": pr.rolling(90, min_periods=80).sum(),
            "obs_dry_spell_days": dry,
            "obs_tmax_7d_mean_c": g["tmax_c"].rolling(7, min_periods=6).mean(),
            "obs_vpd_max_7d_mean_kpa": g["vpd_max_kpa"].rolling(7, min_periods=6).mean(),
        })
        f["cell_id"] = cell
        f.index.name = "obs_end"
        parts.append(f.reset_index())
    st = pd.concat(parts, ignore_index=True)
    doy = st["obs_end"].dt.dayofyear.to_numpy()
    ids = st["cell_id"].to_numpy()
    st["obs_sm_pct_last"] = clim.percentile("sm", ids, doy, st["obs_sm_last"])
    st["obs_rain_30d_pct"] = clim.percentile("rain30", ids, doy, st["obs_rain_30d_mm"])
    return st


def _forecast_wide(fc: pd.DataFrame) -> pd.DataFrame:
    """Return features only for cell/issue cohorts containing every lead exactly once.

    Previous Runs is requested on a valid-date interval, so its leading/trailing issue
    days naturally contain only some horizons.  Removing the *whole* incomplete cohort
    ensures every lead-day evaluation uses the same issue dates and prevents a missing
    horizon from being hidden by ``pivot_table``.
    """
    f = fc.copy()
    f["cell_id"] = f["cell_id"].astype(str)
    f["valid_date"] = pd.to_datetime(f["valid_date"]).dt.normalize()
    f["lead_days"] = pd.to_numeric(f["lead_days"], errors="coerce")
    f["issue_day"] = f["valid_date"] - pd.to_timedelta(f["lead_days"], unit="D")

    keys = ["cell_id", "issue_day"]
    cohorts = f.groupby(keys, sort=False, dropna=False)["lead_days"].agg(
        row_count="size", lead_count="nunique", min_lead="min", max_lead="max"
    )
    complete = cohorts[
        (cohorts["row_count"] == len(LEADS))
        & (cohorts["lead_count"] == len(LEADS))
        & (cohorts["min_lead"] == min(LEADS))
        & (cohorts["max_lead"] == max(LEADS))
    ].reset_index()[keys]
    f = f.merge(complete, on=keys, how="inner")
    if len(f):
        f["lead_days"] = f["lead_days"].astype(int)

    wide = f.pivot_table(index=["cell_id", "issue_day"], columns="lead_days", values="precip_mm", aggfunc="first")
    rows = []
    for L in LEADS:
        cols = [k for k in LEADS if k <= L]
        if any(k not in wide.columns for k in cols):
            continue
        sub = wide[cols]
        full = sub.notna().all(axis=1)
        r = pd.DataFrame({"fc_precip_cum_mm": sub.sum(axis=1).where(full),
                          "fc_dry_days": (sub < 1.0).sum(axis=1).where(full)})
        r["lead_days"] = L
        rows.append(r.reset_index())
    cum = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(
        columns=["cell_id", "issue_day", "fc_precip_cum_mm", "fc_dry_days", "lead_days"])
    day = f.rename(columns={"precip_mm": "fc_precip_day_mm", "tmax_c": "fc_tmax_c", "tmin_c": "fc_tmin_c",
                            "tmean_c": "fc_tmean_c", "vpd_max_kpa": "fc_vpd_max_kpa"})
    day = day[["cell_id", "issue_day", "lead_days", "valid_date", "fc_precip_day_mm", "fc_tmax_c",
               "fc_tmin_c", "fc_tmean_c", "fc_vpd_max_kpa"]]
    return day.merge(cum, on=["cell_id", "issue_day", "lead_days"], how="left")


def build_features(cells: pd.DataFrame, obs: pd.DataFrame, fc: pd.DataFrame, clim: Climatology,
                   static: pd.DataFrame | None = None, esi: pd.DataFrame | None = None,
                   issue_days: list | None = None) -> pd.DataFrame:
    """One row per (cell, issue_day, lead). `esi` (cell_id, date, esi) attaches labels if given."""
    st = _observed_state(obs, clim)
    wide = _forecast_wide(fc)
    if issue_days is not None:
        wide = wide[wide["issue_day"].isin(pd.to_datetime(issue_days))]
    wide = wide.assign(obs_end=wide["issue_day"] - pd.Timedelta(days=OBS_LAG_DAYS))
    df = wide.merge(st, on=["cell_id", "obs_end"], how="left")
    meta = cells[["cell_id", "latitude", "longitude"]].drop_duplicates("cell_id")
    df = df.merge(meta, on="cell_id", how="left")
    if static is not None and "elevation_m" in static:
        df = df.merge(static[["cell_id", "elevation_m"]], on="cell_id", how="left")
    else:
        df["elevation_m"] = np.nan
    doy = df["valid_date"].dt.dayofyear.to_numpy()
    df["doy_sin"], df["doy_cos"] = np.sin(2 * np.pi * doy / 366), np.cos(2 * np.pi * doy / 366)
    ids = df["cell_id"].to_numpy()
    df["fc_tmax_pct"] = clim.percentile("tmax", ids, doy, df["fc_tmax_c"])
    df["fc_vpd_pct"] = clim.percentile("vpd", ids, doy, df["fc_vpd_max_kpa"])
    df = df.rename(columns={"valid_date": "target_date"})
    if esi is not None:
        e = esi.rename(columns={"date": "target_date", "esi": "esi_target"})
        df = df.merge(e, on=["cell_id", "target_date"], how="left")
    return df


def feature_matrix(df: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in FEATURES_V1 if c not in df.columns]
    if missing:
        raise ValueError(f"missing model inputs: {missing}")
    return df[FEATURES_V1].astype(float)


def completeness(df: pd.DataFrame) -> pd.Series:
    """Fraction of model inputs present per row (elevation excluded: static)."""
    cols = [c for c in FEATURES_V1 if c != "elevation_m"]
    return df[cols].notna().mean(axis=1)
