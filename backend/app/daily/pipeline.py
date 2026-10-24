"""Live daily pipeline: inputs -> validate -> features -> forecast -> score -> explain -> snapshot."""
from __future__ import annotations

import logging
import os
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from . import providers
from .climatology import Climatology
from .config import (CLIMATOLOGY_BUNDLE_FILES, FEATURES_V1, LEADS, OBS_LAG_DAYS,
                     PROVIDERS, SCHEMA_VERSION, TIMEZONE, risk_level)
from .features import build_features, completeness, feature_matrix
from .http import Client, ProviderError
from .modeling import GROUPS, group_contributions, load_bundle
from .store import Paths, read_json, sha256_file, write_json_atomic

log = logging.getLogger("badia.daily.pipeline")
FORECAST_STALE_HOURS = 18          # older than this => "stale"
SNAPSHOT_EXPIRE_HOURS = 72         # fallback snapshot older than this => "expired"
VEG_TOLERANCE = 0.005              # ~ frozen +16d model test MAE (NDVI units): smaller anomalies = "near normal"
CONTRIB_MIN = 0.01                 # ESI units; smaller contributions are not reported as reasons
LIVE_OBS_DAYS = 120                # enough for 90-day rain plus missing-day tolerance


def _now() -> datetime:
    return datetime.now(timezone.utc)


def amman_today(now: datetime | None = None) -> date:
    return (now or _now()).astimezone(ZoneInfo(TIMEZONE)).date()


def _as_utc(value: str | datetime) -> datetime:
    d = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    """Write a dataframe without exposing a half-written live store."""
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = ".csv.gz" if str(path).endswith(".gz") else path.suffix
    fd, name = tempfile.mkstemp(dir=path.parent, suffix=suffix)
    os.close(fd)
    try:
        frame.to_csv(name, index=False, compression="gzip" if str(path).endswith(".gz") else None)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _combined_meta(parts: list[dict], *, local_path: Path | None = None) -> dict:
    if not parts:
        ts = datetime.fromtimestamp(local_path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds") \
            if local_path and local_path.exists() else _now().isoformat(timespec="seconds")
        return {"from_cache": True, "local_store": True, "stale": False, "fetched_at": ts, "chunks": 0}
    times = [p.get("fetched_at") for p in parts if p.get("fetched_at")]
    return {"from_cache": all(bool(p.get("from_cache")) for p in parts),
            "stale": any(bool(p.get("stale")) for p in parts),
            "fetched_at": min(times) if times else _now().isoformat(timespec="seconds"),
            "chunks": sum(int(p.get("chunks", 1)) for p in parts)}


def _live_observations(paths: Paths, client: Client, cells: pd.DataFrame, obs_end: date):
    """Load the rolling observation store and fetch only missing cells/dates.

    The first production update acquires the required 120-day context.  Later
    six-hourly runs normally reuse it, downloading at most newly verified days.
    """
    live = paths.data / "live"
    obs_file, static_file = live / "obs_daily.csv.gz", live / "static.csv"
    wanted = set(cells["cell_id"].astype(str))
    start = obs_end - timedelta(days=LIVE_OBS_DAYS)
    if obs_file.exists():
        obs = pd.read_csv(obs_file, dtype={"cell_id": str}, parse_dates=["date"])
        obs = obs[obs["cell_id"].isin(wanted) & (obs["date"] >= pd.Timestamp(start))]
    else:
        obs = pd.DataFrame()
    static = pd.read_csv(static_file, dtype={"cell_id": str}) if static_file.exists() else pd.DataFrame()
    metas: list[dict] = []

    # A cell is considered complete only when both ends of the rolling window
    # exist. Missing/new cells get a bounded full-window request.
    if len(obs):
        ranges = obs.groupby("cell_id")["date"].agg(["min", "max"])
        complete = {cid for cid, r in ranges.iterrows()
                    if r["min"] <= pd.Timestamp(start + timedelta(days=2)) and r["max"] >= pd.Timestamp(obs_end)}
    else:
        complete = set()
    missing = wanted - complete
    if missing:
        sub = cells[cells["cell_id"].astype(str).isin(missing)]
        fresh, fresh_static, meta = providers.fetch_archive(client, sub, start, obs_end)
        obs = pd.concat([obs[~obs["cell_id"].isin(missing)] if len(obs) else obs, fresh], ignore_index=True)
        static = pd.concat([static[~static["cell_id"].isin(missing)] if len(static) else static,
                            fresh_static], ignore_index=True)
        metas.append(meta)

    # If all cells existed but the provider has published a new verified day,
    # one small append fetch covers every cell; otherwise no archive call occurs.
    if len(obs) and not missing:
        last = obs.groupby("cell_id")["date"].max().min()
        if last < pd.Timestamp(obs_end):
            fresh, fresh_static, meta = providers.fetch_archive(
                client, cells, (last + pd.Timedelta(days=1)).date(), obs_end)
            obs = pd.concat([obs, fresh], ignore_index=True)
            static = pd.concat([static, fresh_static], ignore_index=True)
            metas.append(meta)

    if obs.empty:
        raise ProviderError("no verified observations are available")
    obs = (obs.drop_duplicates(["cell_id", "date"], keep="last")
              .sort_values(["cell_id", "date"]).reset_index(drop=True))
    static = static.drop_duplicates("cell_id", keep="last").sort_values("cell_id").reset_index(drop=True)
    latest = obs.groupby("cell_id")["date"].max()
    absent = wanted - set(latest[latest >= pd.Timestamp(obs_end)].index)
    if absent:
        log.warning("verified observations incomplete for %d cells; their confidence will be degraded", len(absent))
    _atomic_csv(obs, obs_file)
    _atomic_csv(static, static_file)
    return obs, static, _combined_meta(metas, local_path=obs_file)


def load_champion(paths: Paths):
    if not paths.champion_file.exists():
        return None
    ch = read_json(paths.champion_file)
    bundle = paths.versions / ch["version"]
    model, cal, meta = load_bundle(bundle)
    climate = meta.get("climatology_artifacts")
    if not isinstance(climate, dict) or not isinstance(climate.get("files"), dict):
        raise ValueError(f"champion {ch['version']} has no versioned climatology manifest")
    for name in CLIMATOLOGY_BUNDLE_FILES:
        artifact = bundle / name
        expected = climate["files"].get(name, {}).get("sha256")
        if not artifact.is_file() or not expected:
            raise ValueError(f"champion {ch['version']} is missing climatology artifact {name}")
        if sha256_file(artifact) != expected:
            raise ValueError(f"champion {ch['version']} climatology checksum mismatch: {name}")
    climatology = Climatology.load(bundle / "climatology.npz")
    return {"pointer": ch, "model": model, "calibrator": cal, "meta": meta,
            "climatology": climatology}


def vegetation_context(project_data: Path) -> dict[str, dict]:
    """Latest MODIS-based state from the existing near-real-time package: shown separately, NOT a model input."""
    out: dict[str, dict] = {}
    for f in sorted(project_data.glob("near_real_time_*/BADIA_968_16d_scored.csv")):
        d = pd.read_csv(f, dtype={"cell_id": str}, encoding="utf-8-sig")
        for r in d.itertuples():
            a = getattr(r, "ndvi_anomaly_current", np.nan)
            if not np.isfinite(a):
                continue
            ps = str(getattr(r, "modis_period_start", ""))
            out[str(r.cell_id)] = {
                "ndvi_anomaly": round(float(a), 5), "composite_start": ps,
                "composite_end": str((pd.Timestamp(ps) + pd.Timedelta(days=15)).date()) if ps and ps != "nan" else None,
                "state": "below_normal" if a < -VEG_TOLERANCE else "above_normal" if a > VEG_TOLERANCE else "near_normal",
                "medium_term_level_16d": getattr(r, "risk_level", None)}
    return out


def _reasons(row: pd.Series, contrib: pd.Series) -> dict:
    up = contrib[contrib > CONTRIB_MIN].sort_values(ascending=False).head(3)
    down = contrib[contrib < -CONTRIB_MIN].sort_values().head(2)

    def key(g: str, rising: bool) -> str:
        if g == "soil_moisture":
            return "soil_moisture_below_normal" if row.get("obs_sm_pct_last", 0.5) < 0.4 else "soil_moisture_state"
        if g == "recent_rain":
            low = row.get("obs_rain_30d_pct", 0.5) < 0.4 or row.get("obs_dry_spell_days", 0) > 20
            return "recent_rain_low" if low else "recent_rain_state"
        if g == "forecast_rain":
            return "forecast_rain_low" if row.get("fc_precip_cum_mm", 99) < 2.0 else "forecast_rain_state"
        if g == "heat":
            return "heat_elevated" if row.get("fc_tmax_pct", 0.5) > 0.6 else "heat_state"
        return "air_dryness_elevated" if row.get("fc_vpd_pct", 0.5) > 0.6 else "air_dryness_state"

    return {"drivers": [{"key": key(g, True), "group": g, "effect": round(float(v), 3)} for g, v in up.items()],
            "offsets": [{"key": key(g, False), "group": g, "effect": round(float(v), 3)} for g, v in down.items()]}


def _confidence(lead_metrics: dict | None, comp: float, forecast_age_h: float, obs_age_days: float) -> dict:
    skill = 0.5 if not lead_metrics else float(np.clip(lead_metrics.get("spearman", 0.5), 0, 1))
    fresh = float(np.clip(1 - forecast_age_h / (2 * FORECAST_STALE_HOURS), 0, 1)) * \
        float(np.clip(1 - max(obs_age_days - (OBS_LAG_DAYS + 2), 0) / 10, 0, 1))
    value = 0.4 * skill + 0.3 * comp + 0.3 * fresh
    return {"value": round(value, 2), "level": "high" if value >= 0.7 else "medium" if value >= 0.45 else "low",
            "components": {"validated_skill": round(skill, 2), "input_completeness": round(float(comp), 2),
                           "freshness": round(fresh, 2)}}


def build_snapshot(champion: dict, cells: pd.DataFrame, static: pd.DataFrame, clim: Climatology, obs: pd.DataFrame,
                   fc: pd.DataFrame, issue_day: date, fetched: dict, veg: dict[str, dict], now: datetime) -> dict:
    df = build_features(cells, obs, fc, clim, static=static, issue_days=[issue_day]).reset_index(drop=True)
    if df.empty:
        raise ProviderError("no forecast rows could be assembled for the issue day")
    expected = set(int(x) for x in LEADS)
    valid_cells: list[str] = []
    for cid, group in df.groupby("cell_id", sort=False):
        leads = [int(x) for x in group["lead_days"]]
        if len(leads) == len(expected) and len(set(leads)) == len(leads) and set(leads) == expected:
            valid_cells.append(str(cid))
    excluded = int(cells["cell_id"].astype(str).nunique() - len(valid_cells))
    df = df[df["cell_id"].astype(str).isin(valid_cells)].reset_index(drop=True)
    if df.empty:
        raise ProviderError("no cell has the complete unique Today-through-+7 horizon")
    X = feature_matrix(df)
    pred = champion["model"].predict(X)
    score = champion["calibrator"].score(pred)
    contrib = group_contributions(champion["model"], X)
    comp = completeness(df).to_numpy()
    df = df.assign(pred_esi=pred, score=score)
    by_lead = champion["meta"]["metrics"]["test"]["by_lead"]
    retrieved = fetched.get("forecast_retrieved_at") or fetched.get("forecast_fetched_at") or now.isoformat()
    fc_time = _as_utc(str(retrieved))
    f_age = max((now - fc_time).total_seconds() / 3600, 0)
    latest_obs = pd.Timestamp(fetched["latest_observation_date"]).date() if fetched.get("latest_observation_date") else None
    o_age = (amman_today(now) - latest_obs).days if latest_obs else 99
    out_cells: dict[str, dict] = {}
    for cid, g in df.groupby("cell_id", sort=False):
        g = g.sort_values("lead_days")
        today = g[g["lead_days"] == min(LEADS)]
        if len(today) != 1:  # defensive; exact horizon validation above should make this impossible
            continue
        today_idx = int(today.index[0])
        today_score = float(today.iloc[0]["score"])
        days = []
        for i, r in g.iterrows():
            rs = _reasons(r, contrib.loc[i])
            d_change = None
            if int(r["lead_days"]) > min(LEADS):
                delta = (contrib.loc[i] - contrib.loc[today_idx]).sort_values(key=np.abs, ascending=False).head(2)
                d_change = [{"group": k, "delta": round(float(v), 3)} for k, v in delta.items() if abs(v) > CONTRIB_MIN]
            days.append({"lead_days": int(r["lead_days"]), "date": str(r["target_date"].date()),
                         "score": round(float(r["score"]), 1), "level": risk_level(float(r["score"])),
                         "change_vs_today": round(float(r["score"]) - today_score, 1),
                         "predicted_esi": round(float(r["pred_esi"]), 3), **rs, "change_drivers": d_change,
                         "confidence": _confidence(by_lead.get(str(int(r["lead_days"]))), float(comp[i]), f_age, o_age)})
        c0 = g.iloc[0]
        out_cells[str(cid)] = {"latitude": round(float(c0["latitude"]), 5), "longitude": round(float(c0["longitude"]), 5),
                               "vegetation": veg.get(str(cid)), "days": days}
    source_stale = bool(fetched.get("forecast_stale"))
    state = "fresh" if f_age <= FORECAST_STALE_HOURS and not source_stale else "stale"
    issue_time = fetched.get("forecast_issue_time")  # Open-Meteo's generic endpoint does not currently provide it.
    return {
        "schema_version": SCHEMA_VERSION, "product": "BADIA Daily Environmental Stress Risk",
        "score_definition": "0-100 relative severity index: percentile of the forecast Environmental Stress Index within the "
                            "training-period distribution of observed values. NOT a probability.",
        "is_synthetic": False, "state": state, "source_state": state,
        "generated_at": now.isoformat(timespec="seconds"), "issued_at": issue_time,
        "forecast_reference_date": str(issue_day), "issue_day": str(issue_day),
        "covers": [str(issue_day + timedelta(days=int(L))) for L in LEADS],
        "freshness": {"forecast_retrieved_at": str(retrieved), "forecast_fetched_at": str(retrieved),
                      "forecast_issue_time": issue_time,
                      "forecast_issue_time_status": "provided" if issue_time else "not_provided_by_provider",
                      "forecast_reference_date": str(issue_day), "forecast_age_hours": round(f_age, 1),
                      "forecast_model": PROVIDERS["open_meteo_forecast"].notes,
                      "latest_observation_date": fetched.get("latest_observation_date"),
                      "observation_retrieved_at": fetched.get("observation_retrieved_at"),
                      "observation_source": "ERA5 reanalysis daily aggregates (delayed; not live)",
                      "source_stale": source_stale,
                      "latest_satellite_date": max((v["composite_end"] for v in veg.values() if v and v.get("composite_end")), default=None),
                      "satellite_source": "MODIS MOD13Q1 16-day composite (near-real-time, delayed)"},
        "model": {"version": champion["pointer"]["version"], "promoted_at": champion["pointer"].get("promoted_at"),
                  "test_window": champion["meta"]["info"]["windows"]},
        "quality": {"requested_cells": int(cells["cell_id"].astype(str).nunique()),
                    "forecast_cells": len(out_cells), "excluded_incomplete_horizon_cells": excluded,
                    "required_leads": list(LEADS)},
        "cells": out_cells}


def run_update(paths: Paths, cells: pd.DataFrame, *, client: Client | None = None, now: datetime | None = None,
               project_data: Path | None = None) -> dict:
    """Never raises for provider problems: falls back to the last good snapshot with an explicit state."""
    paths.ensure()
    now = now or _now()
    client = client or Client(paths.cache, cache_ttl_s=1800)
    status_file = paths.data / "update_status.json"
    previous_status = read_json(status_file) if status_file.exists() else {}
    try:
        champion = load_champion(paths)
        if champion is None:
            return {"state": "not_initialized",
                    "detail": "no champion model; run `python -m backend.app.daily.cli bootstrap`"}
        clim = champion["climatology"]
        issue = amman_today(now)
        obs_end = issue - timedelta(days=OBS_LAG_DAYS)
        obs, static, ometa = _live_observations(paths, client, cells, obs_end)
        fc, _, fmeta = providers.fetch_live(client, cells, issue)
        if obs.empty or fc.empty:
            raise ProviderError("empty provider response")
        latest_by_cell = obs.groupby("cell_id")["date"].max()
        fetched = {"forecast_retrieved_at": fmeta.get("fetched_at", now.isoformat(timespec="seconds")),
                   "forecast_issue_time": fmeta.get("forecast_issue_time"),
                   "forecast_stale": bool(fmeta.get("stale")),
                   "latest_observation_date": str(latest_by_cell.min().date()),
                   "observation_retrieved_at": ometa.get("fetched_at")}
        veg = vegetation_context(project_data or paths.data.parent)
        snap = build_snapshot(champion, cells, static, clim, obs, fc, issue, fetched, veg, now)
        snap["freshness"]["last_successful_update"] = now.isoformat(timespec="seconds")
        write_json_atomic(paths.snapshots / f"forecast_{issue}.json", snap)
        write_json_atomic(paths.snapshots / "latest.json", snap)
        if snap["state"] == "fresh":
            write_json_atomic(paths.snapshots / "last_good.json", snap)
        write_json_atomic(status_file, {"state": snap["state"], "last_attempt_at": now.isoformat(timespec="seconds"),
                                        "last_successful_update": now.isoformat(timespec="seconds"),
                                        "last_fresh_update": (now.isoformat(timespec="seconds") if snap["state"] == "fresh"
                                                              else previous_status.get("last_fresh_update")),
                                        "provider_error": None})
        log.info("snapshot written issue=%s state=%s cells=%d", issue, snap["state"], len(snap["cells"]))
        return {"state": snap["state"], "issue_day": str(issue), "cells": len(snap["cells"])}
    except Exception as exc:  # noqa: BLE001 - deliberate: serve last good data instead of failing
        message = f"{type(exc).__name__}: {exc}"
        log.error("update failed (%s); falling back to last good snapshot", message)
        fallback_exists = any((paths.snapshots / name).exists() for name in ("latest.json", "last_good.json"))
        state = "fallback" if fallback_exists else "unavailable"
        write_json_atomic(status_file, {"state": state, "last_attempt_at": now.isoformat(timespec="seconds"),
                                        "last_successful_update": previous_status.get("last_successful_update"),
                                        "last_fresh_update": previous_status.get("last_fresh_update"),
                                        "provider_error": message})
        return {"state": state, "error": message, "has_last_good": fallback_exists}


def serve_snapshot(paths: Paths, now: datetime | None = None) -> dict:
    """What the API returns: latest -> last_good -> explicit not-available. Staleness is recomputed at read time."""
    now = now or _now()
    status_file = paths.data / "update_status.json"
    update_status = read_json(status_file) if status_file.exists() else {}
    for name in ("latest.json", "last_good.json"):
        f = paths.snapshots / name
        if f.exists():
            snap = read_json(f)
            generated = snap.get("generated_at") or snap.get("issued_at")
            age_h = (now - _as_utc(generated)).total_seconds() / 3600
            intrinsic = snap.get("source_state", snap.get("state", "fresh"))
            failed_after_snapshot = update_status.get("state") in {"fallback", "unavailable"} and \
                bool(update_status.get("provider_error"))
            if age_h > SNAPSHOT_EXPIRE_HOURS:
                state = "expired"
            elif failed_after_snapshot:
                state = "fallback"
            elif intrinsic == "stale" or age_h > FORECAST_STALE_HOURS:
                state = "stale"
            else:
                state = "fresh"
            snap["state"] = state
            snap["snapshot_age_hours"] = round(age_h, 1)
            snap["served_from"] = name
            snap["provider_status"] = "unavailable" if failed_after_snapshot else "available"
            snap["last_update_error"] = update_status.get("provider_error")
            snap["last_successful_update"] = update_status.get("last_successful_update") or \
                snap.get("freshness", {}).get("last_successful_update")
            return snap
    if paths.champion_file.exists() and update_status.get("state") == "unavailable":
        return {"state": "unavailable", "is_synthetic": False, "cells": {},
                "last_update_error": update_status.get("provider_error"),
                "detail": "A champion exists, but no forecast snapshot could be generated."}
    return {"state": "not_initialized", "is_synthetic": False, "cells": {},
            "detail": "No daily forecast has been generated yet."}
