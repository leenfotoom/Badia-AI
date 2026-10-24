"""Build the immutable BADIA AI map snapshot from the saved project artifacts.

The script deliberately uses the already-trained XGBoost models.  It does not
retrain or invent labels.  The selected date is the latest common within-year
input period that supports both +16 and +32 day targets in the original design:
2025 period 21 (nominal period end 2025-12-02).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import xgboost as xgb


SNAPSHOT_YEAR = 2025
SNAPSHOT_PERIOD = 21
SNAPSHOT_DATE = "2025-12-02"
SNAPSHOT_LABEL = (
    "Latest common model-evaluable historical-input demo "
    "(2025 period 21; nominal period end 2 Dec 2025)"
)
FEATURES = [
    "ndvi",
    "ndvi_anomaly_current",
    "rain_16d_mm",
    "rain_30d_mm",
    "rain_90d_mm",
    "temperature_30d_c",
    "soil_moisture_30d",
    "period_sin",
    "period_cos",
    "latitude",
    "longitude",
    "area_km2",
]
CORE_FEATURES = ["ndvi", "ndvi_anomaly_current"]
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
RAW_QUALITY_FEATURES = [
    "ndvi",
    "ndvi_anomaly_current",
    "rain_16d_mm",
    "rain_30d_mm",
    "rain_90d_mm",
    "temperature_30d_c",
    "soil_moisture_30d",
    "latitude",
    "longitude",
    "area_km2",
]


def finite_or_none(value: Any, digits: int | None = None) -> Any:
    if value is None:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        if not math.isfinite(float(value)):
            return None
        return round(float(value), digits) if digits is not None else float(value)
    return value


def clean_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): clean_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean_json(item) for item in value]
    return finite_or_none(value)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(clean_json(payload), ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def locate(source_dir: Path, relative: str) -> Path:
    path = source_dir / relative
    if not path.is_file():
        raise FileNotFoundError(f"Required source artifact is missing: {path}")
    return path


def risk_level(score: float | None) -> str:
    if score is None:
        return "N/A"
    if score < 40:
        return "Low"
    if score < 70:
        return "Moderate"
    return "High"


def percentile_scores(predictions: np.ndarray, reference: np.ndarray) -> np.ndarray:
    """Percentile of vegetation-stress severity (-anomaly) in training history."""

    reference = np.asarray(reference, dtype=float)
    reference = np.sort(-reference[np.isfinite(reference)])
    if not len(reference):
        raise ValueError("Risk reference distribution is empty")
    severity = -np.asarray(predictions, dtype=float)
    ranks = np.searchsorted(reference, severity, side="right")
    return np.clip(100.0 * ranks / len(reference), 0.0, 100.0)


def approximate_square(lat: float, lon: float, area_km2: float) -> dict[str, Any]:
    side_km = math.sqrt(max(area_km2, 0.01))
    half_lat = (side_km / 2.0) / 111.32
    half_lon = (side_km / 2.0) / (111.32 * max(math.cos(math.radians(lat)), 0.2))
    ring = [
        [lon - half_lon, lat - half_lat],
        [lon + half_lon, lat - half_lat],
        [lon + half_lon, lat + half_lat],
        [lon - half_lon, lat + half_lat],
        [lon - half_lon, lat - half_lat],
    ]
    return {
        "type": "Polygon",
        "coordinates": [[[round(x, 7), round(y, 7)] for x, y in ring]],
    }


def quality_for(row: pd.Series) -> dict[str, Any]:
    missing = [name for name in RAW_QUALITY_FEATURES if pd.isna(row[name])]
    completeness = 100.0 * (len(RAW_QUALITY_FEATURES) - len(missing)) / len(RAW_QUALITY_FEATURES)
    core_missing = [name for name in CORE_FEATURES if name in missing]
    if core_missing:
        status = "Limited"
    elif completeness >= 90:
        status = "Good"
    elif completeness >= 70:
        status = "Partial"
    else:
        status = "Limited"
    return {
        "status": status,
        "completeness_pct": round(completeness, 1),
        "missing_fields": missing,
        "core_signal_available": not core_missing,
        "note": (
            "Missing values were retained; XGBoost supports NaN. "
            "Risk is withheld when the current vegetation signal is unavailable."
        ),
    }


def top_factors(row: pd.Series, contributions: np.ndarray) -> list[dict[str, Any]]:
    ranked = np.argsort(np.abs(contributions))[::-1]
    factors: list[dict[str, Any]] = []
    for index in ranked:
        feature = FEATURES[int(index)]
        value = row[feature]
        if pd.isna(value):
            continue
        contribution = float(contributions[index])
        factors.append(
            {
                "feature": feature,
                "display_name": DISPLAY_NAMES[feature],
                "value": round(float(value), 5),
                "contribution": round(contribution, 7),
                "direction": (
                    "Lowers predicted anomaly / raises relative risk signal"
                    if contribution < 0
                    else "Raises predicted anomaly / lowers relative risk signal"
                ),
            }
        )
        if len(factors) == 3:
            break
    return factors


def build_horizon(
    horizon: int,
    snapshot: pd.DataFrame,
    training: pd.DataFrame,
    model_path: Path,
    saved_predictions_path: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    model = xgb.Booster()
    model.load_model(model_path)
    matrix = xgb.DMatrix(snapshot[FEATURES], feature_names=FEATURES)
    predictions = model.predict(matrix)
    contributions = model.predict(matrix, pred_contribs=True)[:, :-1]

    # Verify that this inference path reproduces the saved historical output.
    saved = pd.read_csv(saved_predictions_path)
    prediction_column = f"predicted_anomaly_{horizon}d"
    saved = saved[
        (saved["year"] == SNAPSHOT_YEAR) & (saved["period_index"] == SNAPSHOT_PERIOD)
    ][["cell_id", prediction_column]]
    check = pd.DataFrame({"cell_id": snapshot["cell_id"], "recomputed": predictions}).merge(
        saved, on="cell_id", how="inner"
    )
    max_abs_difference = float(
        np.max(np.abs(check["recomputed"] - check[prediction_column]))
    )
    if max_abs_difference > 1e-6:
        raise RuntimeError(
            f"Saved +{horizon} predictions were not reproduced: max diff {max_abs_difference}"
        )

    target_column = f"target_anomaly_{horizon}d"
    reference = training.loc[
        (training["period_index"] == SNAPSHOT_PERIOD) & training[target_column].notna(),
        target_column,
    ].to_numpy()
    scores = percentile_scores(predictions, reference)

    cells: list[dict[str, Any]] = []
    for position, (_, row) in enumerate(snapshot.iterrows()):
        quality = quality_for(row)
        publish = bool(quality["core_signal_available"])
        prediction = round(float(predictions[position]), 8) if publish else None
        score = round(float(scores[position]), 1) if publish else None
        level = risk_level(score)
        factors = top_factors(row, contributions[position]) if publish else []
        cell = {
            "cell_id": str(row["cell_id"]),
            "lat": round(float(row["latitude"]), 7),
            "lon": round(float(row["longitude"]), 7),
            "area_km2": round(float(row["area_km2"]), 4),
            "year": SNAPSHOT_YEAR,
            "period_index": SNAPSHOT_PERIOD,
            "horizon_days": horizon,
            "predicted_anomaly": prediction,
            "risk_score": score,
            "risk_level": level,
            "risk_percentile": score,
            "risk_reference_n": int(len(reference)),
            "ndvi": finite_or_none(row["ndvi"], 6),
            "ndvi_anomaly_current": finite_or_none(row["ndvi_anomaly_current"], 6),
            "rain_16d_mm": finite_or_none(row["rain_16d_mm"], 3),
            "rain_30d_mm": finite_or_none(row["rain_30d_mm"], 3),
            "rain_90d_mm": finite_or_none(row["rain_90d_mm"], 3),
            "temperature_30d_c": finite_or_none(row["temperature_30d_c"], 3),
            "soil_moisture_30d": finite_or_none(row["soil_moisture_30d"], 5),
            "top_factors": factors,
            "top_factors_method": (
                "Largest absolute TreeSHAP model contributions; associations, not causal effects."
            ),
            "data_quality": quality,
            "snapshot_date": SNAPSHOT_DATE,
            "snapshot_label": SNAPSHOT_LABEL,
            "temporal_status": "Retrospective saved-model demo; not a live forecast",
            "geometry_quality": (
                "Approximate square derived from centroid and reported area; not an official boundary."
            ),
        }
        cells.append(cell)

    counts = Counter(cell["risk_level"] for cell in cells)
    available_scores = [cell["risk_score"] for cell in cells if cell["risk_score"] is not None]
    summary = {
        "scope": "Jordan",
        "horizon_days": horizon,
        "snapshot_date": SNAPSHOT_DATE,
        "snapshot_label": SNAPSHOT_LABEL,
        "summary": {
            "total_cells": len(cells),
            "available_cells": len(available_scores),
            "mean_risk_score": round(float(np.mean(available_scores)), 1),
            "high_count": counts["High"],
            "moderate_count": counts["Moderate"],
            "low_count": counts["Low"],
            "na_count": counts["N/A"],
        },
        "levels": {
            "low": counts["Low"],
            "moderate": counts["Moderate"],
            "high": counts["High"],
            "na": counts["N/A"],
        },
        "prediction_reproduction_check": {
            "saved_rows_compared": len(check),
            "max_abs_difference": max_abs_difference,
            "passed": True,
        },
        "is_live": False,
    }
    return cells, summary


def metrics_payload() -> dict[str, Any]:
    return {
        "model_name": "XGBoost",
        "metric": "MAE",
        "lower_is_better": True,
        "evaluation_protocol": "Train 2015–2022 · validation 2023 · frozen-model test 2024–2025",
        "evaluation_context": "Held-out historical evaluation",
        "horizons": {
            "16": {
                "validation": {
                    "model_mae": 0.005072,
                    "baseline_mae": 0.005446,
                    "improvement_pct": 6.9,
                },
                "test": {
                    "model_mae": 0.004711,
                    "baseline_mae": 0.004840,
                    "improvement_pct": 2.7,
                },
            },
            "32": {
                "validation": {
                    "model_mae": 0.006047,
                    "baseline_mae": 0.006907,
                    "improvement_pct": 12.4,
                },
                "test": {
                    "model_mae": 0.005536,
                    "baseline_mae": 0.006193,
                    "improvement_pct": 10.6,
                },
            },
        },
        "note": (
            "Metrics were read from the supplied BADIA_AI_XGBoost_results artifact. "
            "The demo build does not re-fit the model."
        ),
        "is_live": False,
    }


def metadata_payload() -> dict[str, Any]:
    return {
        "project_name": "BADIA AI",
        "scope": "Jordan",
        "data_period": "2015–2025",
        "snapshot_year": SNAPSHOT_YEAR,
        "snapshot_period": SNAPSHOT_PERIOD,
        "snapshot_date": SNAPSHOT_DATE,
        "snapshot_label": SNAPSHOT_LABEL,
        "serving_mode": "saved_local_snapshot",
        "is_live": False,
        "source": (
            "Prepared satellite-derived vegetation and environmental observations, "
            "seasonal anomaly tables, and saved XGBoost model artifacts supplied with the project."
        ),
        "model_features": FEATURES,
        "risk_definition": (
            "Risk score = empirical percentile (0–100) of predicted vegetation-stress severity "
            "(-predicted anomaly) against 2015–2022 target anomalies for the same source period "
            "and horizon. It is a relative index, not a probability."
        ),
        "risk_thresholds": {
            "Low": "0.0–39.9",
            "Moderate": "40.0–69.9",
            "High": "70.0–100.0",
            "N/A": "Core current vegetation signal unavailable",
        },
        "top_factors_method": (
            "Per-cell TreeSHAP contribution magnitude from the saved model. "
            "Factors are model associations, not causal explanations."
        ),
        "geometry_note": (
            "Map polygons are approximate squares reconstructed from each centroid and area; "
            "they are not official cadastral or administrative boundaries."
        ),
        "disclaimer": (
            "Satellite-derived vegetation anomaly risk indicator; not a field-verified "
            "desertification diagnosis, not a causal claim, and not a live forecast."
        ),
        "limitations": [
            "No 2026 inputs were supplied; the demo uses the latest common model-evaluable 2025 period.",
            "The map is retrospective and intended for product demonstration and decision support.",
            "Field observations are required before operational or land-management decisions.",
            "The risk index is calibrated to historical seasonal distributions and must not be read as probability.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--frontend-public", type=Path)
    args = parser.parse_args()
    source_dir = args.source_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    seasonal_path = locate(
        source_dir,
        "BADIA_AI_seasonal_anomaly_ready/badia_all_years_with_seasonal_anomaly.csv",
    )
    xgb_dir = source_dir / "BADIA_AI_XGBoost_results"
    seasonal = pd.read_csv(seasonal_path)
    seasonal["period_sin"] = np.sin(2 * np.pi * (seasonal["period_index"] - 1) / 23)
    seasonal["period_cos"] = np.cos(2 * np.pi * (seasonal["period_index"] - 1) / 23)
    snapshot = seasonal[
        (seasonal["year"] == SNAPSHOT_YEAR)
        & (seasonal["period_index"] == SNAPSHOT_PERIOD)
    ].copy()
    training = seasonal[seasonal["split"].str.lower() == "train"].copy()
    if snapshot["cell_id"].nunique() != 968:
        raise RuntimeError(f"Expected 968 snapshot cells, found {snapshot['cell_id'].nunique()}")

    all_rows: list[dict[str, Any]] = []
    summaries: dict[str, Any] = {}
    geojson_by_horizon: dict[str, Any] = {}
    for horizon in (16, 32):
        cells, summary = build_horizon(
            horizon,
            snapshot,
            training,
            locate(xgb_dir, f"xgboost_{horizon}d.json"),
            locate(xgb_dir, f"predictions_{horizon}d_test.csv"),
        )
        summaries[str(horizon)] = summary
        all_rows.extend(cells)
        write_json(
            output_dir / f"cells_{horizon}.json",
            {
                "type": "CellCollection",
                "scope": "Jordan",
                "horizon_days": horizon,
                "snapshot_date": SNAPSHOT_DATE,
                "snapshot_label": SNAPSHOT_LABEL,
                "is_live": False,
                "cells": cells,
            },
        )
        geojson = {
            "type": "FeatureCollection",
            "name": f"BADIA AI +{horizon}-day historical demo snapshot",
            "scope": "Jordan",
            "horizon_days": horizon,
            "snapshot_date": SNAPSHOT_DATE,
            "snapshot_label": SNAPSHOT_LABEL,
            "is_live": False,
            "features": [
                {
                    "type": "Feature",
                    "id": cell["cell_id"],
                    "geometry": approximate_square(cell["lat"], cell["lon"], cell["area_km2"]),
                    "properties": cell,
                }
                for cell in cells
            ],
        }
        geojson_by_horizon[str(horizon)] = geojson
        write_json(output_dir / f"cells_{horizon}.geojson", geojson)

    flat_rows = []
    for cell in all_rows:
        flat = {key: value for key, value in cell.items() if key not in {"top_factors", "data_quality"}}
        flat["top_factors"] = json.dumps(cell["top_factors"], ensure_ascii=False)
        flat["data_quality"] = json.dumps(cell["data_quality"], ensure_ascii=False)
        flat_rows.append(flat)
    pd.DataFrame(flat_rows).to_csv(output_dir / "cells_latest.csv", index=False, encoding="utf-8-sig")

    metrics = metrics_payload()
    metadata = metadata_payload()
    national = {
        "scope": "Jordan",
        "snapshot_date": SNAPSHOT_DATE,
        "snapshot_label": SNAPSHOT_LABEL,
        "horizons": summaries,
        "is_live": False,
        "disclaimer": metadata["disclaimer"],
    }
    write_json(output_dir / "metrics.json", metrics)
    write_json(output_dir / "metadata.json", metadata)
    write_json(output_dir / "national_summary.json", national)

    model_out = output_dir.parent / "models"
    model_out.mkdir(parents=True, exist_ok=True)
    compact_files = [
        "xgboost_16d.json",
        "xgboost_32d.json",
        "xgboost_evaluation.csv",
        "feature_importance_16d.csv",
        "feature_importance_32d.csv",
        "tuning_16d.csv",
        "tuning_32d.csv",
    ]
    for filename in compact_files:
        shutil.copy2(locate(xgb_dir, filename), model_out / filename)

    manifest_sources = [
        seasonal_path,
        locate(source_dir, "BADIA_AI_XGBoost_results.zip"),
        locate(source_dir, "BADIA_AI_targets_16d_32d.zip"),
        locate(source_dir, "BADIA_AI_seasonal_anomaly_ready.zip"),
        locate(source_dir, "BADIA_AI_prepared_2015_2025.zip"),
        locate(source_dir, "BADIA_AI_baseline_evaluation.csv"),
    ]
    write_json(
        output_dir / "provenance.json",
        {
            "generated_from": [
                {"name": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)}
                for path in manifest_sources
            ],
            "generated_snapshot": SNAPSHOT_LABEL,
            "retrained": False,
            "saved_models_reused": True,
        },
    )

    if args.frontend_public:
        bundle = {
            "cells": geojson_by_horizon,
            "areas": summaries,
            "metrics": metrics,
            "metadata": metadata,
        }
        write_json(args.frontend_public.resolve() / "demo-data.json", bundle)

    print(
        json.dumps(
            {
                "snapshot": SNAPSHOT_LABEL,
                "cells_per_horizon": len(snapshot),
                "summaries": summaries,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
