"""Build BADIA AI near-real-time output files from validated environmental inputs."""

from __future__ import annotations

import json
import math
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import xgboost as xgb

from .earth_engine_source import AnchorPeriod, EarthEngineSource
from .live_features import (
    CORE_FEATURES,
    MODEL_FEATURES,
    finite_or_none,
    percentile_scores,
    risk_level,
    seasonal_encoding,
)


DISPLAY_NAMES = {
    "ndvi": "Current NDVI",
    "ndvi_anomaly_current": "Current seasonal NDVI anomaly",
    "rain_16d_mm": "Rainfall · 16 days",
    "rain_30d_mm": "Rainfall · 30 days",
    "rain_90d_mm": "Rainfall · 90 days",
    "temperature_30d_c": "Temperature · 30 days",
    "soil_moisture_30d": "Soil moisture · 30 days",
    "period_sin": "Seasonal timing (sine)",
    "period_cos": "Seasonal timing (cosine)",
    "latitude": "Latitude",
    "longitude": "Longitude",
    "area_km2": "Cell area",
}


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def _base_cells(data_dir: Path) -> list[dict[str, Any]]:
    payload = _json(data_dir / "cells_16.json")
    return payload["cells"]


def _quality(row: pd.Series) -> dict[str, Any]:
    raw = [
        "ndvi", "ndvi_anomaly_current", "rain_16d_mm", "rain_30d_mm", "rain_90d_mm",
        "temperature_30d_c", "soil_moisture_30d", "latitude", "longitude", "area_km2",
    ]
    missing = [name for name in raw if pd.isna(row[name])]
    completeness = 100.0 * (len(raw) - len(missing)) / len(raw)
    core_missing = [name for name in CORE_FEATURES if name in missing]
    status = "Limited" if core_missing else ("Good" if completeness >= 90 else "Partial")
    return {
        "status": status,
        "completeness_pct": round(completeness, 1),
        "missing_fields": missing,
        "core_signal_available": not core_missing,
        "note": "Missing values are retained; risk is withheld if the current vegetation signal is unavailable.",
    }


def _top_factors(row: pd.Series, contrib: np.ndarray) -> list[dict[str, Any]]:
    ranked = np.argsort(np.abs(contrib))[::-1]
    output = []
    for idx in ranked:
        feature = MODEL_FEATURES[int(idx)]
        value = row[feature]
        if pd.isna(value):
            continue
        c = float(contrib[idx])
        output.append({
            "feature": feature,
            "display_name": DISPLAY_NAMES[feature],
            "value": round(float(value), 5),
            "contribution": round(c, 7),
            "direction": (
                "Lowers predicted anomaly / raises relative risk signal"
                if c < 0 else "Raises predicted anomaly / lowers relative risk signal"
            ),
        })
        if len(output) == 3:
            break
    return output


def _prepare_frame(data_dir: Path, source_rows: dict[str, dict[str, Any]], anchor: AnchorPeriod) -> pd.DataFrame:
    base = _base_cells(data_dir)
    sin_value, cos_value = seasonal_encoding(anchor.period_index)
    records = []
    for cell in base:
        cell_id = str(cell["cell_id"])
        source = source_rows.get(cell_id, {})
        records.append({
            "cell_id": cell_id,
            "ndvi": source.get("ndvi"),
            "ndvi_anomaly_current": source.get("ndvi_anomaly_current"),
            "rain_16d_mm": source.get("rain_16d_mm"),
            "rain_30d_mm": source.get("rain_30d_mm"),
            "rain_90d_mm": source.get("rain_90d_mm"),
            "temperature_30d_c": source.get("temperature_30d_c"),
            "soil_moisture_30d": source.get("soil_moisture_30d"),
            "period_sin": sin_value,
            "period_cos": cos_value,
            "latitude": cell["lat"],
            "longitude": cell["lon"],
            "area_km2": cell["area_km2"],
        })
    return pd.DataFrame.from_records(records)


def _model_cells(
    frame: pd.DataFrame,
    model_path: Path,
    reference: list[float],
    horizon: int,
    anchor: AnchorPeriod,
) -> list[dict[str, Any]]:
    model = xgb.Booster()
    model.load_model(model_path)
    matrix = xgb.DMatrix(frame[MODEL_FEATURES], feature_names=MODEL_FEATURES)
    predictions = model.predict(matrix)
    contributions = model.predict(matrix, pred_contribs=True)[:, :-1]
    scores = percentile_scores(predictions, reference)

    cells = []
    for pos, (_, row) in enumerate(frame.iterrows()):
        quality = _quality(row)
        publish = bool(quality["core_signal_available"])
        prediction = round(float(predictions[pos]), 8) if publish else None
        score = round(float(scores[pos]), 1) if publish else None
        cells.append({
            "cell_id": row["cell_id"],
            "lat": round(float(row["latitude"]), 7),
            "lon": round(float(row["longitude"]), 7),
            "area_km2": round(float(row["area_km2"]), 4),
            "year": anchor.year,
            "period_index": anchor.period_index,
            "horizon_days": horizon,
            "predicted_anomaly": prediction,
            "risk_score": score,
            "risk_level": risk_level(score),
            "risk_percentile": score,
            "risk_reference_n": len(reference),
            "ndvi": finite_or_none(row["ndvi"], 6),
            "ndvi_anomaly_current": finite_or_none(row["ndvi_anomaly_current"], 6),
            "rain_16d_mm": finite_or_none(row["rain_16d_mm"], 3),
            "rain_30d_mm": finite_or_none(row["rain_30d_mm"], 3),
            "rain_90d_mm": finite_or_none(row["rain_90d_mm"], 3),
            "temperature_30d_c": finite_or_none(row["temperature_30d_c"], 3),
            "soil_moisture_30d": finite_or_none(row["soil_moisture_30d"], 5),
            "top_factors": _top_factors(row, contributions[pos]) if publish else [],
            "top_factors_method": "Largest absolute TreeSHAP model contributions; associations, not causal effects.",
            "data_quality": quality,
            "snapshot_date": anchor.snapshot_date.isoformat(),
            "snapshot_label": f"Latest common-source environmental snapshot ending {anchor.snapshot_date.isoformat()}",
            "temporal_status": "Near-real-time, latest common available source period; source latency applies.",
            "geometry_quality": "Approximate square derived from centroid and reported area; not an official boundary.",
        })
    return cells


def _summary(cells: list[dict[str, Any]], horizon: int, anchor: AnchorPeriod) -> dict[str, Any]:
    counts = Counter(c["risk_level"] for c in cells)
    scores = [c["risk_score"] for c in cells if c["risk_score"] is not None]
    return {
        "scope": "Jordan",
        "horizon_days": horizon,
        "snapshot_date": anchor.snapshot_date.isoformat(),
        "snapshot_label": f"Latest common-source environmental snapshot ending {anchor.snapshot_date.isoformat()}",
        "summary": {
            "total_cells": len(cells),
            "available_cells": len(scores),
            "mean_risk_score": round(float(np.mean(scores)), 1) if scores else None,
            "high_count": counts["High"], "moderate_count": counts["Moderate"],
            "low_count": counts["Low"], "na_count": counts["N/A"],
        },
        "levels": {"low": counts["Low"], "moderate": counts["Moderate"], "high": counts["High"], "na": counts["N/A"]},
        "is_live": True,
        "live_mode": "near_real_time",
    }


def _geojson(template: dict[str, Any], cells: list[dict[str, Any]], horizon: int, anchor: AnchorPeriod) -> dict[str, Any]:
    values = {str(c["cell_id"]): c for c in cells}
    features = []
    for feature in template.get("features", []):
        cell_id = str(feature.get("id") or (feature.get("properties") or {}).get("cell_id"))
        cell = values.get(cell_id)
        if not cell:
            continue
        features.append({"type": "Feature", "id": cell_id, "geometry": feature.get("geometry"), "properties": cell})
    return {
        "type": "FeatureCollection", "name": f"BADIA AI +{horizon}-day near-real-time snapshot",
        "scope": "Jordan", "horizon_days": horizon,
        "snapshot_date": anchor.snapshot_date.isoformat(), "is_live": True,
        "features": features,
    }


def build_live_snapshot(repo_root: Path, ee_project: str, output_dir: Path) -> dict[str, Any]:
    data_dir = repo_root / "data"
    models_dir = repo_root / "models"
    geojson_path = data_dir / "cells_16.geojson"
    source = EarthEngineSource(ee_project)
    anchor = source.latest_common_anchor()
    source_rows = source.current_features(geojson_path, anchor)
    frame = _prepare_frame(data_dir, source_rows, anchor)

    output_dir.mkdir(parents=True, exist_ok=True)
    summaries: dict[str, Any] = {}
    template = _json(geojson_path)
    all_csv = []
    for horizon in (16, 32):
        reference = source.target_reference(geojson_path, anchor.period_index, horizon)
        cells = _model_cells(frame, models_dir / f"xgboost_{horizon}d.json", reference, horizon, anchor)
        payload = {
            "type": "CellCollection", "scope": "Jordan", "horizon_days": horizon,
            "count": len(cells), "snapshot_date": anchor.snapshot_date.isoformat(),
            "snapshot_label": f"Latest common-source environmental snapshot ending {anchor.snapshot_date.isoformat()}",
            "is_live": True, "live_mode": "near_real_time", "cells": cells,
        }
        _write(output_dir / f"cells_{horizon}.json", payload)
        _write(output_dir / f"cells_{horizon}.geojson", _geojson(template, cells, horizon, anchor))
        summaries[str(horizon)] = _summary(cells, horizon, anchor)
        all_csv.extend(cells)

    pd.DataFrame(all_csv).to_csv(output_dir / "cells_latest.csv", index=False)
    _write(output_dir / "national_summary.json", {
        "scope": "Jordan", "snapshot_date": anchor.snapshot_date.isoformat(),
        "is_live": True, "live_mode": "near_real_time", "horizons": summaries,
        "disclaimer": "Near-real-time satellite-derived vegetation anomaly risk indicator; not a field-verified desertification diagnosis.",
    })
    _write(output_dir / "metadata.json", {
        "project_name": "BADIA AI", "scope": "Jordan", "serving_mode": "near_real_time_generated",
        "is_live": True, "live_mode": "near_real_time",
        "snapshot_date": anchor.snapshot_date.isoformat(), "snapshot_year": anchor.year,
        "snapshot_period": anchor.period_index,
        "source": {
            "ndvi": "MODIS/061/MOD13Q1",
            "rainfall": "UCSB-CHG/CHIRPS/DAILY",
            "temperature_soil_moisture": "ECMWF/ERA5_LAND/DAILY_AGGR",
        },
        "source_freshness": {
            "modis_composite_start": anchor.composite_start.isoformat(),
            "common_snapshot_end": anchor.snapshot_date.isoformat(),
            "latest_chirps": anchor.latest_chirps_date.isoformat(),
            "latest_era5": anchor.latest_era5_date.isoformat(),
        },
        "model_features": MODEL_FEATURES,
        "risk_definition": "Empirical percentile (0–100) of predicted vegetation-stress severity (-predicted anomaly) against reconstructed 2015–2022 target anomalies for the same source period and horizon; not a probability.",
        "disclaimer": "Near-real-time/latest-available environmental monitoring; source latency applies and field verification is required.",
    })
    if (data_dir / "metrics.json").is_file():
        shutil.copy2(data_dir / "metrics.json", output_dir / "metrics.json")
    _write(output_dir / "provenance.json", {
        "generated_by": "BADIA AI near-real-time Earth Engine pipeline",
        "earth_engine_project": ee_project,
        "snapshot_date": anchor.snapshot_date.isoformat(),
        "datasets": ["MODIS/061/MOD13Q1", "UCSB-CHG/CHIRPS/DAILY", "ECMWF/ERA5_LAND/DAILY_AGGR"],
        "note": "Generated outputs are separate from the immutable packaged historical demo.",
    })
    return {
        "snapshot_date": anchor.snapshot_date.isoformat(),
        "period_index": anchor.period_index,
        "output_dir": str(output_dir),
        "cell_count": len(frame),
    }
