"""Read and normalize BADIA AI's saved demo datasets.

The MVP deliberately serves immutable local snapshots.  Nothing in this module
connects to Earth Engine or labels a saved result as a live forecast.
"""

from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .priority import add_national_priority


DEFAULT_SNAPSHOT_LABEL = "Historical / latest available demo (saved local snapshot)"
DISCLAIMER = (
    "Satellite-derived vegetation anomaly risk indicator; not a field-verified "
    "desertification diagnosis and not a live forecast."
)


class DataStoreError(RuntimeError):
    """Base exception for unavailable or invalid local demo data."""


class DataFileMissingError(DataStoreError):
    """Raised when a required local data file is absent."""


class DataFileInvalidError(DataStoreError):
    """Raised when a local data file cannot be interpreted."""


def _read_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise DataFileMissingError(f"Data file is not available: {path.name}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise DataFileInvalidError(f"Could not read valid JSON from {path.name}") from exc


def _first(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return None


def _as_float(value: Any) -> float | None:
    if value in (None, "", "null", "None", "nan", "NaN"):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _as_int(value: Any) -> int | None:
    number = _as_float(value)
    return int(number) if number is not None else None


def _parse_jsonish(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped or stripped[0:1] not in ("[", "{"):
        return value
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return value


def _normalize_level(value: Any, score: float | None) -> str:
    if score is None:
        return "N/A"
    if value is not None:
        label = str(value).strip().lower()
        aliases = {
            "low": "Low",
            "moderate": "Moderate",
            "medium": "Moderate",
            "high": "High",
            "n/a": "N/A",
            "na": "N/A",
            "unknown": "N/A",
        }
        if label in aliases:
            return aliases[label]
    # This fallback is only for display compatibility when a source omitted the
    # label. The authoritative score remains the value stored in the data file.
    # Canonical presentation thresholds from data/metadata.json.
    if score < 40.0:
        return "Low"
    if score < 70.0:
        return "Moderate"
    return "High"


def _extract_horizon(value: Any) -> int | None:
    if isinstance(value, (int, float)):
        return int(value)
    match = re.search(r"\d+", str(value or ""))
    return int(match.group()) if match else None


def _sanitize(value: Any) -> Any:
    """Replace non-standard JSON numbers and normalize nested values."""

    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    return value


class DataStore:
    """Filesystem-backed store for the frontend-facing API contract."""

    def __init__(self, data_dir: Path | str) -> None:
        self.data_dir = Path(data_dir).resolve()

    def _path(self, filename: str) -> Path:
        return self.data_dir / filename

    def _json_if_present(self, filename: str) -> Any | None:
        path = self._path(filename)
        return _read_json(path) if path.is_file() else None

    def availability(self) -> dict[str, Any]:
        names = (
            "cells_16.json",
            "cells_32.json",
            "cells_16.geojson",
            "cells_32.geojson",
            "cells_latest.csv",
            "metadata.json",
            "metrics.json",
            "national_summary.json",
        )
        files = {name: self._path(name).is_file() for name in names}
        csv_available = files["cells_latest.csv"]
        horizons = {
            "16": files["cells_16.json"] or files["cells_16.geojson"] or csv_available,
            "32": files["cells_32.json"] or files["cells_32.geojson"] or csv_available,
        }
        return {"files": files, "horizons": horizons}

    def _read_csv_cells(self, horizon: int) -> list[dict[str, Any]]:
        path = self._path("cells_latest.csv")
        if not path.is_file():
            raise DataFileMissingError(
                f"No saved cell dataset is available for the +{horizon}-day horizon"
            )
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                records = list(csv.DictReader(handle))
        except (OSError, csv.Error) as exc:
            raise DataFileInvalidError("Could not read cells_latest.csv") from exc

        filtered = []
        for record in records:
            record_horizon = _extract_horizon(
                _first(record, "horizon_days", "horizon", "forecast_horizon")
            )
            if record_horizon == horizon:
                filtered.append(record)
        return filtered

    @staticmethod
    def _records_from_payload(payload: Any, filename: str) -> tuple[list[Any], dict[str, Any]]:
        defaults: dict[str, Any] = {}
        if isinstance(payload, list):
            return payload, defaults
        if not isinstance(payload, dict):
            raise DataFileInvalidError(f"{filename} must contain a list or object")

        for key in ("snapshot_date", "snapshot_label", "as_of_date", "date"):
            if payload.get(key) not in (None, ""):
                defaults[key] = payload[key]

        if payload.get("type") == "FeatureCollection":
            records = payload.get("features")
        else:
            records = next(
                (
                    payload[key]
                    for key in ("cells", "records", "data", "features")
                    if isinstance(payload.get(key), list)
                ),
                None,
            )
        if not isinstance(records, list):
            raise DataFileInvalidError(
                f"{filename} does not contain a cells, records, data, or features list"
            )
        return records, defaults

    @staticmethod
    def _normalize_cell(record: Any, horizon: int, defaults: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(record, dict):
            raise DataFileInvalidError("Each cell record must be a JSON object")

        if record.get("type") == "Feature" and isinstance(record.get("properties"), dict):
            raw = dict(record["properties"])
            geometry = record.get("geometry") or {}
            coordinates = geometry.get("coordinates") if isinstance(geometry, dict) else None
            if isinstance(coordinates, list) and len(coordinates) >= 2:
                raw.setdefault("lon", coordinates[0])
                raw.setdefault("lat", coordinates[1])
            if record.get("id") not in (None, ""):
                raw.setdefault("cell_id", record["id"])
        else:
            raw = dict(record)

        cell_id = _first(raw, "cell_id", "grid_id", "id")
        if cell_id is None:
            raise DataFileInvalidError("A cell record is missing cell_id")

        lat = _as_float(_first(raw, "lat", "latitude", "center_lat", "centroid_lat"))
        lon = _as_float(_first(raw, "lon", "lng", "longitude", "center_lon", "centroid_lon"))
        predicted_anomaly = _as_float(
            _first(
                raw,
                "predicted_anomaly",
                "prediction",
                "predicted_ndvi_anomaly",
                "y_pred",
            )
        )
        risk_score = _as_float(_first(raw, "risk_score", "score"))
        raw_level = _first(raw, "risk_level", "level", "risk_category")
        source_horizon = _extract_horizon(
            _first(raw, "horizon_days", "horizon", "forecast_horizon")
        )
        snapshot_date = _first(raw, "snapshot_date", "as_of_date", "date")
        if snapshot_date is None:
            snapshot_date = _first(defaults, "snapshot_date", "as_of_date", "date")
        snapshot_label = _first(raw, "snapshot_label") or defaults.get("snapshot_label")

        normalized = {
            "cell_id": str(cell_id),
            "lat": lat,
            "lon": lon,
            "predicted_anomaly": predicted_anomaly,
            "risk_score": risk_score,
            "risk_level": _normalize_level(raw_level, risk_score),
            "top_factors": _parse_jsonish(raw.get("top_factors", [])) or [],
            "data_quality": _parse_jsonish(raw.get("data_quality", "Unknown")),
            "horizon_days": source_horizon or horizon,
            "snapshot_date": str(snapshot_date) if snapshot_date is not None else None,
            "snapshot_label": str(snapshot_label or DEFAULT_SNAPSHOT_LABEL),
        }

        # Keep useful explanatory fields without allowing them to overwrite the
        # stable contract above.
        optional_keys = (
            "area_km2",
            "year",
            "period_index",
            "percentile",
            "risk_percentile",
            "risk_reference_n",
            "ndvi",
            "current_anomaly",
            "ndvi_anomaly_current",
            "rainfall_16d",
            "rainfall_30d",
            "rainfall_90d",
            "rain_16d_mm",
            "rain_30d_mm",
            "rain_90d_mm",
            "temperature",
            "temperature_30d_c",
            "soil_moisture",
            "soil_moisture_30d",
            "period",
            "top_factors_method",
            "geometry_quality",
            "temporal_status",
            # Offline, centroid-derived bilingual location lookup.  These fields
            # are display metadata only and never affect risk predictions.
            "location_label_ar",
            "location_label_en",
            "governorate_ar",
            "governorate_en",
            "governorate_code",
            "locality_ar",
            "locality_en",
            "region_ar",
            "region_en",
            "location_kind",
            "locality_distance_km",
            "locality_geoname_id",
            "governorate_assignment_method",
            "governorate_boundary_distance_km",
        )
        for key in optional_keys:
            if key in raw:
                normalized[key] = _sanitize(raw[key])

        return _sanitize(normalized)

    def get_cells(self, horizon: int) -> list[dict[str, Any]]:
        if horizon not in (16, 32):
            raise ValueError("horizon must be 16 or 32")

        json_path = self._path(f"cells_{horizon}.json")
        geojson_path = self._path(f"cells_{horizon}.geojson")
        if json_path.is_file():
            payload = _read_json(json_path)
            filename = json_path.name
        elif geojson_path.is_file():
            payload = _read_json(geojson_path)
            filename = geojson_path.name
        else:
            records = self._read_csv_cells(horizon)
            payload = records
            filename = "cells_latest.csv"

        records, defaults = self._records_from_payload(payload, filename)
        cells = [self._normalize_cell(record, horizon, defaults) for record in records]
        return add_national_priority(cells)

    @staticmethod
    def snapshot_fields(cells: Iterable[dict[str, Any]]) -> tuple[str | None, str]:
        cells_list = list(cells)
        snapshot_date = next(
            (cell.get("snapshot_date") for cell in cells_list if cell.get("snapshot_date")),
            None,
        )
        snapshot_label = next(
            (cell.get("snapshot_label") for cell in cells_list if cell.get("snapshot_label")),
            DEFAULT_SNAPSHOT_LABEL,
        )
        return snapshot_date, snapshot_label

    def cells_payload(self, horizon: int) -> dict[str, Any]:
        cells = self.get_cells(horizon)
        snapshot_date, snapshot_label = self.snapshot_fields(cells)
        return {
            "type": "CellCollection",
            "scope": "Jordan",
            "horizon_days": horizon,
            "count": len(cells),
            "snapshot_date": snapshot_date,
            "snapshot_label": snapshot_label,
            "is_live": False,
            "disclaimer": DISCLAIMER,
            "cells": cells,
        }

    def geojson_payload(self, horizon: int) -> dict[str, Any]:
        # Keep properties and rankings identical to the canonical /api/cells
        # payload.  A packaged project can contain both JSON and GeoJSON; the
        # GeoJSON is authoritative only for geometry, while get_cells() applies
        # the documented source preference (JSON, then GeoJSON, then CSV) for
        # cell values.  Matching geometry by cell_id also avoids silently
        # assigning the wrong polygon if the two files use different ordering.
        cells = self.get_cells(horizon)
        geojson_path = self._path(f"cells_{horizon}.geojson")
        geometry_by_cell_id: dict[str, Any] = {}
        if geojson_path.is_file():
            payload = _read_json(geojson_path)
            records, defaults = self._records_from_payload(payload, geojson_path.name)
            for record in records:
                normalized = self._normalize_cell(record, horizon, defaults)
                geometry = (
                    _sanitize(record.get("geometry"))
                    if isinstance(record, dict) and record.get("type") == "Feature"
                    else None
                )
                geometry_by_cell_id.setdefault(
                    normalized["cell_id"].casefold(), geometry
                )
        snapshot_date, snapshot_label = self.snapshot_fields(cells)
        features = []
        for cell in cells:
            lon, lat = cell.get("lon"), cell.get("lat")
            geometry = geometry_by_cell_id.get(cell["cell_id"].casefold())
            if geometry is None and lon is not None and lat is not None:
                geometry = {"type": "Point", "coordinates": [lon, lat]}
            features.append(
                {
                    "type": "Feature",
                    "id": cell["cell_id"],
                    "geometry": geometry,
                    "properties": cell,
                }
            )
        return {
            "type": "FeatureCollection",
            "name": f"BADIA AI +{horizon}-day historical demo snapshot",
            "scope": "Jordan",
            "horizon_days": horizon,
            "snapshot_date": snapshot_date,
            "snapshot_label": snapshot_label,
            "is_live": False,
            "disclaimer": DISCLAIMER,
            "features": features,
        }

    def find_cell(self, cell_id: str, horizon: int) -> dict[str, Any] | None:
        wanted = str(cell_id).casefold()
        return next(
            (cell for cell in self.get_cells(horizon) if cell["cell_id"].casefold() == wanted),
            None,
        )

    @staticmethod
    def _default_metrics() -> dict[str, Any]:
        raw = {
            "16": {
                "validation": {"xgboost_mae": 0.005072, "persistence_mae": 0.005446},
                "test": {"xgboost_mae": 0.004711, "persistence_mae": 0.004840},
            },
            "32": {
                "validation": {"xgboost_mae": 0.006047, "persistence_mae": 0.006907},
                "test": {"xgboost_mae": 0.005536, "persistence_mae": 0.006193},
            },
        }
        for splits in raw.values():
            for values in splits.values():
                baseline = values["persistence_mae"]
                model = values["xgboost_mae"]
                values["improvement_percent"] = round((baseline - model) / baseline * 100, 2)
        return {
            "metric": "MAE",
            "lower_is_better": True,
            "horizons": raw,
            "note": "Evaluation metrics are for held-out historical validation/test periods.",
        }

    def metrics(self) -> dict[str, Any]:
        payload = self._json_if_present("metrics.json")
        if payload is None:
            payload = self._default_metrics()
        if not isinstance(payload, dict):
            raise DataFileInvalidError("metrics.json must contain a JSON object")
        result = dict(payload)
        result["is_live"] = False
        result.setdefault("evaluation_context", "Held-out historical evaluation")
        return _sanitize(result)

    def metadata(self) -> dict[str, Any]:
        payload = self._json_if_present("metadata.json")
        if payload is None:
            payload = {
                "project": "BADIA AI",
                "scope": "Jordan",
                "snapshot_label": DEFAULT_SNAPSHOT_LABEL,
            }
        if not isinstance(payload, dict):
            raise DataFileInvalidError("metadata.json must contain a JSON object")
        result = dict(payload)
        result["is_live"] = False
        result["serving_mode"] = "saved_local_snapshot"
        result.setdefault("snapshot_label", DEFAULT_SNAPSHOT_LABEL)
        result.setdefault("disclaimer", DISCLAIMER)
        return _sanitize(result)

    @staticmethod
    def _summary_for_cells(cells: list[dict[str, Any]], horizon: int) -> dict[str, Any]:
        scores = [cell["risk_score"] for cell in cells if cell.get("risk_score") is not None]
        anomalies = [
            cell["predicted_anomaly"]
            for cell in cells
            if cell.get("predicted_anomaly") is not None
        ]
        counts = Counter(cell.get("risk_level", "N/A") for cell in cells)
        snapshot_date, snapshot_label = DataStore.snapshot_fields(cells)
        return {
            "horizon_days": horizon,
            "cell_count": len(cells),
            "risk_level_counts": {
                "Low": counts.get("Low", 0),
                "Moderate": counts.get("Moderate", 0),
                "High": counts.get("High", 0),
                "N/A": counts.get("N/A", 0),
            },
            "mean_risk_score": round(sum(scores) / len(scores), 3) if scores else None,
            "min_risk_score": min(scores) if scores else None,
            "max_risk_score": max(scores) if scores else None,
            "mean_predicted_anomaly": (
                round(sum(anomalies) / len(anomalies), 6) if anomalies else None
            ),
            "snapshot_date": snapshot_date,
            "snapshot_label": snapshot_label,
        }

    def national_summary(self) -> dict[str, Any]:
        payload = self._json_if_present("national_summary.json")
        if payload is not None:
            if isinstance(payload, list):
                result: dict[str, Any] = {"areas": payload}
            elif isinstance(payload, dict):
                result = dict(payload)
            else:
                raise DataFileInvalidError(
                    "national_summary.json must contain a JSON object or list"
                )
        else:
            horizons: dict[str, Any] = {}
            errors: dict[str, str] = {}
            for horizon in (16, 32):
                try:
                    cells = self.get_cells(horizon)
                    horizons[str(horizon)] = self._summary_for_cells(cells, horizon)
                except DataStoreError as exc:
                    errors[str(horizon)] = str(exc)
            if not horizons:
                raise DataFileMissingError("No national summary or cell datasets are available")
            result = {"scope": "Jordan", "horizons": horizons}
            if errors:
                result["unavailable_horizons"] = errors

        result["is_live"] = False
        result.setdefault("scope", "Jordan")
        result.setdefault("snapshot_label", DEFAULT_SNAPSHOT_LABEL)
        result.setdefault("disclaimer", DISCLAIMER)
        return _sanitize(result)
