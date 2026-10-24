"""Daily-engine command line with explicit acquisition and local-training phases."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, timedelta

import pandas as pd

from .config import OBS_LAG_DAYS
from .dataset import (
    DEFAULT_FORECAST_CHUNK_DAYS,
    DEFAULT_OBSERVATION_CHUNK_DAYS,
    DEFAULT_TRAIN_CELLS,
    build_climatology,
    load_cells,
    refresh_training_data,
    select_training_cells,
)
from .http import Client
from .lock import OperationLocked, operation_lock
from .pipeline import run_update
from .retrain import Registry, run_retrain, should_retrain
from .store import ROOT, Paths


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="badia-daily")
    parser.add_argument("cmd", choices=["acquire", "train-local", "bootstrap", "update", "retrain", "rollback", "status"])
    parser.add_argument("--train-cells", type=int, default=DEFAULT_TRAIN_CELLS,
                        help="deterministic climatology/training anchors (default: 24)")
    parser.add_argument("--end", type=date.fromisoformat,
                        help="last verified training day (YYYY-MM-DD; defaults to archive-safe lag)")
    parser.add_argument("--observation-chunk-days", type=int, default=DEFAULT_OBSERVATION_CHUNK_DAYS)
    parser.add_argument("--forecast-chunk-days", type=int, default=DEFAULT_FORECAST_CHUNK_DAYS)
    parser.add_argument("--climatology-chunk-days", type=int, default=DEFAULT_OBSERVATION_CHUNK_DAYS)
    parser.add_argument("--force", action="store_true")
    return parser


def _client(paths: Paths) -> Client:
    return Client(paths.cache)


def _acquire(paths: Paths, args, *, client: Client | None = None) -> dict:
    all_cells = load_cells(ROOT)
    anchors = select_training_cells(all_cells, args.train_cells)
    client = client or _client(paths)
    build_climatology(
        client,
        anchors,
        paths.climatology,
        all_cells=all_cells,
        parts_dir=paths.climatology_parts,
        date_chunk_days=args.climatology_chunk_days,
    )
    manifest = refresh_training_data(
        client,
        anchors,
        paths,
        end=args.end,
        observation_chunk_days=args.observation_chunk_days,
        forecast_chunk_days=args.forecast_chunk_days,
    )
    return {"action": "acquired", "data_end": manifest["data_end"], "training_cells": manifest["n_cells"],
            "obs_rows": manifest["obs_rows"], "forecast_rows": manifest["forecast_rows"]}


def _train_local(paths: Paths, *, force: bool) -> dict:
    # Deliberately contains no provider client or cell-source lookup: this phase must be
    # repeatable without internet once the manifest-verified local artifacts exist.
    return run_retrain(paths, force=force)


def _print(payload: dict) -> None:
    print(json.dumps(payload, indent=1, default=str))


def _training_exit(result: dict) -> int:
    return 0 if result.get("action") in {"promoted", "skipped"} else 2


def _run_locked(paths: Paths, args) -> int:
    if args.cmd == "acquire":
        result = _acquire(paths, args)
        _print(result)
        return 0
    if args.cmd == "train-local":
        result = _train_local(paths, force=args.force)
        _print({key: result.get(key) for key in ("action", "reason", "passed", "failures") if key in result})
        return _training_exit(result)
    if args.cmd == "bootstrap":
        acquired = _acquire(paths, args)
        trained = _train_local(paths, force=True)
        _print({"acquisition": acquired,
                "training": {key: trained.get(key) for key in ("action", "reason", "passed", "failures") if key in trained}})
        return _training_exit(trained)
    if args.cmd == "update":
        cells = load_cells(ROOT)
        result = run_update(paths, cells, client=_client(paths))
        _print(result)
        return 0 if result.get("state") in {"fresh", "stale"} else 2
    if args.cmd == "retrain":
        end = args.end or (date.today() - timedelta(days=OBS_LAG_DAYS + 2))
        registry = Registry(paths)
        due, reason = should_retrain({"data_end": str(end)}, registry.champion())
        if not (due or args.force):
            _print({"action": "skipped", "reason": reason, "acquisition_performed": False})
            return 0
        cells_file = paths.dataset / "cells.csv"
        if not cells_file.exists():
            raise FileNotFoundError("local training cells are missing; run `badia-daily acquire` first")
        training_cells = pd.read_csv(cells_file, dtype={"cell_id": str})
        refresh_training_data(
            _client(paths),
            training_cells,
            paths,
            end=end,
            observation_chunk_days=args.observation_chunk_days,
            forecast_chunk_days=args.forecast_chunk_days,
        )
        # Cadence was checked before network acquisition; force avoids repeating a subtly
        # different check after the manifest was advanced.
        result = _train_local(paths, force=True)
        result.setdefault("cadence_reason", reason)
        _print({key: result.get(key) for key in ("action", "cadence_reason", "passed", "failures") if key in result})
        return _training_exit(result)
    if args.cmd == "rollback":
        version = Registry(paths).rollback()
        _print({"action": "rolled_back", "version": version})
        return 0
    raise AssertionError(f"unexpected mutating command {args.cmd}")


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    paths = Paths.default().ensure()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(paths.data / "daily.log")],
    )
    if args.cmd == "status":
        registry = Registry(paths)
        _print({"champion": registry.champion(), "versions": registry.versions()})
        return 0
    try:
        with operation_lock(paths.operation_lock, operation=args.cmd):
            return _run_locked(paths, args)
    except OperationLocked as exc:
        _print({"state": "locked", "error": str(exc)})
        return 3


if __name__ == "__main__":
    sys.exit(main())
