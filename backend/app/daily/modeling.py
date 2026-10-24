"""Training, honest validation, baselines, 0-100 calibration and TreeSHAP reasons."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

from .config import FEATURES_V1, LEADS, SCHEMA_VERSION
from .features import feature_matrix

PARAMS = dict(n_estimators=600, learning_rate=0.05, max_depth=5, min_child_weight=20, subsample=0.8,
              colsample_bytree=0.8, reg_lambda=5.0, tree_method="hist", early_stopping_rounds=40,
              random_state=42, n_jobs=2)

SEASON_MONTHS = {
    "DJF": (12, 1, 2),
    "MAM": (3, 4, 5),
    "JJA": (6, 7, 8),
    "SON": (9, 10, 11),
}


@dataclass
class Splits:
    train_end: pd.Timestamp
    val_end: pd.Timestamp
    embargo_days: int = 7


def split_by_time(df: pd.DataFrame, sp: Splits) -> dict[str, pd.DataFrame]:
    """Strict time split on ISSUE day with a purge: a row's target date must also lie inside its window."""
    e = pd.Timedelta(days=sp.embargo_days)
    tr = df[(df["issue_day"] <= sp.train_end) & (df["target_date"] <= sp.train_end)]
    va = df[(df["issue_day"] > sp.train_end + e) & (df["issue_day"] <= sp.val_end) & (df["target_date"] <= sp.val_end)]
    te = df[(df["issue_day"] > sp.val_end + e)]
    return {"train": tr, "val": va, "test": te}


def _auc(y: np.ndarray, s: np.ndarray) -> float | None:
    pos, neg = s[y == 1], s[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        # AUC is undefined when a seasonal holdout contains only one class.  It is
        # an optional diagnostic for this regression model, so preserve that fact
        # as JSON null instead of emitting non-standard NaN.
        return None
    r = pd.Series(np.concatenate([pos, neg])).rank().to_numpy()
    return float((r[: len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def _r2(y: np.ndarray, prediction: np.ndarray) -> float | None:
    """Coefficient of determination on the evaluated rows.

    R² is undefined when fewer than two observations exist or the observed target
    has zero variance. Negative values are valid and are intentionally preserved.
    """
    if len(y) < 2:
        return None
    denominator = float(np.sum((y - np.mean(y)) ** 2))
    if not np.isfinite(denominator) or denominator <= 0:
        return None
    numerator = float(np.sum((y - prediction) ** 2))
    return float(1.0 - numerator / denominator)


def _metrics(y: np.ndarray, p: np.ndarray, pers: np.ndarray, clim: np.ndarray, hi: float) -> dict:
    model_ok = np.isfinite(y) & np.isfinite(p)
    ym, pm = y[model_ok], p[model_ok]
    if not len(ym):
        return (
            {k: float("nan") for k in (
                "mae", "rmse", "spearman", "mae_persistence", "mae_climatology",
               "mae_model_on_persistence_rows", "mae_model_on_climatology_rows",
               "skill_vs_persistence", "skill_vs_climatology")}
            | {"n": 0, "n_persistence_common": 0, "n_climatology_common": 0,
               "auc_high_stress": None, "r2": None}
        )

    # Baseline skill must compare predictions on exactly the same rows.  The old
    # implementation compared model MAE on every row with persistence MAE on a
    # smaller subset whenever the lagged label was missing, which could make the
    # reported skill optimistic or pessimistic for purely bookkeeping reasons.
    po = model_ok & np.isfinite(pers)
    co = model_ok & np.isfinite(clim)
    mae = float(np.mean(np.abs(ym - pm)))
    model_p = float(np.mean(np.abs(y[po] - p[po]))) if po.any() else float("nan")
    base_p = float(np.mean(np.abs(y[po] - pers[po]))) if po.any() else float("nan")
    model_c = float(np.mean(np.abs(y[co] - p[co]))) if co.any() else float("nan")
    base_c = float(np.mean(np.abs(y[co] - clim[co]))) if co.any() else float("nan")
    out = {"n": int(len(ym)), "mae": mae, "rmse": float(np.sqrt(np.mean((ym - pm) ** 2))),
           "r2": _r2(ym, pm),
           "spearman": float(pd.Series(ym).corr(pd.Series(pm), method="spearman")),
           "n_persistence_common": int(po.sum()), "n_climatology_common": int(co.sum()),
           "mae_model_on_persistence_rows": model_p, "mae_persistence": base_p,
           "mae_model_on_climatology_rows": model_c, "mae_climatology": base_c,
           "auc_high_stress": _auc((ym >= hi).astype(int), pm)}
    out["skill_vs_persistence"] = 1 - model_p / base_p if np.isfinite(base_p) and base_p > 0 else float("nan")
    out["skill_vs_climatology"] = 1 - model_c / base_c if np.isfinite(base_c) and base_c > 0 else float("nan")
    return out


def baselines(train: pd.DataFrame, other: pd.DataFrame, esi_lookup: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    """persistence = last OBSERVED esi (issue-5d, i.e. what was known); climatology = train cell-month mean."""
    last_obs = pd.MultiIndex.from_arrays([other["cell_id"], other["obs_end"]])
    pers = esi_lookup.reindex(last_obs).to_numpy()
    key = train.assign(m=train["target_date"].dt.month).groupby(["cell_id", "m"])["esi_target"].mean()
    mk = pd.MultiIndex.from_arrays([other["cell_id"], other["target_date"].dt.month])
    clim = key.reindex(mk).to_numpy()
    clim = np.where(np.isfinite(clim), clim, float(train["esi_target"].mean()))
    return pers, clim


def evaluate(model: xgb.XGBRegressor, df: pd.DataFrame, train: pd.DataFrame, esi_lookup: pd.Series, hi: float) -> dict:
    d = df.dropna(subset=["esi_target"])
    p = model.predict(feature_matrix(d))
    pers, clim = baselines(train, d, esi_lookup)
    target = d["esi_target"].to_numpy()
    res = {"overall": _metrics(target, p, pers, clim, hi), "by_lead": {}, "by_season": {}}
    for L in LEADS:
        m = (d["lead_days"] == L).to_numpy()
        if m.sum() >= 50:
            res["by_lead"][str(L)] = _metrics(target[m], p[m], pers[m], clim[m], hi)
    months = d["target_date"].dt.month.to_numpy()
    for season, season_months in SEASON_MONTHS.items():
        m = np.isin(months, season_months)
        if m.any():
            seasonal = _metrics(target[m], p[m], pers[m], clim[m], hi)
            seasonal.update({"available": True, "months": list(season_months), "date_basis": "target_date"})
        else:
            seasonal = {"n": 0, "available": False, "months": list(season_months),
                        "date_basis": "target_date", "reason": "no target dates in evaluation window"}
        res["by_season"][season] = seasonal
    return res


def spatial_cv(train: pd.DataFrame, k: int = 4) -> dict:
    """Leave-latitude-band-out: does the model generalise to cells it has never seen?"""
    d = train.dropna(subset=["esi_target"]).copy()
    cells = d.groupby("cell_id")["latitude"].first().sort_values()
    band = pd.Series(np.arange(len(cells)) * k // max(len(cells), 1), index=cells.index)
    d["band"] = d["cell_id"].map(band)
    maes, rhos = [], []
    for b in range(k):
        tr, te = d[d["band"] != b], d[d["band"] == b]
        if tr.empty or te.empty:
            continue
        m = xgb.XGBRegressor(**{**PARAMS, "early_stopping_rounds": None, "n_estimators": 200})
        m.fit(feature_matrix(tr), tr["esi_target"])
        p = m.predict(feature_matrix(te))
        maes.append(float(np.mean(np.abs(p - te["esi_target"]))))
        rhos.append(float(pd.Series(p).corr(te["esi_target"].reset_index(drop=True), method="spearman")))
    return {"folds": len(maes), "mae_mean": float(np.mean(maes)) if maes else None,
            "spearman_mean": float(np.mean(rhos)) if rhos else None, "scheme": f"leave-{k}-latitude-band-out"}


@dataclass
class Calibrator:
    """score = percentile of predicted ESI inside the training-period distribution of OBSERVED ESI.
    A relative severity index (0-100), NOT a probability."""
    reference: np.ndarray = field(default_factory=lambda: np.array([]))

    def score(self, pred: np.ndarray) -> np.ndarray:
        if not len(self.reference):
            raise ValueError("empty calibration reference")
        return np.clip(100.0 * np.searchsorted(self.reference, pred, side="right") / len(self.reference), 0, 100)

    def to_json(self) -> list:
        return [round(float(x), 5) for x in np.quantile(self.reference, np.linspace(0, 1, 201))]

    @classmethod
    def from_json(cls, q: list) -> "Calibrator":
        return cls(np.sort(np.asarray(q, dtype=float)))


@dataclass
class TrainResult:
    model: xgb.XGBRegressor
    calibrator: Calibrator
    metrics: dict
    info: dict


def train_candidate(df: pd.DataFrame, sp: Splits, esi: pd.DataFrame, seed: int = 42, with_spatial: bool = True) -> TrainResult:
    labelled = df.dropna(subset=["esi_target"])
    parts = split_by_time(labelled, sp)
    tr, va, te = parts["train"], parts["val"], parts["test"]
    if min(len(tr), len(va), len(te)) < 200:
        raise ValueError(f"not enough rows per split: {[len(tr), len(va), len(te)]}")
    model = xgb.XGBRegressor(**{**PARAMS, "random_state": seed})
    model.fit(feature_matrix(tr), tr["esi_target"], eval_set=[(feature_matrix(va), va["esi_target"])], verbose=False)
    lookup = esi.set_index(["cell_id", "date"])["esi"]
    hi = float(tr["esi_target"].quantile(0.70))
    metrics = {"validation": evaluate(model, va, tr, lookup, hi), "test": evaluate(model, te, tr, lookup, hi)}
    if with_spatial:
        metrics["spatial_cv_train_window"] = spatial_cv(tr)
    calib = Calibrator(np.sort(tr["esi_target"].to_numpy()))
    info = {"schema_version": SCHEMA_VERSION, "features": FEATURES_V1, "seed": seed, "high_stress_esi_threshold": hi,
            "rows": {"train": len(tr), "val": len(va), "test": len(te)},
            "windows": {"train_start": str(tr["issue_day"].min().date()), "train_end": str(sp.train_end.date()),
                        "validation_start": str(va["issue_day"].min().date()), "val_end": str(sp.val_end.date()),
                        "test_start": str(te["issue_day"].min().date()), "test_end": str(te["issue_day"].max().date())},
            "best_iteration": int(getattr(model, "best_iteration", model.n_estimators))}
    return TrainResult(model, calib, metrics, info)


# ---------------------------------------------------------------- explanations
GROUPS = {
    "soil_moisture": ["obs_sm_last", "obs_sm_pct_last", "obs_sm_change_7d"],
    "recent_rain": ["obs_rain_7d_mm", "obs_rain_30d_mm", "obs_rain_90d_mm", "obs_rain_30d_pct", "obs_dry_spell_days"],
    "forecast_rain": ["fc_precip_day_mm", "fc_precip_cum_mm", "fc_dry_days"],
    "heat": ["fc_tmax_c", "fc_tmin_c", "fc_tmean_c", "fc_tmax_pct", "obs_tmax_7d_mean_c"],
    "dryness": ["fc_vpd_max_kpa", "fc_vpd_pct", "obs_vpd_max_7d_mean_kpa"],
}
# Seasonality / location / lead are context, never shown as a "reason".


def _tree_range(model: xgb.XGBRegressor) -> tuple[int, int]:
    """Same trees as model.predict(): up to best_iteration when early stopping was used."""
    try:
        return (0, int(model.best_iteration) + 1)
    except (AttributeError, ValueError):
        best = model.get_booster().attr("best_iteration")
        return (0, int(best) + 1) if best is not None else (0, 0)


def group_contributions(model: xgb.XGBRegressor, X: pd.DataFrame) -> pd.DataFrame:
    """TreeSHAP contributions (ESI units) summed per interpretable group; additive with model.predict()."""
    contrib = model.get_booster().predict(xgb.DMatrix(X), pred_contribs=True, iteration_range=_tree_range(model))[:, :-1]
    cdf = pd.DataFrame(contrib, columns=list(X.columns), index=X.index)
    return pd.DataFrame({g: cdf[cols].sum(axis=1) for g, cols in GROUPS.items()})


def save_bundle(path: Path, res: TrainResult, extra: dict | None = None) -> None:
    path.mkdir(parents=True, exist_ok=True)
    res.model.save_model(path / "model.json")
    (path / "calibration.json").write_text(json.dumps({"quantiles": res.calibrator.to_json()}))
    (path / "metrics.json").write_text(json.dumps({"metrics": res.metrics, "info": res.info, **(extra or {})}, indent=1, default=float))


def load_bundle(path: Path) -> tuple[xgb.XGBRegressor, Calibrator, dict]:
    m = xgb.XGBRegressor()
    m.load_model(path / "model.json")
    cal = Calibrator.from_json(json.loads((path / "calibration.json").read_text())["quantiles"])
    return m, cal, json.loads((path / "metrics.json").read_text())
