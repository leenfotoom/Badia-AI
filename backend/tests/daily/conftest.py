import numpy as np
import pandas as pd
import pytest

from backend.app.daily import synthetic as S
from backend.app.daily.climatology import Climatology
from backend.app.daily.features import build_features
from backend.app.daily.target import compute_esi


@pytest.fixture(scope="session")
def panel():
    cells = S.make_cells(12, seed=5)
    obs, fc = S.make_panel(cells, end="2025-12-31", seed=11)
    clim = Climatology.fit(obs)
    esi = compute_esi(obs, clim)
    static = cells[["cell_id", "elevation_m"]]
    df = build_features(cells, obs, fc, clim, static=static, esi=esi)
    return dict(cells=cells, obs=obs, fc=fc, clim=clim, esi=esi, static=static, df=df)
