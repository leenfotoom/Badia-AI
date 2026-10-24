"""Daily Environmental Stress Index (ESI): the supervised target.

ESI(c, D) in [0,1] is a fixed-weight composite of *observed* day-D conditions, each expressed as
a climatological percentile (high = more stress):
  soil-moisture deficit (1 - pct SM), 30-day rain deficit (1 - pct rain30), atmospheric dryness
  (pct of daily-max VPD) and heat (pct of daily Tmax).
It is evaluable every day from reanalysis, needs no interpolation, and is an index of
meteorological/hydrological stress - NOT a measured vegetation outcome or a probability.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .climatology import Climatology, clim_frame
from .config import ESI_WEIGHTS


def compute_esi(obs: pd.DataFrame, clim: Climatology) -> pd.DataFrame:
    f = clim_frame(obs)
    doy = f["date"].dt.dayofyear.to_numpy()
    ids = f["cell_id"].to_numpy()
    comp = {
        "sm": 1.0 - clim.percentile("sm", ids, doy, f["sm"]),
        "rain": 1.0 - clim.percentile("rain30", ids, doy, f["rain30"]),
        "vpd": clim.percentile("vpd", ids, doy, f["vpd"]),
        "heat": clim.percentile("tmax", ids, doy, f["tmax"]),
    }
    mat = np.column_stack([comp[k] for k in ESI_WEIGHTS])
    w = np.array(list(ESI_WEIGHTS.values()))
    esi = np.where(np.isfinite(mat).all(axis=1), mat @ w, np.nan)   # all components required
    out = f[["cell_id", "date"]].copy()
    out["esi"] = esi
    return out
