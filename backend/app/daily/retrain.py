"""Safe auto-retraining: candidate -> identical-holdout comparison -> predefined gates -> promote or keep champion."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .climatology import Climatology
from .config import CLIMATOLOGY_BUNDLE_FILES, LEADS, SCHEMA_VERSION
from .dataset import load_training_data
from .features import build_features
from .modeling import Splits, evaluate, load_bundle, save_bundle, split_by_time, train_candidate
from .store import Paths, read_json, sha256_file, write_bytes_atomic, write_json_atomic
from .target import compute_esi

log = logging.getLogger("badia.daily.retrain")


@dataclass(frozen=True)
class Gates:
    min_test_rows: int = 3000
    min_rows_per_lead: int = 250
    min_mae_improvement: float = 0.01        # candidate MAE must be >=1% lower than champion on the SAME rows
    max_lead_regression: float = 0.05        # no single lead may be >5% worse than champion
    max_spearman_drop: float = 0.01
    min_skill_vs_persistence: float = 0.0    # must beat persistence overall
    min_skill_vs_climatology: float = 0.0    # must beat climatology overall
    first_champion_min_skill: float = 0.05   # bootstrap: no champion yet -> stricter absolute bar vs baselines
    first_champion_min_lead_skill: float = -0.02  # no horizon may materially underperform either baseline
    min_spatial_folds: int = 2
    min_spatial_spearman: float = 0.10


_REQUIRED_GATE_METRICS = (
    "mae",
    "rmse",
    "spearman",
    "mae_persistence",
    "mae_climatology",
    "skill_vs_persistence",
    "skill_vs_climatology",
)


def _required_metrics_finite(metrics: dict) -> bool:
    """Validate metrics that can change a promotion decision.

    ``auc_high_stress`` is deliberately excluded: AUC is undefined for a
    one-class seasonal holdout, while the deployed model is a regressor and its
    MAE/rank/baseline skills remain valid evidence.
    """
    try:
        return all(np.isfinite(float(metrics[name])) for name in _REQUIRED_GATE_METRICS)
    except (KeyError, TypeError, ValueError):
        return False


def snapshot_climatology(paths: Paths, version_dir: Path) -> dict:
    """Copy the exact climatology used for training into a candidate bundle.

    The global climatology is an acquisition workspace.  It must never be a
    mutable runtime dependency of an already-promoted champion.
    """
    sources = {
        "climatology.npz": paths.climatology,
        "climatology_mapping.csv": paths.climatology_mapping,
        "climatology_metadata.json": paths.climatology_metadata,
    }
    missing = [name for name, source in sources.items() if not source.is_file()]
    if missing:
        raise FileNotFoundError(f"climatology artifacts are missing: {missing}")
    version_dir.mkdir(parents=True, exist_ok=True)
    files: dict[str, dict] = {}
    for name in CLIMATOLOGY_BUNDLE_FILES:
        source = sources[name]
        destination = version_dir / name
        write_bytes_atomic(destination, source.read_bytes())
        files[name] = {"sha256": sha256_file(destination), "bytes": destination.stat().st_size}
    return {"format": 1, "files": files}


def check_gates(cand: dict, champ: dict | None, g: Gates = Gates()) -> tuple[bool, list[str]]:
    """cand/champ: {'overall': {...}, 'by_lead': {...}} evaluated on the SAME holdout rows."""
    fails: list[str] = []
    o = cand["overall"]
    if not _required_metrics_finite(o):
        return False, ["non-finite candidate metrics"]
    if o["n"] < g.min_test_rows:
        fails.append(f"holdout too small ({o['n']} < {g.min_test_rows})")
    need_p = g.min_skill_vs_persistence if champ else g.first_champion_min_skill
    if o["skill_vs_persistence"] <= need_p:
        fails.append(f"does not beat persistence by enough ({o['skill_vs_persistence']:.3f} <= {need_p})")
    if o["skill_vs_climatology"] <= (g.min_skill_vs_climatology if champ else g.first_champion_min_skill):
        fails.append(f"does not beat climatology by enough ({o['skill_vs_climatology']:.3f})")
    expected = {str(L) for L in LEADS}
    missing = expected - set(cand.get("by_lead", {}))
    if missing:
        fails.append(f"missing per-lead metrics: {sorted(missing, key=int)}")
    for L in sorted(expected & set(cand.get("by_lead", {})), key=int):
        m = cand["by_lead"][L]
        if not _required_metrics_finite(m):
            fails.append(f"lead {L} has non-finite metrics")
            continue
        if int(m.get("n", 0)) < g.min_rows_per_lead:
            fails.append(f"lead {L} holdout too small ({m.get('n', 0)} < {g.min_rows_per_lead})")
        if champ is None:
            if m.get("skill_vs_persistence", float("-inf")) <= g.first_champion_min_lead_skill:
                fails.append(f"lead {L} materially underperforms persistence")
            if m.get("skill_vs_climatology", float("-inf")) <= g.first_champion_min_lead_skill:
                fails.append(f"lead {L} materially underperforms climatology")

    spatial = cand.get("spatial_cv_train_window")
    if not spatial or int(spatial.get("folds") or 0) < g.min_spatial_folds:
        fails.append("spatial cross-validation is missing or has too few folds")
    elif not np.isfinite(spatial.get("mae_mean", np.nan)) or not np.isfinite(spatial.get("spearman_mean", np.nan)):
        fails.append("spatial cross-validation has non-finite metrics")
    elif float(spatial["spearman_mean"]) < g.min_spatial_spearman:
        fails.append(f"spatial CV Spearman {spatial['spearman_mean']:.3f} < {g.min_spatial_spearman:.3f}")
    if champ:
        c = champ["overall"]
        if o["mae"] > c["mae"] * (1 - g.min_mae_improvement):
            fails.append(f"MAE {o['mae']:.4f} not >={g.min_mae_improvement:.0%} better than champion {c['mae']:.4f}")
        if o["spearman"] < c["spearman"] - g.max_spearman_drop:
            fails.append(f"Spearman dropped {c['spearman']:.3f} -> {o['spearman']:.3f}")
        for L, m in cand.get("by_lead", {}).items():
            cm = champ["by_lead"].get(L)
            if cm and m["mae"] > cm["mae"] * (1 + g.max_lead_regression):
                fails.append(f"lead {L} regressed beyond {g.max_lead_regression:.0%}")
    return (not fails), fails


class Registry:
    def __init__(self, paths: Paths) -> None:
        self.p = paths.ensure()

    def champion(self) -> dict | None:
        return read_json(self.p.champion_file) if self.p.champion_file.exists() else None

    def promote(self, version: str, reason: str, gate_report: dict) -> None:
        cur = self.champion()
        ptr = {"version": version, "promoted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "reason": reason, "previous": cur["version"] if cur else None, "gate_report": gate_report}
        write_json_atomic(self.p.champion_file, ptr)

    def rollback(self) -> str:
        cur = self.champion()
        if not cur or not cur.get("previous"):
            raise RuntimeError("no previous model to roll back to")
        prev = cur["previous"]
        if not (self.p.versions / prev / "model.json").exists():
            raise RuntimeError(f"previous version {prev} is missing")
        write_json_atomic(self.p.champion_file, {"version": prev, "previous": None, "reason": f"rollback from {cur['version']}",
                                                 "promoted_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        return prev

    def versions(self) -> list[str]:
        return sorted(d.name for d in self.p.versions.iterdir() if (d / "model.json").exists())


def should_retrain(manifest: dict, champion: dict | None, now: datetime | None = None,
                   min_days: int = 30, min_new_days: int = 21) -> tuple[bool, str]:
    """Evidence-based cadence: enough elapsed time AND enough newly verified labelled days. Never per request."""
    if champion is None:
        return True, "no champion yet"
    now = now or datetime.now(timezone.utc)
    last = datetime.fromisoformat(champion["promoted_at"])
    trained_end = pd.Timestamp(champion.get("gate_report", {}).get("data_end", "1970-01-01"))
    new_days = (pd.Timestamp(manifest["data_end"]) - trained_end).days
    if (now - last).days < min_days:
        return False, f"only {(now - last).days} days since last promotion (< {min_days})"
    if new_days < min_new_days:
        return False, f"only {new_days} new verified days (< {min_new_days})"
    return True, f"{(now - last).days} days elapsed, {new_days} new verified days"


def _assert_metric_replay(existing: dict, replayed: dict, label: str) -> None:
    """Refuse an additive metric update if any previously reported value changed."""
    for section in ("overall", "by_lead"):
        old_section, new_section = existing[section], replayed[section]
        if section == "by_lead" and set(old_section) != set(new_section):
            raise ValueError(f"{label} lead set changed during replay")
        groups = old_section.items() if section == "by_lead" else [("overall", old_section)]
        for group, old_metrics in groups:
            new_metrics = new_section[group] if section == "by_lead" else new_section
            for key, old_value in old_metrics.items():
                if key in {"r2", "by_season"}:
                    continue
                if key not in new_metrics:
                    raise ValueError(f"{label}.{section}.{group}.{key} missing from replay")
                new_value = new_metrics[key]
                if isinstance(old_value, (int, float)) and isinstance(new_value, (int, float)):
                    if not np.isclose(float(old_value), float(new_value), rtol=1e-12, atol=1e-12,
                                      equal_nan=True):
                        raise ValueError(
                            f"{label}.{section}.{group}.{key} changed: {old_value!r} != {new_value!r}")
                elif old_value != new_value:
                    raise ValueError(
                        f"{label}.{section}.{group}.{key} changed: {old_value!r} != {new_value!r}")


def _add_replayed_fields(existing: dict, replayed: dict) -> None:
    """Add only R² and the seasonal breakdown to an existing evaluation."""
    existing["overall"]["r2"] = replayed["overall"]["r2"]
    for lead, metrics in existing["by_lead"].items():
        metrics["r2"] = replayed["by_lead"][lead]["r2"]
    existing["by_season"] = replayed["by_season"]


def replay_saved_version(paths: Paths, version: str) -> tuple[dict, dict]:
    """Evaluate a saved model on its original split without fitting any model."""
    version_dir = paths.versions / version
    model, _, metadata = load_bundle(version_dir)
    cells, obs, forecasts, static, manifest = load_training_data(paths)
    saved_manifest = metadata.get("dataset_manifest", {})
    if saved_manifest.get("sha256") != manifest.get("sha256"):
        raise ValueError("current dataset hashes do not match the saved model manifest")

    climatology = Climatology.load(version_dir / "climatology.npz")
    esi = compute_esi(obs, climatology)
    frame = build_features(cells, obs, forecasts, climatology, static=static, esi=esi)
    labelled = frame.dropna(subset=["esi_target"])
    info = metadata["info"]
    split = Splits(train_end=pd.Timestamp(info["windows"]["train_end"]),
                   val_end=pd.Timestamp(info["windows"]["val_end"]))
    parts = split_by_time(labelled, split)
    actual_rows = {name: int(len(parts[name])) for name in ("train", "val", "test")}
    expected_rows = {name: int(info["rows"][name]) for name in actual_rows}
    if actual_rows != expected_rows:
        raise ValueError(f"saved split row counts changed: {actual_rows} != {expected_rows}")

    lookup = esi.set_index(["cell_id", "date"])["esi"]
    threshold = float(info["high_stress_esi_threshold"])
    replayed = {
        "validation": evaluate(model, parts["val"], parts["train"], lookup, threshold),
        "test": evaluate(model, parts["test"], parts["train"], lookup, threshold),
        "promotion_holdout": evaluate(model, parts["test"], parts["train"], lookup, threshold),
    }
    return replayed, metadata


def augment_saved_version_metrics(paths: Paths, version: str) -> dict:
    """Add R²/season metrics to an existing champion without retraining or changing old results."""
    paths.ensure()
    champion = read_json(paths.champion_file)
    if champion.get("version") != version:
        raise ValueError(f"refusing to edit non-champion version {version!r}")
    version_dir = paths.versions / version
    replayed, metadata = replay_saved_version(paths, version)

    for name in ("validation", "test", "promotion_holdout"):
        _assert_metric_replay(metadata["metrics"][name], replayed[name], name)
    gate = metadata["gate_report"]
    _assert_metric_replay(
        {"overall": gate["candidate_holdout"], "by_lead": gate["candidate_by_lead"]},
        replayed["promotion_holdout"], "gate_report")

    for name in ("validation", "test", "promotion_holdout"):
        _add_replayed_fields(metadata["metrics"][name], replayed[name])
    gate["candidate_holdout"]["r2"] = replayed["promotion_holdout"]["overall"]["r2"]
    for lead, metrics in gate["candidate_by_lead"].items():
        metrics["r2"] = replayed["promotion_holdout"]["by_lead"][lead]["r2"]
    gate["candidate_by_season"] = replayed["promotion_holdout"]["by_season"]

    champion_gate = champion["gate_report"]
    _assert_metric_replay(
        {"overall": champion_gate["candidate_holdout"], "by_lead": champion_gate["candidate_by_lead"]},
        replayed["promotion_holdout"], "champion.gate_report")
    champion_gate["candidate_holdout"]["r2"] = replayed["promotion_holdout"]["overall"]["r2"]
    for lead, metrics in champion_gate["candidate_by_lead"].items():
        metrics["r2"] = replayed["promotion_holdout"]["by_lead"][lead]["r2"]
    champion_gate["candidate_by_season"] = replayed["promotion_holdout"]["by_season"]

    test = replayed["test"]
    summary = {
        "schema_version": SCHEMA_VERSION,
        "version": version,
        "evaluation": "saved-model replay on the original chronological holdout; no model fitting performed",
        "recomputed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "target": "Environmental Stress Index (ESI, 0-1); R2 may be negative and is not a probability",
        "test_window": metadata["info"]["windows"],
        "dataset": {key: metadata["dataset_manifest"].get(key) for key in
                    ("data_start", "data_end", "n_cells", "forecast_model", "issue_time_contract")},
        "model_sha256": sha256_file(version_dir / "model.json"),
        "calibration_sha256": sha256_file(version_dir / "calibration.json"),
        "gate_decision_preserved": {"passed": gate["passed"], "failures": gate["failures"]},
        "overall": test["overall"],
        "by_lead": test["by_lead"],
        "by_season": test["by_season"],
        "reproduce": f"augment_saved_version_metrics(Paths.default(), {version!r})",
    }
    write_json_atomic(version_dir / "metrics.json", metadata)
    write_json_atomic(paths.champion_file, champion)
    write_json_atomic(version_dir / "backtest_summary.json", summary)
    return summary


def run_retrain(paths: Paths, gates: Gates = Gates(), holdout_days: int = 75, val_days: int = 60, force: bool = False,
                now: datetime | None = None, tag: str | None = None) -> dict:
    """Train a CANDIDATE on data ending before a fixed holdout, compare with the champion on identical holdout rows."""
    reg = Registry(paths)
    cells, obs, fc, static, manifest = load_training_data(paths)
    champ_ptr = reg.champion()
    go, why = should_retrain(manifest, champ_ptr, now)
    if not (go or force):
        return {"action": "skipped", "reason": why}
    clim = Climatology.load(paths.climatology)
    esi = compute_esi(obs, clim)
    df = build_features(cells, obs, fc, clim, static=static, esi=esi)
    last_issue = df.dropna(subset=["esi_target"])["issue_day"].max()
    sp = Splits(train_end=last_issue - pd.Timedelta(days=holdout_days + val_days + 14),
                val_end=last_issue - pd.Timedelta(days=holdout_days + 7))
    cand = train_candidate(df, sp, esi, with_spatial=True)
    version = tag or datetime.now(timezone.utc).strftime("v%Y%m%dT%H%M%S")
    holdout = df.dropna(subset=["esi_target"])
    holdout = holdout[holdout["issue_day"] > sp.val_end + pd.Timedelta(days=7)]
    lookup = esi.set_index(["cell_id", "date"])["esi"]
    train_rows = df.dropna(subset=["esi_target"])
    train_rows = train_rows[(train_rows["issue_day"] <= sp.train_end) & (train_rows["target_date"] <= sp.train_end)]
    hi = float(train_rows["esi_target"].quantile(0.70))
    cand_m = evaluate(cand.model, holdout, train_rows, lookup, hi)
    cand_m["spatial_cv_train_window"] = cand.metrics.get("spatial_cv_train_window")
    champ_m = None
    if champ_ptr:
        cm, _, _ = load_bundle(paths.versions / champ_ptr["version"])
        champ_m = evaluate(cm, holdout, train_rows, lookup, hi)
    ok, fails = check_gates(cand_m, champ_m, gates)
    report = {"candidate": version, "champion": champ_ptr["version"] if champ_ptr else None, "passed": ok, "failures": fails,
              "candidate_holdout": cand_m["overall"], "champion_holdout": champ_m["overall"] if champ_m else None,
              "candidate_by_lead": cand_m["by_lead"],
              "candidate_by_season": cand_m["by_season"],
              "champion_by_season": champ_m["by_season"] if champ_m else None,
              "spatial_cv_train_window": cand_m.get("spatial_cv_train_window"),
              "holdout_rows": int(len(holdout)), "data_end": manifest["data_end"], "schema_version": SCHEMA_VERSION}
    cand.metrics["promotion_holdout"] = cand_m
    version_dir = paths.versions / version
    climatology_artifacts = snapshot_climatology(paths, version_dir)
    save_bundle(version_dir, cand, {"gate_report": report, "dataset_manifest": manifest,
                                    "climatology_artifacts": climatology_artifacts})
    if ok:
        reg.promote(version, "passed all gates", report)
        log.info("PROMOTED %s", version)
        return {"action": "promoted", **report}
    log.warning("candidate %s rejected: %s", version, fails)
    return {"action": "rejected_kept_champion", **report}
