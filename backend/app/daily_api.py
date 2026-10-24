"""Read-only API and health helpers for the BADIA daily forecast."""
from __future__ import annotations

from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Query, Request

from .daily.config import CLIMATOLOGY_BUNDLE_FILES
from .daily.pipeline import serve_snapshot
from .daily.store import Paths, read_json

NOTE = (
    "Environmental Stress Risk is a 0-100 relative severity index of forecast "
    "meteorological/hydrological stress. It is not a probability, not a vegetation "
    "measurement and not a field diagnosis."
)

DAILY_LEAD_MIN = 0
DAILY_LEAD_MAX = 7
_USABLE_SNAPSHOT_STATES = frozenset({"fresh", "stale", "fallback"})


def _snapshot_context(snapshot: dict) -> dict:
    """Return the provenance fields shared by every daily response.

    ``issued_at`` is intentionally allowed to be null: it is the NWP model issue
    time, not the time BADIA generated or retrieved the snapshot. The legacy
    ``issue_day`` alias remains available while clients move to
    ``forecast_reference_date``.
    """
    freshness = snapshot.get("freshness")
    if not isinstance(freshness, dict):
        freshness = None
    reference_date = snapshot.get("forecast_reference_date") or snapshot.get("issue_day")
    generated_at = snapshot.get("generated_at")
    if generated_at is None and "generated_at" not in snapshot:
        # Compatibility for already-saved pre-provenance snapshots only.
        generated_at = snapshot.get("issued_at")
    last_successful = snapshot.get("last_successful_update")
    if last_successful is None and freshness:
        last_successful = freshness.get("last_successful_update")
    state = snapshot.get("state", "unavailable")
    return {
        "generated_at": generated_at,
        "issued_at": snapshot.get("issued_at"),
        "forecast_reference_date": reference_date,
        "issue_day": snapshot.get("issue_day") or reference_date,
        "covers": snapshot.get("covers", []),
        "freshness": freshness,
        "source_state": snapshot.get("source_state"),
        "quality": snapshot.get("quality"),
        "provider_status": snapshot.get("provider_status"),
        "last_update_error": snapshot.get("last_update_error"),
        "last_successful_update": last_successful,
        "using_fallback": bool(
            state == "fallback"
            or snapshot.get("fallback")
            or snapshot.get("served_from") == "last_good.json"
        ),
        "snapshot_age_hours": snapshot.get("snapshot_age_hours"),
        "served_from": snapshot.get("served_from"),
        "model": snapshot.get("model"),
    }


def _champion_status(paths: Paths) -> tuple[dict | None, dict, str | None]:
    required = {
        "model": False,
        "calibration": False,
        "metrics": False,
        **{name: False for name in CLIMATOLOGY_BUNDLE_FILES},
    }
    if not paths.champion_file.exists():
        return None, required, None
    try:
        champion = read_json(paths.champion_file)
        version = champion.get("version") if isinstance(champion, dict) else None
        if not version:
            return champion, required, "champion pointer has no version"
        bundle = paths.versions / str(version)
        required = {
            "model": (bundle / "model.json").is_file(),
            "calibration": (bundle / "calibration.json").is_file(),
            "metrics": (bundle / "metrics.json").is_file(),
            **{name: (bundle / name).is_file() for name in CLIMATOLOGY_BUNDLE_FILES},
        }
        return champion, required, None
    except (OSError, ValueError, TypeError) as exc:
        return None, required, f"{type(exc).__name__}: {exc}"


def daily_health(paths: Paths, snapshot: dict | None = None) -> dict:
    """Summarise model and snapshot readiness without loading the XGBoost model."""
    champion, artifacts, model_error = _champion_status(paths)
    model_ready = champion is not None and all(artifacts.values())
    snapshot_error = None
    if snapshot is None:
        try:
            snapshot = serve_snapshot(paths)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            snapshot = {"state": "unavailable", "cells": {}}
            snapshot_error = f"{type(exc).__name__}: {exc}"
    if not isinstance(snapshot, dict):
        snapshot = {"state": "unavailable", "cells": {}}
        snapshot_error = snapshot_error or "snapshot payload is not an object"
    cells = snapshot.get("cells")
    state = snapshot.get("state", "unavailable")
    cell_count = len(cells) if isinstance(cells, dict) else 0
    snapshot_ready = cell_count > 0 and state in _USABLE_SNAPSHOT_STATES
    ready = model_ready and snapshot_ready
    freshness = snapshot.get("freshness") if isinstance(snapshot.get("freshness"), dict) else {}
    source_stale = bool(freshness.get("source_stale"))
    if ready and state == "fresh" and not source_stale:
        status = "ok"
    elif model_ready or cell_count:
        status = "degraded"
    else:
        status = "unavailable"
    champion_pointer = None
    if isinstance(champion, dict):
        champion_pointer = {
            key: champion.get(key) for key in ("version", "promoted_at", "previous")
        }
    context = _snapshot_context(snapshot)
    return {
        "status": status,
        "ready": ready,
        "model_ready": model_ready,
        "snapshot_ready": snapshot_ready,
        "snapshot_state": state,
        "cell_count": cell_count,
        "champion_pointer": champion_pointer,
        "model_artifacts": artifacts,
        "model_error": model_error,
        "snapshot_error": snapshot_error,
        **{
            key: context[key]
            for key in (
                "generated_at",
                "issued_at",
                "forecast_reference_date",
                "provider_status",
                "last_update_error",
                "last_successful_update",
                "using_fallback",
                "snapshot_age_hours",
                "served_from",
            )
        },
    }


def make_router(paths_getter) -> APIRouter:
    router = APIRouter(prefix="/api/daily", tags=["daily"])

    def snap(request: Request) -> dict:
        return serve_snapshot(paths_getter(request))

    @router.get("/status", summary="Daily forecast state, freshness and model info")
    def status(request: Request) -> dict:
        snapshot = snap(request)
        paths = paths_getter(request)
        health = daily_health(paths, snapshot)
        return {
            "state": snapshot.get("state", "unavailable"),
            "is_synthetic": snapshot.get("is_synthetic", False),
            **_snapshot_context(snapshot),
            "champion_pointer": health["champion_pointer"],
            "readiness": health,
            "score_definition": snapshot.get("score_definition"),
            "note": NOTE,
            "detail": snapshot.get("detail"),
        }

    @router.get("/forecast", summary="Per-cell score for one lead (or all)")
    def forecast(
        request: Request,
        lead: int | None = Query(None, ge=DAILY_LEAD_MIN, le=DAILY_LEAD_MAX),
    ) -> dict:
        snapshot = snap(request)
        source_cells = snapshot.get("cells") or {}
        context = _snapshot_context(snapshot)
        if not source_cells:
            return {
                "state": snapshot.get("state", "unavailable"),
                "is_synthetic": snapshot.get("is_synthetic", False),
                **context,
                "cells": {},
                "note": NOTE,
                "detail": snapshot.get("detail"),
            }
        cells = {}
        for cell_id, cell_data in source_cells.items():
            days = [
                day
                for day in cell_data.get("days", [])
                if lead is None or day.get("lead_days") == lead
            ]
            compact_days = []
            for day in days:
                confidence = day.get("confidence")
                confidence_level = (
                    confidence.get("level") if isinstance(confidence, dict) else confidence
                )
                compact_days.append(
                    {
                        key: day.get(key)
                        for key in (
                            "lead_days",
                            "date",
                            "score",
                            "level",
                            "change_vs_today",
                        )
                    }
                    | {"confidence": confidence_level}
                )
            cells[cell_id] = {
                "latitude": cell_data.get("latitude"),
                "longitude": cell_data.get("longitude"),
                "days": compact_days,
            }
        return {
            "state": snapshot.get("state", "unavailable"),
            "is_synthetic": snapshot.get("is_synthetic", False),
            **context,
            "note": NOTE,
            "cells": cells,
        }

    @router.get("/cells/{cell_id}", summary="Full daily detail for one cell")
    def cell(cell_id: str, request: Request) -> dict:
        snapshot = snap(request)
        decoded = unquote(cell_id)
        cells = snapshot.get("cells") or {}
        if not cells:
            raise HTTPException(
                503,
                snapshot.get("detail") or "Daily forecast is not currently available",
            )
        cell_data = cells.get(decoded)
        if cell_data is None:
            raise HTTPException(404, f"Cell '{decoded}' has no daily forecast (no data)")
        return {
            "cell_id": decoded,
            "state": snapshot.get("state", "unavailable"),
            "is_synthetic": snapshot.get("is_synthetic", False),
            **_snapshot_context(snapshot),
            "note": NOTE,
            **cell_data,
        }

    @router.get("/summary", summary="National counts per lead")
    def summary(request: Request) -> dict:
        snapshot = snap(request)
        context = _snapshot_context(snapshot)
        cells = snapshot.get("cells") or {}
        if not cells:
            return {
                "state": snapshot.get("state", "unavailable"),
                "is_synthetic": snapshot.get("is_synthetic", False),
                **context,
                "leads": {},
            }
        output: dict[str, dict] = {}
        for cell_data in cells.values():
            for day in cell_data.get("days", []):
                lead_key = str(day["lead_days"])
                item = output.setdefault(
                    lead_key,
                    {
                        "date": day.get("date"),
                        "Low": 0,
                        "Moderate": 0,
                        "High": 0,
                        "N/A": 0,
                        "scores": [],
                    },
                )
                level = day.get("level", "N/A")
                item[level if level in item else "N/A"] += 1
                score = day.get("score")
                if isinstance(score, (int, float)):
                    item["scores"].append(float(score))
        for item in output.values():
            scores = sorted(item.pop("scores"))
            item["mean_score"] = round(sum(scores) / len(scores), 1) if scores else None
            item["cells"] = sum(
                item[level] for level in ("Low", "Moderate", "High", "N/A")
            )
        return {
            "state": snapshot.get("state", "unavailable"),
            "is_synthetic": snapshot.get("is_synthetic", False),
            **context,
            "leads": output,
        }

    @router.get("/metrics", summary="Champion backtest metrics (held-out test window)")
    def metrics(request: Request) -> dict:
        paths = paths_getter(request)
        if not paths.champion_file.exists():
            return {"state": "not_initialized"}
        champion = read_json(paths.champion_file)
        meta = read_json(paths.versions / champion["version"] / "metrics.json")
        return {
            "version": champion["version"],
            "metrics": meta["metrics"],
            "info": meta["info"],
            "gate_report": meta.get("gate_report"),
            "note": NOTE,
        }

    return router
