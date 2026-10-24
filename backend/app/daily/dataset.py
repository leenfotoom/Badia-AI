"""Bounded, resumable construction of leakage-aware daily training artifacts."""
from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from . import providers
from .climatology import Climatology
from .config import (
    CLIM_YEARS,
    FORECAST_MODEL,
    ISSUE_TIME_CONTRACT,
    LEADS,
    OBS_LAG_DAYS,
    PROVIDERS,
    SCHEMA_VERSION,
)
from .http import Client
from .store import Paths, read_json, sha256_file, write_csv_atomic, write_json_atomic

log = logging.getLogger("badia.daily.dataset")
# A live one-cell Jordan probe on 2026-10-06 found 2024-03-07 to be the first
# valid date for which ECMWF IFS 0.25° Previous Runs returned every required
# field at every fixed offset (day 0 through day 7).  Earlier dates must not be
# admitted merely because the provider has partial model coverage.
FC_ARCHIVE_START = date(2024, 3, 7)
OBS_PRELOAD_DAYS = 100
DEFAULT_TRAIN_CELLS = 24
DEFAULT_OBSERVATION_CHUNK_DAYS = 366
DEFAULT_FORECAST_CHUNK_DAYS = 31

OBS_FILE = "obs_daily.csv.gz"
FORECAST_FILE = "forecast_prev.csv.gz"
STATIC_FILE = "static.csv"
CELLS_FILE = "cells.csv"
DATA_FILES = (OBS_FILE, FORECAST_FILE, STATIC_FILE, CELLS_FILE)
FORECAST_EXCLUDED_DATES_FIELD = "excluded_forecast_valid_dates"
FORECAST_OUTAGE_POLICY = (
    "Exclude a whole valid date only when every missing (valid_date, lead_days) combination "
    "is absent for every requested cell; reject any partial-cell gap and never fill values."
)

MIN_PLAUSIBLE_TEMP_C = -100.0
MAX_PLAUSIBLE_TEMP_C = 70.0
SOIL_MOISTURE_ROUNDOFF_TOLERANCE = 0.01


def load_cells(project_dir: Path) -> pd.DataFrame:
    source = Path(project_dir) / "data" / "near_real_time_2026_08_28" / "BADIA_968_16d_scored.csv"
    cells = pd.read_csv(source, dtype={"cell_id": str}, encoding="utf-8-sig")
    return _normalise_cells(cells[["cell_id", "latitude", "longitude"]])


def _normalise_cells(cells: pd.DataFrame) -> pd.DataFrame:
    required = {"cell_id", "latitude", "longitude"}
    if not required.issubset(cells.columns):
        raise ValueError(f"cells missing columns {sorted(required - set(cells.columns))}")
    out = cells[["cell_id", "latitude", "longitude"]].copy()
    out["cell_id"] = out["cell_id"].astype(str)
    out["latitude"] = pd.to_numeric(out["latitude"], errors="coerce")
    out["longitude"] = pd.to_numeric(out["longitude"], errors="coerce")
    if out.empty or out["cell_id"].duplicated().any() or not np.isfinite(out[["latitude", "longitude"]]).all().all():
        raise ValueError("cells must be non-empty, unique and have finite coordinates")
    return out.sort_values("cell_id").reset_index(drop=True)


def select_training_cells(cells: pd.DataFrame, n: int = DEFAULT_TRAIN_CELLS) -> pd.DataFrame:
    """Select a small deterministic, spatially distributed anchor set."""
    cells = _normalise_cells(cells)
    if n <= 0:
        raise ValueError("training-cell count must be positive")
    if n >= len(cells):
        return cells
    ordered = cells.sort_values(["latitude", "longitude", "cell_id"]).reset_index(drop=True)
    bands = max(int(np.sqrt(n / 2)), 1)
    ordered["lat_bin"] = pd.qcut(ordered["latitude"], bands, labels=False, duplicates="drop")
    selected = []
    per_band = int(np.ceil(n / ordered["lat_bin"].nunique()))
    for _, group in ordered.groupby("lat_bin", sort=True):
        group = group.sort_values(["longitude", "cell_id"])
        positions = np.linspace(0, len(group) - 1, min(per_band, len(group))).round().astype(int)
        selected.append(group.iloc[positions])
    result = pd.concat(selected).drop_duplicates("cell_id").head(n).drop(columns="lat_bin")
    if len(result) < n:  # Fill rare qcut/rounding shortfalls deterministically.
        remaining = ordered[~ordered["cell_id"].isin(result["cell_id"])].head(n - len(result)).drop(columns="lat_bin")
        result = pd.concat([result, remaining], ignore_index=True)
    return result.sort_values("cell_id").reset_index(drop=True)


def _cell_signature(cells: pd.DataFrame) -> str:
    canonical = _normalise_cells(cells).to_csv(index=False, lineterminator="\n", float_format="%.8f")
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _date_chunks(start: date, end: date, days: int) -> Iterable[tuple[date, date]]:
    if days <= 0:
        raise ValueError("date chunk size must be positive")
    if end < start:
        raise ValueError(f"end date {end} precedes start date {start}")
    cursor = start
    while cursor <= end:
        chunk_end = min(end, cursor + timedelta(days=days - 1))
        yield cursor, chunk_end
        cursor = chunk_end + timedelta(days=1)


def _part_paths(directory: Path, kind: str, signature: str, start: date, end: date) -> tuple[Path, Path]:
    data = directory / f"{kind}_{signature}_{start:%Y%m%d}_{end:%Y%m%d}.csv.gz"
    return data, directory / f"{data.name}.meta.json"


def _load_part(data_path: Path, meta_path: Path, expected: dict) -> tuple[pd.DataFrame, dict] | None:
    if not data_path.exists() or not meta_path.exists():
        return None
    try:
        meta = read_json(meta_path)
        if any(meta.get(key) != value for key, value in expected.items()):
            return None
        if meta.get("sha256") != sha256_file(data_path):
            log.warning("part checksum mismatch; reacquiring %s", data_path.name)
            return None
        frame = pd.read_csv(data_path, dtype={"cell_id": str})
        if int(meta.get("rows", -1)) != len(frame):
            log.warning("part row count mismatch; reacquiring %s", data_path.name)
            return None
        return frame, meta
    except (OSError, ValueError, KeyError, pd.errors.ParserError) as exc:
        log.warning("unreadable acquisition part %s; reacquiring (%s)", data_path.name, exc)
        return None


def _write_part(frame: pd.DataFrame, data_path: Path, meta_path: Path, metadata: dict) -> dict:
    write_csv_atomic(frame, data_path, index=False)
    complete = {**metadata, "rows": int(len(frame)), "sha256": sha256_file(data_path),
                "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    write_json_atomic(meta_path, complete)
    return complete


def _normalise_excluded_dates(values, start: date, end: date, *, field: str) -> list[date]:
    """Parse a persisted outage-date list and require a canonical in-range set."""
    if values is None:
        values = []
    if not isinstance(values, (list, tuple, set)):
        raise ValueError(f"{field} must be a list of ISO dates")
    parsed: list[date] = []
    for value in values:
        try:
            parsed.append(date.fromisoformat(str(value)))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field} contains an invalid ISO date: {value!r}") from exc
    if len(parsed) != len(set(parsed)):
        raise ValueError(f"{field} contains duplicate dates")
    outside = [value for value in parsed if value < start or value > end]
    if outside:
        raise ValueError(f"{field} contains dates outside {start}..{end}: {outside[:3]}")
    return sorted(parsed)


def _numeric_columns(frame: pd.DataFrame, columns: list[str], *, kind: str) -> pd.DataFrame:
    """Coerce provider numerics and reject missing/infinite values explicitly."""
    numeric = frame[columns].apply(pd.to_numeric, errors="coerce")
    finite = np.isfinite(numeric.to_numpy(dtype=float))
    if not finite.all():
        bad_columns = [column for column, ok in zip(columns, finite.all(axis=0)) if not ok]
        raise ValueError(f"{kind} data contain non-finite values in {bad_columns}")
    frame[columns] = numeric
    return frame


def _validate_weather_values(frame: pd.DataFrame, *, kind: str, soil: bool) -> None:
    """Reject impossible values; normalize only documented ERA5 round-off."""
    if (frame["precip_mm"] < 0).any():
        raise ValueError(f"{kind} data contain negative precipitation")
    if (frame["vpd_max_kpa"] < 0).any():
        raise ValueError(f"{kind} data contain negative VPD")
    temperature = frame[["tmin_c", "tmean_c", "tmax_c"]]
    if ((temperature < MIN_PLAUSIBLE_TEMP_C) | (temperature > MAX_PLAUSIBLE_TEMP_C)).any().any():
        raise ValueError(
            f"{kind} data contain temperatures outside the conservative "
            f"[{MIN_PLAUSIBLE_TEMP_C:g}, {MAX_PLAUSIBLE_TEMP_C:g}] °C bounds"
        )
    if (frame["tmin_c"] > frame["tmax_c"]).any():
        raise ValueError(f"{kind} data contain tmin greater than tmax")
    if ((frame["tmean_c"] < frame["tmin_c"]) | (frame["tmean_c"] > frame["tmax_c"])).any():
        raise ValueError(f"{kind} data contain tmean outside the daily min/max interval")
    if soil:
        sm = frame["sm_0_7"]
        if ((sm < -SOIL_MOISTURE_ROUNDOFF_TOLERANCE) |
                (sm > 1 + SOIL_MOISTURE_ROUNDOFF_TOLERANCE)).any():
            raise ValueError(f"{kind} data contain soil moisture outside the volumetric [0, 1] range")
        clipped = int(((sm < 0) | (sm > 1)).sum())
        if clipped:
            log.info("clipping %d ERA5 soil-moisture round-off values to [0, 1]", clipped)
            frame["sm_0_7"] = sm.clip(0, 1)


def _require_complete_daily_grid(frame: pd.DataFrame, cells: pd.DataFrame, start: date, end: date,
                                 *, date_column: str, kind: str,
                                 excluded_dates: Iterable[date] = ()) -> None:
    """Require every requested cell/date pair; an absent whole day is still a gap."""
    excluded = set(excluded_dates)
    retained_dates = [when for when in pd.date_range(start, end, freq="D") if when.date() not in excluded]
    expected = pd.MultiIndex.from_product(
        [_normalise_cells(cells)["cell_id"], retained_dates],
        names=["cell_id", date_column],
    )
    actual = pd.MultiIndex.from_frame(frame[["cell_id", date_column]])
    missing = expected.difference(actual)
    if len(missing):
        sample = [f"{cell}/{when:%Y-%m-%d}" for cell, when in missing[:3]]
        raise ValueError(f"{kind} coverage is missing {len(missing)} requested cell/date groups; sample={sample}")


def _validate_observations(frame: pd.DataFrame, cells: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    columns = ["cell_id", "date", "precip_mm", "tmax_c", "tmin_c", "tmean_c", "vpd_max_kpa", "sm_0_7"]
    required = set(columns)
    if not required.issubset(frame.columns):
        raise ValueError(f"observation data missing columns {sorted(required - set(frame.columns))}")
    out = frame[columns].copy()
    out["cell_id"] = out["cell_id"].astype(str)
    out["date"] = pd.to_datetime(out["date"]).dt.normalize()
    numeric = ["precip_mm", "tmax_c", "tmin_c", "tmean_c", "vpd_max_kpa", "sm_0_7"]
    out = _numeric_columns(out, numeric, kind="observation")
    _validate_weather_values(out, kind="observation", soil=True)
    valid_cells = set(_normalise_cells(cells)["cell_id"])
    if set(out["cell_id"]) - valid_cells:
        raise ValueError("observation provider returned unrequested cells")
    if len(out) and (out["date"].min().date() < start or out["date"].max().date() > end):
        raise ValueError("observation provider returned dates outside the request")
    if out.duplicated(["cell_id", "date"]).any():
        raise ValueError("duplicate observation cell/date rows")
    _require_complete_daily_grid(out, cells, start, end, date_column="date", kind="observation")
    return out.sort_values(["cell_id", "date"]).reset_index(drop=True)


def _validate_forecasts(frame: pd.DataFrame, cells: pd.DataFrame, start: date, end: date, *,
                        excluded_dates: Iterable[str | date] = ()) -> pd.DataFrame:
    """Validate a complete retained forecast grid, accounting for declared provider-wide outages."""
    excluded = _normalise_excluded_dates(
        list(excluded_dates), start, end, field=FORECAST_EXCLUDED_DATES_FIELD
    )
    retained_dates = [when for when in pd.date_range(start, end, freq="D") if when.date() not in set(excluded)]
    columns = ["cell_id", "valid_date", "lead_days", "precip_mm", "tmax_c", "tmin_c", "tmean_c", "vpd_max_kpa"]
    required = set(columns)
    if not required.issubset(frame.columns):
        raise ValueError(f"forecast data missing columns {sorted(required - set(frame.columns))}")
    out = frame[columns].copy()
    out["cell_id"] = out["cell_id"].astype(str)
    out["valid_date"] = pd.to_datetime(out["valid_date"]).dt.normalize()
    out["lead_days"] = pd.to_numeric(out["lead_days"], errors="raise").astype(int)
    numeric = ["precip_mm", "tmax_c", "tmin_c", "tmean_c", "vpd_max_kpa"]
    out = _numeric_columns(out, numeric, kind="forecast")
    _validate_weather_values(out, kind="forecast", soil=False)
    if set(out["lead_days"]) - set(LEADS):
        raise ValueError("forecast provider returned unsupported lead offsets")
    valid_cells = set(_normalise_cells(cells)["cell_id"])
    if set(out["cell_id"]) - valid_cells:
        raise ValueError("forecast provider returned unrequested cells")
    if len(out) and (out["valid_date"].min().date() < start or out["valid_date"].max().date() > end):
        raise ValueError("forecast provider returned dates outside the request")
    present_excluded = sorted(set(out["valid_date"].dt.date) & set(excluded))
    if present_excluded:
        raise ValueError(f"forecast data contain rows for declared excluded dates: {present_excluded[:3]}")
    if out.duplicated(["cell_id", "valid_date", "lead_days"]).any():
        raise ValueError("duplicate forecast cell/date/lead rows")
    found_leads = set(out["lead_days"])
    if retained_dates and found_leads != set(LEADS):
        raise ValueError(f"forecast data must contain exactly the required leads {LEADS}; found {sorted(found_leads)}")
    _require_complete_daily_grid(
        out, cells, start, end, date_column="valid_date", kind="forecast", excluded_dates=excluded
    )
    expected = pd.MultiIndex.from_product(
        [_normalise_cells(cells)["cell_id"], retained_dates, LEADS],
        names=["cell_id", "valid_date", "lead_days"],
    )
    actual = pd.MultiIndex.from_frame(out[["cell_id", "valid_date", "lead_days"]])
    missing = expected.difference(actual)
    if len(missing):
        sample = [f"{cell}/{when:%Y-%m-%d}/lead={lead}" for cell, when, lead in missing[:3]]
        raise ValueError(f"forecast coverage is missing {len(missing)} required cell/date/lead rows; sample={sample}")
    return out.sort_values(["cell_id", "valid_date", "lead_days"]).reset_index(drop=True)


def _exclude_provider_wide_forecast_outages(frame: pd.DataFrame, cells: pd.DataFrame,
                                             start: date, end: date) -> tuple[pd.DataFrame, list[str]]:
    """Remove whole valid dates only for strictly provider-wide missing combinations.

    For any missing ``(valid_date, lead_days)`` combination, every requested cell must
    be missing.  A gap affecting even one-but-not-all cells is a local/data-integrity
    failure and aborts acquisition.  Once a date qualifies, all of its rows are removed
    so every retained valid date continues to have the exact cell x lead grid.  Values
    are never synthesized or filled.
    """
    keys = {"cell_id", "valid_date", "lead_days"}
    if not keys.issubset(frame.columns):
        raise ValueError(f"forecast data missing columns {sorted(keys - set(frame.columns))}")
    keyed = frame.copy()
    keyed["cell_id"] = keyed["cell_id"].astype(str)
    keyed["valid_date"] = pd.to_datetime(keyed["valid_date"], errors="raise").dt.normalize()
    keyed["lead_days"] = pd.to_numeric(keyed["lead_days"], errors="raise").astype(int)
    requested_cells = set(_normalise_cells(cells)["cell_id"])
    extra_cells = set(keyed["cell_id"]) - requested_cells
    if extra_cells:
        raise ValueError(f"forecast provider returned unrequested cells: {sorted(extra_cells)[:3]}")
    extra_leads = set(keyed["lead_days"]) - set(LEADS)
    if extra_leads:
        raise ValueError(f"forecast provider returned unsupported lead offsets: {sorted(extra_leads)}")
    if len(keyed) and (keyed["valid_date"].min().date() < start or keyed["valid_date"].max().date() > end):
        raise ValueError("forecast provider returned dates outside the request")
    if keyed.duplicated(["cell_id", "valid_date", "lead_days"]).any():
        raise ValueError("duplicate forecast cell/date/lead rows")

    excluded: set[date] = set()
    for when in pd.date_range(start, end, freq="D"):
        day = keyed[keyed["valid_date"] == when]
        for lead in LEADS:
            present = set(day.loc[day["lead_days"] == lead, "cell_id"])
            missing = requested_cells - present
            if missing and missing != requested_cells:
                sample = sorted(missing)[:3]
                raise ValueError(
                    "forecast gap is not provider-wide: "
                    f"{when:%Y-%m-%d} lead={lead} is missing {len(missing)}/{len(requested_cells)} "
                    f"cells; sample={sample}"
                )
            if missing:
                excluded.add(when.date())

    excluded_strings = [value.isoformat() for value in sorted(excluded)]
    retained = keyed[~keyed["valid_date"].dt.date.isin(excluded)].copy()
    retained = _validate_forecasts(retained, cells, start, end, excluded_dates=excluded_strings)
    if excluded_strings:
        log.warning(
            "excluding %d provider-wide Previous Runs outage dates: %s",
            len(excluded_strings), ",".join(excluded_strings),
        )
    return retained, excluded_strings


def _acquire_archive_parts(client: Client, cells: pd.DataFrame, start: date, end: date, directory: Path,
                           *, kind: str, chunk_days: int) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    directory.mkdir(parents=True, exist_ok=True)
    cells = _normalise_cells(cells)
    signature = _cell_signature(cells)
    frames, statics, metadata = [], [], []
    reused = fetched = 0
    for chunk_start, chunk_end in _date_chunks(start, end, chunk_days):
        data_path, meta_path = _part_paths(directory, kind, signature, chunk_start, chunk_end)
        expected = {"part_format": 1, "schema_version": SCHEMA_VERSION, "kind": kind,
                    "cell_signature": signature, "start_date": str(chunk_start), "end_date": str(chunk_end),
                    "provider_model": "era5"}
        loaded = _load_part(data_path, meta_path, expected)
        if loaded is None:
            frame, static, provider_meta = providers.fetch_archive(
                client, cells, chunk_start, chunk_end, date_chunk_days=None)
            frame = _validate_observations(frame, cells, chunk_start, chunk_end)
            static = static[["cell_id", "elevation_m"]].copy()
            static["cell_id"] = static["cell_id"].astype(str)
            part_meta = _write_part(frame, data_path, meta_path, {
                **expected,
                "provider": provider_meta,
                "static": static.to_dict(orient="records"),
            })
            fetched += 1
        else:
            frame, part_meta = loaded
            frame = _validate_observations(frame, cells, chunk_start, chunk_end)
            static = pd.DataFrame(part_meta.get("static", []), columns=["cell_id", "elevation_m"])
            reused += 1
        frames.append(frame)
        statics.append(static)
        metadata.append(part_meta)
    observations = pd.concat(frames, ignore_index=True)
    observations = _validate_observations(observations, cells, start, end)
    static = pd.concat(statics, ignore_index=True)
    static["cell_id"] = static["cell_id"].astype(str)
    static = static.drop_duplicates("cell_id", keep="last").sort_values("cell_id").reset_index(drop=True)
    if set(static["cell_id"]) != set(cells["cell_id"]):
        raise ValueError("archive response did not provide static elevation for every requested cell")
    provider_meta = providers.merge_metadata(part.get("provider", {}) for part in metadata)
    provider_meta.update({"parts": len(metadata), "parts_reused": reused, "parts_fetched": fetched,
                          "cell_signature": signature})
    return observations, static, provider_meta


def _acquire_forecast_parts(client: Client, cells: pd.DataFrame, start: date, end: date, directory: Path,
                            *, chunk_days: int) -> tuple[pd.DataFrame, dict]:
    directory.mkdir(parents=True, exist_ok=True)
    cells = _normalise_cells(cells)
    signature = _cell_signature(cells)
    frames, metadata = [], []
    reused = fetched = 0
    for chunk_start, chunk_end in _date_chunks(start, end, chunk_days):
        data_path, meta_path = _part_paths(directory, "forecasts", signature, chunk_start, chunk_end)
        expected = {"part_format": 1, "schema_version": SCHEMA_VERSION, "kind": "forecasts",
                    "cell_signature": signature, "start_date": str(chunk_start), "end_date": str(chunk_end),
                    "forecast_model": FORECAST_MODEL, "leads": list(LEADS),
                    "issue_time_contract": ISSUE_TIME_CONTRACT}
        loaded = _load_part(data_path, meta_path, expected)
        if loaded is None:
            frame, provider_meta = providers.fetch_previous_runs(
                client, cells, chunk_start, chunk_end, LEADS, date_chunk_days=None)
            frame, excluded_dates = _exclude_provider_wide_forecast_outages(
                frame, cells, chunk_start, chunk_end
            )
            part_meta = _write_part(frame, data_path, meta_path, {
                **expected,
                "provider": provider_meta,
                FORECAST_EXCLUDED_DATES_FIELD: excluded_dates,
                "forecast_outage_policy": FORECAST_OUTAGE_POLICY,
            })
            fetched += 1
        else:
            frame, part_meta = loaded
            excluded_dates = part_meta.get(FORECAST_EXCLUDED_DATES_FIELD, [])
            frame = _validate_forecasts(
                frame, cells, chunk_start, chunk_end, excluded_dates=excluded_dates
            )
            reused += 1
        frames.append(frame)
        metadata.append(part_meta)
    all_excluded_dates = sorted({
        value
        for part in metadata
        for value in part.get(FORECAST_EXCLUDED_DATES_FIELD, [])
    })
    forecasts = pd.concat(frames, ignore_index=True)
    forecasts = _validate_forecasts(
        forecasts, cells, start, end, excluded_dates=all_excluded_dates
    )
    provider_meta = providers.merge_metadata(part.get("provider", {}) for part in metadata)
    provider_meta.update({"parts": len(metadata), "parts_reused": reused, "parts_fetched": fetched,
                          "cell_signature": signature, "issue_time_contract": ISSUE_TIME_CONTRACT,
                          FORECAST_EXCLUDED_DATES_FIELD: all_excluded_dates,
                          "excluded_forecast_valid_date_count": len(all_excluded_dates),
                          "forecast_outage_policy": FORECAST_OUTAGE_POLICY})
    return forecasts, provider_meta


def build_climatology(client: Client, cells: pd.DataFrame, out: Path, chunk: int = 40, *,
                      all_cells: pd.DataFrame | None = None, parts_dir: Path | None = None,
                      date_chunk_days: int = DEFAULT_OBSERVATION_CHUNK_DAYS) -> Climatology:
    """Fit only anchor cells, then map all target cells to their nearest fitted anchor."""
    del chunk  # retained for API compatibility; provider adapters own spatial chunking.
    anchors = _normalise_cells(cells)
    targets = _normalise_cells(all_cells if all_cells is not None else anchors)
    lo, hi = CLIM_YEARS
    out = Path(out)
    part_root = Path(parts_dir) if parts_dir is not None else out.parent / "climatology_parts"
    observations, _, acquisition = _acquire_archive_parts(
        client, anchors, date(lo, 1, 1), date(hi, 12, 31), part_root,
        kind="climatology", chunk_days=date_chunk_days,
    )
    fitted = Climatology.fit(observations)
    expanded, mapping = fitted.expand_nearest(anchors, targets)
    expanded.save(out)
    mapping_path = out.with_name("climatology_mapping.csv")
    metadata_path = out.with_name("climatology_metadata.json")
    write_csv_atomic(mapping, mapping_path, index=False)
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "reference_period": {"start": f"{lo}-01-01", "end": f"{hi}-12-31"},
        "method": "fit_on_reference_cells_then_copy_nearest_spatial_anchor",
        "n_anchor_cells": int(len(anchors)),
        "n_target_cells": int(len(targets)),
        "anchor_cell_signature": _cell_signature(anchors),
        "target_cell_signature": _cell_signature(targets),
        "mapping_sha256": sha256_file(mapping_path),
        "acquisition": acquisition,
        "limitation": "Non-anchor cells reuse the nearest training anchor's climatology; this is a documented "
                      "spatial approximation and not a cell-specific 2015-2023 climatology.",
    }
    write_json_atomic(metadata_path, metadata)
    return expanded


def refresh_training_data(client: Client, train_cells: pd.DataFrame, paths: Paths, end: date | None = None, *,
                          start: date = FC_ARCHIVE_START,
                          observation_chunk_days: int = DEFAULT_OBSERVATION_CHUNK_DAYS,
                          forecast_chunk_days: int = DEFAULT_FORECAST_CHUNK_DAYS) -> dict:
    """Acquire/reuse verified parts, then atomically publish one local training dataset."""
    paths.ensure()
    cells = _normalise_cells(train_cells)
    end = end or (date.today() - timedelta(days=OBS_LAG_DAYS + 2))
    if start < FC_ARCHIVE_START:
        raise ValueError(
            f"training start {start} precedes the first verified complete Previous Runs valid date "
            f"{FC_ARCHIVE_START}"
        )
    if end < start:
        raise ValueError(f"training end {end} precedes Previous Runs start {start}")
    observations, static, archive_meta = _acquire_archive_parts(
        client, cells, start - timedelta(days=OBS_PRELOAD_DAYS), end, paths.observation_parts,
        kind="observations", chunk_days=observation_chunk_days,
    )
    forecasts, forecast_meta = _acquire_forecast_parts(
        client, cells, start, end, paths.forecast_parts, chunk_days=forecast_chunk_days,
    )
    excluded_forecast_dates = forecast_meta.get(FORECAST_EXCLUDED_DATES_FIELD, [])
    if observations.empty or forecasts.empty:
        raise ValueError("verified acquisition produced an empty training dataset")
    if set(forecasts["lead_days"].unique()) != set(LEADS):
        raise ValueError(f"training forecasts do not contain exactly the required leads {LEADS}")
    complete = forecasts.groupby(["cell_id", "valid_date"])["lead_days"].nunique()
    incomplete = complete[complete != len(LEADS)]
    if len(incomplete):
        raise ValueError(f"{len(incomplete)} forecast cell/date groups do not contain all required leads")
    if set(cells["cell_id"]) - set(observations["cell_id"]):
        raise ValueError("one or more training cells have no observations")
    if set(cells["cell_id"]) - set(forecasts["cell_id"]):
        raise ValueError("one or more training cells have no archived forecasts")

    write_csv_atomic(observations, paths.dataset / OBS_FILE, index=False)
    write_csv_atomic(forecasts, paths.dataset / FORECAST_FILE, index=False)
    write_csv_atomic(static, paths.dataset / STATIC_FILE, index=False)
    write_csv_atomic(cells, paths.dataset / CELLS_FILE, index=False)
    checksums = {filename: sha256_file(paths.dataset / filename) for filename in DATA_FILES}
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "data_start": str(start),
        "data_end": str(end),
        "first_verified_complete_valid_date": str(FC_ARCHIVE_START),
        "observation_preload_start": str(start - timedelta(days=OBS_PRELOAD_DAYS)),
        "n_cells": int(len(cells)),
        "obs_rows": int(len(observations)),
        "forecast_rows": int(len(forecasts)),
        "forecast_model": FORECAST_MODEL,
        "leads": list(LEADS),
        "issue_time_contract": ISSUE_TIME_CONTRACT,
        FORECAST_EXCLUDED_DATES_FIELD: excluded_forecast_dates,
        "forecast_outage_policy": FORECAST_OUTAGE_POLICY,
        "sources": {key: {"host": provider.host, "license": provider.license, "role": provider.role,
                          "notes": provider.notes} for key, provider in PROVIDERS.items()},
        "provider_fetch_metadata": {"archive": archive_meta, "previous_runs": forecast_meta},
        "sha256": checksums,
        "leakage_policy": "Observed antecedent inputs are restricted by the feature builder to data genuinely "
                          "available at the reference day. Forecast inputs use the Open-Meteo reference run "
                          "plus previous_day1..7 fixed 24-hour offsets; these are explicitly an approximation, "
                          "not exact issue runs. "
                          "Climatology is fixed to 2015-2023 and target-day observations are labels only.",
    }
    write_json_atomic(paths.dataset / "manifest.json", manifest)
    return manifest


def verify_dataset_manifest(paths: Paths) -> dict:
    manifest_path = paths.dataset / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"training manifest not found: {manifest_path}")
    manifest = read_json(manifest_path)
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"dataset schema {manifest.get('schema_version')!r} is incompatible with {SCHEMA_VERSION!r}")
    if manifest.get("forecast_model") != FORECAST_MODEL:
        raise ValueError("dataset forecast model does not match the configured serving model")
    if manifest.get("leads") != list(LEADS):
        raise ValueError(f"dataset leads must be exactly {list(LEADS)}")
    try:
        start, end = date.fromisoformat(manifest["data_start"]), date.fromisoformat(manifest["data_end"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("dataset manifest contains invalid data_start/data_end dates") from exc
    excluded = _normalise_excluded_dates(
        manifest.get(FORECAST_EXCLUDED_DATES_FIELD, []), start, end,
        field=FORECAST_EXCLUDED_DATES_FIELD,
    )
    canonical_excluded = [value.isoformat() for value in excluded]
    if manifest.get(FORECAST_EXCLUDED_DATES_FIELD, []) != canonical_excluded:
        raise ValueError(f"dataset manifest {FORECAST_EXCLUDED_DATES_FIELD} must be sorted canonical ISO dates")
    previous_runs_meta = manifest.get("provider_fetch_metadata", {}).get("previous_runs", {})
    if previous_runs_meta.get(FORECAST_EXCLUDED_DATES_FIELD, []) != canonical_excluded:
        raise ValueError("dataset manifest and Previous Runs metadata disagree on excluded dates")
    checksums = manifest.get("sha256")
    if not isinstance(checksums, dict):
        raise ValueError("dataset manifest does not contain checksums")
    for filename in DATA_FILES:
        path = paths.dataset / filename
        if not path.exists():
            raise FileNotFoundError(f"dataset artifact missing: {path}")
        expected = checksums.get(filename)
        actual = sha256_file(path)
        if not expected or actual != expected:
            raise ValueError(f"dataset artifact checksum mismatch: {filename}")
    return manifest


def load_training_data(paths: Paths):
    manifest = verify_dataset_manifest(paths)
    directory = paths.dataset
    observations = pd.read_csv(directory / OBS_FILE, dtype={"cell_id": str}, parse_dates=["date"])
    forecasts = pd.read_csv(directory / FORECAST_FILE, dtype={"cell_id": str}, parse_dates=["valid_date"])
    if observations.empty or forecasts.empty:
        raise ValueError("dataset artifacts must not be empty")
    cells = _normalise_cells(pd.read_csv(directory / CELLS_FILE, dtype={"cell_id": str}))
    static = pd.read_csv(directory / STATIC_FILE, dtype={"cell_id": str})
    data_start = date.fromisoformat(manifest["data_start"])
    data_end = date.fromisoformat(manifest["data_end"])
    observation_start = date.fromisoformat(manifest["observation_preload_start"])
    excluded_forecast_dates = manifest.get(FORECAST_EXCLUDED_DATES_FIELD, [])
    observations = _validate_observations(
        observations, cells, observation_start, data_end)
    forecasts = _validate_forecasts(
        forecasts, cells, data_start, data_end, excluded_dates=excluded_forecast_dates)
    if set(forecasts["lead_days"].unique()) != set(LEADS):
        raise ValueError("dataset content is missing one or more required lead offsets")
    if static["cell_id"].astype(str).duplicated().any():
        raise ValueError("dataset static artifact contains duplicate cells")
    return cells, observations, forecasts, static, manifest
