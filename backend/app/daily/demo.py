"""UI-preview generator. Produces a snapshot explicitly flagged is_synthetic=True. Never used in production paths."""
from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import synthetic as S
from .climatology import Climatology
from .dataset import load_cells
from .features import build_features
from .modeling import Splits, save_bundle, train_candidate, load_bundle
from .pipeline import build_snapshot
from .store import ROOT, Paths, write_json_atomic
from .target import compute_esi
from datetime import timedelta


def make_demo_snapshot(paths: Paths, n_cells: int = 968) -> Path:
    cells = load_cells(ROOT).head(n_cells).copy()
    cells["elevation_m"] = np.random.default_rng(3).uniform(-300, 1200, len(cells))
    # synthetic climate for a modest subset to train, then score every cell
    sub = cells.iloc[:: max(len(cells) // 24, 1)].head(24)
    obs, fc = S.make_panel(sub, end="2026-09-30")
    clim = Climatology.fit(obs)
    esi = compute_esi(obs, clim)
    df = build_features(sub, obs, fc, clim, static=sub[["cell_id", "elevation_m"]], esi=esi)
    res = train_candidate(df, Splits(pd.Timestamp("2025-06-30"), pd.Timestamp("2025-10-31")), esi, with_spatial=False)
    champion = {"pointer": {"version": "SYNTHETIC-DEMO", "promoted_at": None}, "model": res.model,
                "calibrator": res.calibrator, "meta": {"metrics": res.metrics, "info": res.info}}
    obs_all, fc_all = S.make_panel(cells, end="2026-09-30", fc_start="2026-09-01", seed=9)
    clim_all = Climatology.fit(obs_all)
    issue = pd.Timestamp("2026-09-30").date()
    now = datetime(2026, 10, 1, 6, 0, tzinfo=timezone.utc)
    fetched = {"forecast_fetched_at": now.isoformat(), "latest_observation_date": str(issue - timedelta(days=5))}
    from .pipeline import vegetation_context
    snap = build_snapshot(champion, cells, cells[["cell_id", "elevation_m"]], clim_all, obs_all, fc_all, issue,
                          fetched, vegetation_context(ROOT / "data"), now)
    snap["is_synthetic"] = True
    snap["product"] += " (SYNTHETIC DEMONSTRATION - NOT A REAL FORECAST)"
    out = paths.snapshots / "latest.json"
    write_json_atomic(out, snap)
    return out
