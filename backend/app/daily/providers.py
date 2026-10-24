"""Open-Meteo adapters that return deterministic, tidy daily frames.

Training observations use provider-native ERA5 daily aggregates. Archived forecast
inputs remain hourly because Previous Runs exposes the selected ECMWF fields that way;
they are reduced with the same local daily rules used for current forecasts.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

from .config import (
    DAILY_OBS_VARS,
    FORECAST_MODEL,
    HOURLY_FC_VARS,
    ISSUE_TIME_CONTRACT,
    LEADS,
    OBS_LAG_DAYS,
    TIMEZONE,
)
from .http import Client, ProviderError

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
PREVIOUS_RUNS_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
SPATIAL_CHUNK = 40
PREVIOUS_RUNS_SPATIAL_CHUNK = 10
ARCHIVE_DATE_CHUNK_DAYS = 366
FORECAST_DATE_CHUNK_DAYS = 31


def vpd_kpa(temp_c: np.ndarray, dew_c: np.ndarray) -> np.ndarray:
    es = 0.6108 * np.exp(17.27 * temp_c / (temp_c + 237.3))
    ea = 0.6108 * np.exp(17.27 * dew_c / (dew_c + 237.3))
    return np.clip(es - ea, 0.0, None)


def _chunks(seq: Sequence, n: int) -> Iterable[Sequence]:
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def _date_chunks(start: date, end: date, days: int | None) -> Iterable[tuple[date, date]]:
    if end < start:
        raise ValueError(f"end date {end} precedes start date {start}")
    if not days or days <= 0:
        yield start, end
        return
    cursor = start
    while cursor <= end:
        chunk_end = min(end, cursor + timedelta(days=days - 1))
        yield cursor, chunk_end
        cursor = chunk_end + timedelta(days=1)


def _as_list(payload) -> list[dict]:
    return payload if isinstance(payload, list) else [payload]


def _parsed_timestamp(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def merge_metadata(metas: Iterable[dict]) -> dict:
    """Collapse chunk metadata pessimistically (oldest timestamp, worst flags)."""
    items = [dict(m) for m in metas if m]
    if not items:
        return {}
    times = [(t, str(m.get("fetched_at"))) for m in items if (t := _parsed_timestamp(m.get("fetched_at")))]
    hosts = sorted({str(m["host"]) for m in items if m.get("host")})
    out = {
        "host": hosts[0] if len(hosts) == 1 else ",".join(hosts),
        "hosts": hosts,
        "chunks": len(items),
        "from_cache": any(bool(m.get("from_cache")) for m in items),
        "all_from_cache": all(bool(m.get("from_cache")) for m in items),
        "stale": any(bool(m.get("stale")) for m in items),
        "stale_chunks": sum(bool(m.get("stale")) for m in items),
        "cache_chunks": sum(bool(m.get("from_cache")) for m in items),
    }
    if times:
        out["fetched_at"] = min(times, key=lambda x: x[0])[1]
        out["freshest_fetched_at"] = max(times, key=lambda x: x[0])[1]
    return out


def _daily_from_hourly(hourly: dict, suffix: str = "") -> pd.DataFrame:
    """Reduce one forecast location to complete local-calendar days."""
    try:
        timestamps = pd.to_datetime(hourly["time"])
        get = lambda name: np.asarray(hourly[name + suffix], dtype=float)  # noqa: E731
        temp, dew, precip = get("temperature_2m"), get("dew_point_2m"), get("precipitation")
    except KeyError as exc:
        raise ProviderError(f"forecast response missing variable {exc}") from exc
    if not (len(timestamps) == len(temp) == len(dew) == len(precip)):
        raise ProviderError("forecast response arrays have inconsistent lengths")
    df = pd.DataFrame({"time": timestamps, "temp": temp, "dew": dew, "precip": precip})
    df["vpd"] = vpd_kpa(temp, dew)
    df["date"] = df["time"].dt.normalize()
    agg = df.groupby("date", sort=True).agg(
        precip_mm=("precip", lambda s: s.sum(min_count=18)),
        tmax_c=("temp", "max"),
        tmin_c=("temp", "min"),
        tmean_c=("temp", "mean"),
        vpd_max_kpa=("vpd", "max"),
    )
    counts = df.groupby("date")[["temp", "dew", "precip"]].count().min(axis=1)
    return agg[counts.reindex(agg.index).ge(18)].reset_index()


def _daily_observations(daily: dict) -> pd.DataFrame:
    """Parse provider-native ERA5 daily aggregates into the established schema."""
    mapping = {
        "precipitation_sum": "precip_mm",
        "temperature_2m_max": "tmax_c",
        "temperature_2m_min": "tmin_c",
        "temperature_2m_mean": "tmean_c",
        "vapour_pressure_deficit_max": "vpd_max_kpa",
        "soil_moisture_0_to_7cm_mean": "sm_0_7",
    }
    try:
        values = {target: np.asarray(daily[source], dtype=float) for source, target in mapping.items()}
        timestamps = pd.to_datetime(daily["time"])
    except KeyError as exc:
        raise ProviderError(f"ERA5 daily response missing variable {exc}") from exc
    lengths = {len(timestamps), *(len(value) for value in values.values())}
    if len(lengths) != 1:
        raise ProviderError("ERA5 daily response arrays have inconsistent lengths")
    return pd.DataFrame({"date": timestamps, **values})


def fetch_archive(
    client: Client,
    cells: pd.DataFrame,
    start: date,
    end: date,
    *,
    date_chunk_days: int | None = ARCHIVE_DATE_CHUNK_DAYS,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Fetch provider-native ERA5 daily observations in bounded time/space chunks."""
    rows: list[pd.DataFrame] = []
    static: list[dict] = []
    metas: list[dict] = []
    records = list(cells.itertuples(index=False))
    for chunk_start, chunk_end in _date_chunks(start, end, date_chunk_days):
        for spatial in _chunks(records, SPATIAL_CHUNK):
            params = {
                "latitude": ",".join(f"{float(cell.latitude):.4f}" for cell in spatial),
                "longitude": ",".join(f"{float(cell.longitude):.4f}" for cell in spatial),
                "start_date": chunk_start.isoformat(),
                "end_date": chunk_end.isoformat(),
                "daily": ",".join(DAILY_OBS_VARS),
                "models": "era5",
                "timezone": TIMEZONE,
            }
            payload, meta = client.get_json(
                ARCHIVE_URL,
                params,
                immutable=chunk_end < date.today() - timedelta(days=OBS_LAG_DAYS + 30),
            )
            metas.append(meta)
            items = _as_list(payload)
            if len(items) != len(spatial):
                raise ProviderError(f"archive returned {len(items)} locations for {len(spatial)} requested")
            for cell, item in zip(spatial, items):
                daily = _daily_observations(item.get("daily", {}))
                daily.insert(0, "cell_id", str(cell.cell_id))
                rows.append(daily)
                static.append({"cell_id": str(cell.cell_id), "elevation_m": item.get("elevation", np.nan)})
    obs = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    if len(obs):
        obs = obs.drop_duplicates(["cell_id", "date"], keep="last").sort_values(["cell_id", "date"]).reset_index(drop=True)
    static_df = pd.DataFrame(static).drop_duplicates("cell_id", keep="last") if static else pd.DataFrame()
    return obs, static_df.reset_index(drop=True), merge_metadata(metas)


def fetch_previous_runs(
    client: Client,
    cells: pd.DataFrame,
    start: date,
    end: date,
    leads: Sequence[int] = LEADS,
    *,
    date_chunk_days: int | None = FORECAST_DATE_CHUNK_DAYS,
) -> tuple[pd.DataFrame, dict]:
    """Fetch fixed-offset archived forecasts for valid dates.

    The unsuffixed reference run plus ``previous_day1..7`` form a fixed
    24-hour-offset approximation. They are not evidence of exact model-run issue
    timestamps.
    """
    leads = tuple(int(lead) for lead in leads)
    if any(lead not in LEADS for lead in leads):
        raise ValueError(f"leads must be a subset of {LEADS}")
    out: list[pd.DataFrame] = []
    metas: list[dict] = []
    records = list(cells.itertuples(index=False))
    # The Previous Runs API exposes the reference run with the ordinary variable
    # name; only older runs carry ``_previous_dayN``.  Asking for day0 is accepted
    # by the API but its response is still unsuffixed.
    hourly = [variable if lead == 0 else f"{variable}_previous_day{lead}"
              for lead in leads for variable in HOURLY_FC_VARS]
    for chunk_start, chunk_end in _date_chunks(start, end, date_chunk_days):
        for spatial in _chunks(records, PREVIOUS_RUNS_SPATIAL_CHUNK):
            params = {
                "latitude": ",".join(f"{float(cell.latitude):.4f}" for cell in spatial),
                "longitude": ",".join(f"{float(cell.longitude):.4f}" for cell in spatial),
                "start_date": chunk_start.isoformat(),
                "end_date": chunk_end.isoformat(),
                "hourly": ",".join(hourly),
                "models": FORECAST_MODEL,
                "timezone": TIMEZONE,
            }
            payload, meta = client.get_json(
                PREVIOUS_RUNS_URL,
                params,
                immutable=chunk_end < date.today() - timedelta(days=3),
            )
            metas.append(meta)
            items = _as_list(payload)
            if len(items) != len(spatial):
                raise ProviderError(f"previous-runs returned {len(items)} locations for {len(spatial)} requested")
            for cell, item in zip(spatial, items):
                for lead in leads:
                    suffix = "" if lead == 0 else f"_previous_day{lead}"
                    daily = _daily_from_hourly(item.get("hourly", {}), suffix)
                    daily.insert(0, "lead_days", lead)
                    daily.insert(0, "cell_id", str(cell.cell_id))
                    out.append(daily.rename(columns={"date": "valid_date"}))
    frame = pd.concat(out, ignore_index=True) if out else pd.DataFrame()
    if len(frame):
        frame = (
            frame.dropna(subset=["tmax_c", "precip_mm"])
            .drop_duplicates(["cell_id", "valid_date", "lead_days"], keep="last")
            .sort_values(["cell_id", "valid_date", "lead_days"])
            .reset_index(drop=True)
        )
    meta = merge_metadata(metas)
    meta["issue_time_contract"] = ISSUE_TIME_CONTRACT
    meta["lead_offsets"] = list(leads)
    return frame, meta


def fetch_live(client: Client, cells: pd.DataFrame, issue: date) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Fetch the current run for reference day ``issue`` and horizons Today through +7."""
    fc_rows: list[pd.DataFrame] = []
    recent_rows: list[pd.DataFrame] = []
    metas: list[dict] = []
    records = list(cells.itertuples(index=False))
    for spatial in _chunks(records, SPATIAL_CHUNK):
        params = {
            "latitude": ",".join(f"{float(cell.latitude):.4f}" for cell in spatial),
            "longitude": ",".join(f"{float(cell.longitude):.4f}" for cell in spatial),
            "hourly": ",".join(HOURLY_FC_VARS),
            "models": FORECAST_MODEL,
            "timezone": TIMEZONE,
            "forecast_days": max(LEADS) + 1,
        }
        payload, meta = client.get_json(FORECAST_URL, params)
        metas.append(meta)
        items = _as_list(payload)
        if len(items) != len(spatial):
            raise ProviderError(f"forecast returned {len(items)} locations for {len(spatial)} requested")
        for cell, item in zip(spatial, items):
            daily = _daily_from_hourly(item.get("hourly", {}))
            daily.insert(0, "cell_id", str(cell.cell_id))
            daily["lead_days"] = (daily["date"] - pd.Timestamp(issue)).dt.days
            fc_rows.append(daily[daily["lead_days"].isin(LEADS)].rename(columns={"date": "valid_date"}))
            recent_rows.append(daily[daily["lead_days"] < min(LEADS)])
    fc = pd.concat(fc_rows, ignore_index=True) if fc_rows else pd.DataFrame()
    recent = pd.concat(recent_rows, ignore_index=True) if recent_rows else pd.DataFrame()
    if len(fc):
        fc = fc.sort_values(["cell_id", "valid_date"]).reset_index(drop=True)
    meta = merge_metadata(metas)
    meta["issue_time_contract"] = "current_run_reference_day"
    meta["reference_day"] = issue.isoformat()
    return fc, recent, meta
