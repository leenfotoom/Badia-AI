"""SYNTHETIC weather generator for tests and UI preview ONLY.

Output has the same schema as the real providers. Anything trained or scored on it must be
labelled synthetic and may never be written to the production model/forecast paths.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import LEADS
from .providers import vpd_kpa


def make_cells(n: int = 24, seed: int = 0) -> pd.DataFrame:
    r = np.random.default_rng(seed)
    return pd.DataFrame({"cell_id": [f"S{i:03d}" for i in range(n)],
                         "latitude": r.uniform(29.2, 32.5, n), "longitude": r.uniform(35.0, 38.8, n),
                         "elevation_m": r.uniform(-300, 1200, n)})


def make_panel(cells: pd.DataFrame, start="2015-01-01", end="2025-12-31", seed: int = 1,
               fc_start="2024-01-01") -> tuple[pd.DataFrame, pd.DataFrame]:
    r = np.random.default_rng(seed)
    days = pd.date_range(start, end, freq="D")
    n = len(days)
    doy = days.dayofyear.to_numpy()
    season = np.cos(2 * np.pi * (doy - 200) / 365.25)            # +1 mid-summer
    wet = np.clip(-season, 0, 1)
    regional_t = np.zeros(n)
    for i in range(1, n):
        regional_t[i] = 0.8 * regional_t[i - 1] + r.normal(0, 1.2)
    regional_rain = r.random(n)
    obs_rows, fc_rows = [], []
    for c in cells.itertuples():
        wetness = np.clip((c.latitude - 29) / 4, 0.1, 1.0)
        temp = 21 + 12 * season - 0.004 * c.elevation_m + regional_t + r.normal(0, 1.0, n)
        dew = temp - (10 + 14 * np.clip(season, 0, 1) + 6 * (1 - wetness)) + r.normal(0, 1.5, n)
        p_rain = 0.28 * wet * wetness * (regional_rain < 0.7)
        rain = np.where(r.random(n) < p_rain + 0.1 * (regional_rain > 0.9) * wet, r.exponential(7, n) * wetness, 0.0)
        sm = np.zeros(n)
        sm[0] = 0.12
        for i in range(1, n):
            et = 0.0012 * max(temp[i] - 10, 0) * (0.5 + sm[i - 1] * 3)
            sm[i] = np.clip(sm[i - 1] - et + 0.006 * rain[i] + 0.0, 0.03, 0.42)
        vpd = vpd_kpa(temp, dew)
        obs_rows.append(pd.DataFrame({
            "cell_id": c.cell_id, "date": days, "precip_mm": rain, "tmax_c": temp + 6, "tmin_c": temp - 6,
            "tmean_c": temp, "vpd_max_kpa": vpd * 1.8, "sm_0_7": sm}))
        for lead in LEADS:
            s = 0.5 + 0.35 * lead
            ft = temp + r.normal(0, s, n)
            fd = dew + r.normal(0, s, n)
            fr = np.clip(rain * np.exp(r.normal(0, 0.25 + 0.12 * lead, n)) +
                         (r.random(n) < 0.03 * lead) * r.exponential(3, n) - (r.random(n) < 0.03 * lead) * rain, 0, None)
            d = pd.DataFrame({"cell_id": c.cell_id, "valid_date": days, "lead_days": lead, "precip_mm": fr,
                              "tmax_c": ft + 6, "tmin_c": ft - 6, "tmean_c": ft, "vpd_max_kpa": vpd_kpa(ft, fd) * 1.8})
            fc_rows.append(d[d["valid_date"] >= pd.Timestamp(fc_start)])
    return pd.concat(obs_rows, ignore_index=True), pd.concat(fc_rows, ignore_index=True)
