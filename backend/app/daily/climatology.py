"""Per-cell, per-day-of-year quantile climatology (fixed reference period) -> percentiles."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from .config import CLIM_BIN_DAYS, CLIM_WINDOW_DAYS, CLIM_YEARS, QUANTILE_NODES

VARS = ("sm", "vpd", "tmax", "rain30")
_Q = np.linspace(0, 1, QUANTILE_NODES)
N_BINS = 366 // CLIM_BIN_DAYS + 1


def _bin(doy: np.ndarray) -> np.ndarray:
    return np.minimum((np.asarray(doy) - 1) // CLIM_BIN_DAYS, N_BINS - 1)


def clim_frame(obs: pd.DataFrame) -> pd.DataFrame:
    """obs_daily -> frame with date, cell_id, sm, vpd, tmax, rain30 (30-day trailing rainfall)."""
    df = obs.copy()
    df["cell_id"] = df["cell_id"].astype(str)
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    expanded = []
    for cell_id, group in df.sort_values(["cell_id", "date"]).groupby("cell_id", sort=True):
        if group["date"].duplicated().any():
            raise ValueError(f"duplicate climatology observations for cell {cell_id}")
        group = group.set_index("date")
        full_index = pd.date_range(group.index.min(), group.index.max(), freq="D")
        group = group.reindex(full_index)
        group["cell_id"] = cell_id
        # Reindexing ensures a 30-row window really means 30 calendar days. Missing
        # observations remain missing instead of silently shrinking the time interval.
        group["rain30"] = group["precip_mm"].rolling(30, min_periods=27).sum()
        group.index.name = "date"
        expanded.append(group.reset_index())
    if not expanded:
        return pd.DataFrame(columns=["cell_id", "date", "sm", "vpd", "tmax", "rain30"])
    df = pd.concat(expanded, ignore_index=True)
    return df.rename(columns={"sm_0_7": "sm", "vpd_max_kpa": "vpd", "tmax_c": "tmax"})[
        ["cell_id", "date", "sm", "vpd", "tmax", "rain30"]]


class Climatology:
    def __init__(self, cell_ids: list[str], nodes: np.ndarray, years: tuple[int, int],
                 anchor_for_cell: list[str] | None = None) -> None:
        self.cell_ids = [str(cell) for cell in cell_ids]
        self.nodes, self.years = nodes, years
        self.anchor_for_cell = ([str(cell) for cell in anchor_for_cell]
                                if anchor_for_cell is not None else list(self.cell_ids))
        if len(self.cell_ids) != len(self.nodes) or len(self.cell_ids) != len(self.anchor_for_cell):
            raise ValueError("climatology cells, nodes and anchor mapping have inconsistent lengths")
        self.index = {c: i for i, c in enumerate(self.cell_ids)}

    @classmethod
    def fit(cls, obs: pd.DataFrame) -> "Climatology":
        lo, hi = CLIM_YEARS
        f = clim_frame(obs)
        f = f[(f["date"].dt.year >= lo) & (f["date"].dt.year <= hi)]
        if f.empty:
            raise ValueError("no observations inside the climatology reference period")
        cells = sorted(f["cell_id"].unique())
        nodes = np.full((len(cells), N_BINS, len(VARS), QUANTILE_NODES), np.nan, dtype=np.float32)
        doy = f["date"].dt.dayofyear.to_numpy()
        for ci, cell in enumerate(cells):
            sub = f[f["cell_id"] == cell]
            sdoy = sub["date"].dt.dayofyear.to_numpy()
            for b in range(N_BINS):
                centre = b * CLIM_BIN_DAYS + (CLIM_BIN_DAYS + 1) / 2
                dist = np.abs(((sdoy - centre + 183) % 366) - 183)
                m = dist <= CLIM_WINDOW_DAYS
                if m.sum() < 30:
                    continue
                for vi, v in enumerate(VARS):
                    vals = sub[v].to_numpy()[m]
                    vals = vals[np.isfinite(vals)]
                    if len(vals) >= 30:
                        nodes[ci, b, vi] = np.quantile(vals, _Q)
        return cls(cells, nodes, CLIM_YEARS, cells)

    def expand_nearest(self, anchor_cells: pd.DataFrame, target_cells: pd.DataFrame) -> tuple["Climatology", pd.DataFrame]:
        """Copy each fitted anchor's nodes to the nearest target cell.

        Ties are deterministic because candidate anchors are sorted by ``cell_id``. The
        returned mapping makes the approximation auditable and is persisted separately by
        the dataset builder.
        """
        required = {"cell_id", "latitude", "longitude"}
        if not required.issubset(anchor_cells.columns) or not required.issubset(target_cells.columns):
            raise ValueError("anchor and target cells require cell_id, latitude and longitude")
        anchors = anchor_cells[list(required)].copy()
        targets = target_cells[list(required)].copy()
        anchors["cell_id"] = anchors["cell_id"].astype(str)
        targets["cell_id"] = targets["cell_id"].astype(str)
        anchors = anchors.drop_duplicates("cell_id").sort_values("cell_id").reset_index(drop=True)
        targets = targets.drop_duplicates("cell_id").sort_values("cell_id").reset_index(drop=True)
        if anchors.empty or targets.empty:
            raise ValueError("at least one anchor and target cell is required")
        missing = sorted(set(anchors["cell_id"]) - set(self.index))
        if missing:
            raise ValueError(f"anchor cells are not fitted in climatology: {missing[:3]}")

        alat = np.radians(anchors["latitude"].to_numpy(dtype=float))[None, :]
        alon = np.radians(anchors["longitude"].to_numpy(dtype=float))[None, :]
        tlat = np.radians(targets["latitude"].to_numpy(dtype=float))[:, None]
        tlon = np.radians(targets["longitude"].to_numpy(dtype=float))[:, None]
        dlat, dlon = alat - tlat, alon - tlon
        hav = np.sin(dlat / 2) ** 2 + np.cos(tlat) * np.cos(alat) * np.sin(dlon / 2) ** 2
        distance = 6371.0088 * 2 * np.arcsin(np.sqrt(np.clip(hav, 0, 1)))
        nearest = np.argmin(distance, axis=1)
        anchor_ids = anchors.iloc[nearest]["cell_id"].tolist()
        copied = np.stack([self.nodes[self.index[anchor_id]] for anchor_id in anchor_ids])
        expanded = Climatology(targets["cell_id"].tolist(), copied, self.years, anchor_ids)
        selected = anchors.iloc[nearest].reset_index(drop=True)
        mapping = pd.DataFrame({
            "cell_id": targets["cell_id"],
            "latitude": targets["latitude"].astype(float),
            "longitude": targets["longitude"].astype(float),
            "climatology_anchor_cell_id": anchor_ids,
            "anchor_latitude": selected["latitude"].astype(float),
            "anchor_longitude": selected["longitude"].astype(float),
            "distance_km": distance[np.arange(len(targets)), nearest],
            "is_fitted_anchor": targets["cell_id"].to_numpy() == np.asarray(anchor_ids),
        })
        return expanded, mapping

    def percentile(self, var: str, cell_ids, doy, values) -> np.ndarray:
        """Percentile in [0,1]; NaN if the cell/bin/value is unknown. Ties interpolate."""
        vi = VARS.index(var)
        ci = np.array([self.index.get(c, -1) for c in cell_ids])
        b = _bin(np.asarray(doy))
        vals = np.asarray(values, dtype=float)
        out = np.full(len(vals), np.nan)
        ok = (ci >= 0) & np.isfinite(vals)
        if not ok.any():
            return out
        nd = self.nodes[ci[ok], b[ok], vi]                       # (n, 21)
        v = vals[ok]
        valid = np.isfinite(nd).all(axis=1)
        lo = (nd < v[:, None]).sum(1)                             # nodes strictly below
        hi = (nd <= v[:, None]).sum(1)                            # nodes at or below
        pos = (lo + hi) / 2.0                                     # mid-rank for ties
        res = np.where(pos <= 0, 0.0, np.where(pos >= QUANTILE_NODES, 1.0, 0.0))
        interior = (pos > 0) & (pos < QUANTILE_NODES)
        if interior.any():
            idx = np.clip(np.floor(pos[interior]).astype(int) - 1, 0, QUANTILE_NODES - 2)
            r = np.arange(len(v))[interior]
            a, c2 = nd[r, idx], nd[r, idx + 1]
            frac = np.where(c2 > a, (v[interior] - a) / np.where(c2 > a, c2 - a, 1), 0.5)
            res[interior] = _Q[idx] + np.clip(frac, 0, 1) * (_Q[idx + 1] - _Q[idx])
        res[~valid] = np.nan
        out[ok] = res
        return out

    def save(self, path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".npz")
        os.close(fd)
        try:
            np.savez_compressed(
                temporary,
                nodes=self.nodes,
                cells=np.asarray(self.cell_ids),
                years=np.asarray(self.years),
                anchor_for_cell=np.asarray(self.anchor_for_cell),
            )
            with open(temporary, "rb+") as stream:
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @classmethod
    def load(cls, path) -> "Climatology":
        with np.load(path, allow_pickle=False) as z:
            cells = [str(value) for value in z["cells"]]
            anchors = ([str(value) for value in z["anchor_for_cell"]]
                       if "anchor_for_cell" in z.files else cells)
            return cls(cells, z["nodes"].copy(), tuple(int(y) for y in z["years"]), anchors)
