from datetime import date
from pathlib import Path

import numpy as np

from app.live_features import (
    period_end,
    period_index_for_date,
    period_start,
    percentile_scores,
    seasonal_encoding,
    shift_period,
)


def test_period_21_matches_packaged_snapshot_nominal_end():
    assert period_start(2025, 21) == date(2025, 11, 17)
    assert period_end(2025, 21) == date(2025, 12, 2)
    assert period_index_for_date(date(2025, 11, 17)) == 21


def test_period_shift_for_horizons():
    assert shift_period(2026, 15, 1) == (2026, 16)
    assert shift_period(2026, 15, 2) == (2026, 17)
    assert shift_period(2026, 23, 1) == (2027, 1)


def test_seasonal_encoding_period_one():
    sine, cosine = seasonal_encoding(1)
    assert abs(sine) < 1e-12
    assert abs(cosine - 1.0) < 1e-12


def test_percentile_scores_matches_demo_definition():
    scores = percentile_scores([-0.1, 0.0, 0.1], [-0.2, -0.1, 0.0, 0.1])
    assert np.allclose(scores, [75.0, 50.0, 25.0])


def test_earth_engine_updater_preserves_validated_mean_and_inclusive_latest_start():
    source = (Path(__file__).resolve().parents[1] / "app" / "earth_engine_source.py").read_text("utf-8")
    baseline = source.split("def _seasonal_baseline", 1)[1].split("def _feature_collection", 1)[0]
    anchor = source.split("def latest_common_anchor", 1)[1].split("def _mask_modis", 1)[0]
    assert ".mean().rename(\"ndvi_baseline\")" in baseline
    assert "latest_allowed_start + timedelta(days=1)" in anchor
