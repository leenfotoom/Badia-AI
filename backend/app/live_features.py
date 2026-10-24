"""Pure helpers for BADIA AI near-real-time feature generation.

These helpers contain no Earth Engine calls, so they can be unit tested offline.
The live data adapter is intentionally separate from the saved demo DataStore.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Iterable

import numpy as np


COMPOSITE_DAYS = 16
PERIODS_PER_YEAR = 23
TRAIN_YEARS = tuple(range(2015, 2023))
NDVI_BASELINE_YEARS = tuple(range(2003, 2023))
MODEL_FEATURES = [
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
CORE_FEATURES = ("ndvi", "ndvi_anomaly_current")


def period_start(year: int, period_index: int) -> date:
    """Return the nominal MODIS 16-day composite start date."""
    if not 1 <= period_index <= PERIODS_PER_YEAR:
        raise ValueError("period_index must be in 1..23")
    return date(year, 1, 1) + timedelta(days=(period_index - 1) * COMPOSITE_DAYS)


def period_end(year: int, period_index: int) -> date:
    """Return the nominal inclusive end date for a 16-day source period."""
    return period_start(year, period_index) + timedelta(days=COMPOSITE_DAYS - 1)


def period_index_for_date(value: date) -> int:
    """Map a MODIS composite start date to BADIA's 1..23 seasonal period."""
    doy = value.timetuple().tm_yday
    return min(((doy - 1) // COMPOSITE_DAYS) + 1, PERIODS_PER_YEAR)


def shift_period(year: int, period_index: int, steps: int) -> tuple[int, int]:
    """Shift a BADIA seasonal period by whole 16-day steps."""
    if steps < 0:
        raise ValueError("steps must be >= 0")
    zero_based = (period_index - 1) + steps
    return year + zero_based // PERIODS_PER_YEAR, (zero_based % PERIODS_PER_YEAR) + 1


def seasonal_encoding(period_index: int) -> tuple[float, float]:
    if not 1 <= period_index <= PERIODS_PER_YEAR:
        raise ValueError("period_index must be in 1..23")
    angle = 2.0 * math.pi * (period_index - 1) / PERIODS_PER_YEAR
    return math.sin(angle), math.cos(angle)


def percentile_scores(predictions: Iterable[float], reference: Iterable[float]) -> np.ndarray:
    """Replicate the frozen demo's vegetation-stress percentile definition."""
    reference_array = np.asarray(list(reference), dtype=float)
    reference_array = np.sort(-reference_array[np.isfinite(reference_array)])
    if not len(reference_array):
        raise ValueError("Risk reference distribution is empty")
    prediction_array = np.asarray(list(predictions), dtype=float)
    severity = -prediction_array
    ranks = np.searchsorted(reference_array, severity, side="right")
    return np.clip(100.0 * ranks / len(reference_array), 0.0, 100.0)


def risk_level(score: float | None) -> str:
    if score is None or not math.isfinite(score):
        return "N/A"
    if score < 40:
        return "Low"
    if score < 70:
        return "Moderate"
    return "High"


def finite_or_none(value: object, digits: int | None = None) -> float | int | str | None:
    if value is None:
        return None
    if isinstance(value, (int, np.integer)):
        return int(value)
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(numeric):
        return None
    return round(numeric, digits) if digits is not None else numeric
