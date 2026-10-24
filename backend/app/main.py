"""FastAPI application for the BADIA AI offline MVP."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal
from urllib.parse import unquote

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .daily.store import Paths as DailyPaths
from .daily_api import daily_health, make_router as make_daily_router
from .open_ai_advisor import router as open_ai_router
from .priority import select_priority
from .data_store import DataFileMissingError, DataStore, DataStoreError


API_VERSION = "0.2.0"
DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DEFAULT_FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def _configured_origins() -> list[str]:
    defaults = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ]
    extra = [
        origin.strip()
        for origin in os.getenv("BADIA_CORS_ORIGINS", "").split(",")
        if origin.strip()
    ]
    return list(dict.fromkeys(defaults + extra))


def create_app(data_dir: Path | str | None = None, daily_paths: DailyPaths | None = None) -> FastAPI:
    resolved_data_dir = Path(
        data_dir or os.getenv("BADIA_DATA_DIR", str(DEFAULT_DATA_DIR))
    ).resolve()
    store = DataStore(resolved_data_dir)

    api = FastAPI(
        title="BADIA AI MVP API",
        version=API_VERSION,
        description=(
            "Read-only API for BADIA's Today-through-+7 environmental-stress forecast "
            "and its separate saved +16/+32-day vegetation outlook for Jordan. Scores "
            "are relative risk indices, not probabilities or field diagnoses."
        ),
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )
    api.state.store = store
    api.state.daily_paths = daily_paths or DailyPaths.default()
    api.include_router(make_daily_router(lambda request: request.app.state.daily_paths))
    api.include_router(open_ai_router)

    api.add_middleware(
        CORSMiddleware,
        allow_origins=_configured_origins(),
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_credentials=False,
        allow_methods=["GET", "OPTIONS"],
        allow_headers=["*"],
    )

    @api.exception_handler(DataStoreError)
    async def data_error_handler(_: Request, exc: DataStoreError) -> JSONResponse:
        status_code = 503 if isinstance(exc, DataFileMissingError) else 500
        return JSONResponse(
            status_code=status_code,
            content={
                "detail": str(exc),
                "error": "local_data_unavailable",
                "is_live": False,
            },
        )

    @api.get("/api/health", tags=["system"], summary="API and local data status")
    def health(request: Request) -> dict:
        availability = request.app.state.store.availability()
        medium_ready = all(availability["horizons"].values())
        daily = daily_health(request.app.state.daily_paths)
        overall_ready = medium_ready and daily["status"] == "ok"
        available_horizons = [
            int(horizon)
            for horizon, available in availability["horizons"].items()
            if available
        ]
        return {
            "status": "ok" if overall_ready else "degraded",
            "ready": overall_ready,
            "service": "BADIA AI MVP API",
            "version": API_VERSION,
            "service_mode": "daily_forecast_with_saved_medium_term_outlook",
            "data_mode": "saved_local_snapshot",
            "is_live": False,
            # Backward-compatible medium-term fields.
            "data_ready": medium_ready,
            "available_horizons": available_horizons,
            "files": availability["files"],
            "medium_term": {
                "status": "ok" if medium_ready else "degraded",
                "data_ready": medium_ready,
                "available_horizons": available_horizons,
                "files": availability["files"],
                "product": "+16/+32-day vegetation outlook",
                "is_live": False,
            },
            "daily": daily,
        }

    @api.get("/api/cells", tags=["map"], summary="Map cells for one horizon")
    def cells(
        request: Request,
        horizon: str = Query("16", pattern="^(16|32)$", description="Prediction horizon in days"),
        format: Literal["json", "geojson"] = Query(
            "json", description="Return a CellCollection or GeoJSON FeatureCollection"
        ),
    ) -> dict:
        horizon_days = int(horizon)
        if format == "geojson":
            return request.app.state.store.geojson_payload(horizon_days)
        return request.app.state.store.cells_payload(horizon_days)

    @api.get("/api/cells/{cell_id}", tags=["map"], summary="One cell's details")
    def cell_detail(
        cell_id: str,
        request: Request,
        horizon: str = Query("16", pattern="^(16|32)$", description="Prediction horizon in days"),
    ) -> dict:
        horizon_days = int(horizon)
        decoded_cell_id = unquote(cell_id)
        cell = request.app.state.store.find_cell(decoded_cell_id, horizon_days)
        if cell is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Cell '{decoded_cell_id}' was not found in the "
                    f"+{horizon_days}-day snapshot"
                ),
            )
        return {
            **cell,
            "is_live": False,
            "disclaimer": (
                "Satellite-derived vegetation anomaly risk indicator; not a "
                "field-verified desertification diagnosis."
            ),
        }

    @api.get("/api/priorities", tags=["map"], summary="Top national-priority cells")
    def priorities(
        request: Request,
        horizon: str = Query("16", pattern="^(16|32)$"),
        band: Literal["Top 1%", "Top 5%", "Top 10%"] | None = Query(None),
        limit: int = Query(10, ge=1, le=2000),
        include_cutoff_ties: bool = Query(
            False,
            description=(
                "Also return every cell sharing the cutoff rank (competition "
                "ranking), so a tie group is never split. count may exceed limit."
            ),
        ),
    ) -> dict:
        cells = request.app.state.store.get_cells(int(horizon))
        selected, selection = select_priority(cells, band, limit, include_cutoff_ties)
        return {
            "type": "PriorityList",
            "horizon_days": int(horizon),
            "count": len(selected),
            "selection": selection,
            "ranked_total": next(
                (c["national_priority_total"] for c in cells if c.get("national_priority_total")),
                0,
            ),
            "is_live": False,
            "note": (
                "National priority is a within-snapshot ordering of the historical "
                "risk score. It is not a probability or a field diagnosis."
            ),
            "cells": selected,
        }

    def _summary(
        request: Request,
        horizon: str | None = Query(
            None, pattern="^(16|32)$", description="Optional prediction horizon in days"
        ),
    ) -> dict:
        payload = request.app.state.store.national_summary()
        if horizon is None or not isinstance(payload.get("horizons"), dict):
            return payload
        horizon_days = int(horizon)
        selected = payload["horizons"].get(str(horizon_days))
        if selected is None:
            raise HTTPException(
                status_code=404,
                detail=f"National summary for +{horizon_days} days is unavailable",
            )
        return {
            **selected,
            "scope": payload.get("scope", "Jordan"),
            "snapshot_date": selected.get("snapshot_date") or payload.get("snapshot_date"),
            "snapshot_label": selected.get("snapshot_label") or payload.get("snapshot_label"),
            "is_live": False,
            "disclaimer": payload.get(
                "disclaimer",
                "Satellite-derived vegetation anomaly risk indicator; not a field diagnosis.",
            ),
        }

    api.add_api_route(
        "/api/areas",
        _summary,
        methods=["GET"],
        tags=["summary"],
        summary="National/area summary",
    )
    api.add_api_route(
        "/api/national-summary",
        _summary,
        methods=["GET"],
        tags=["summary"],
        summary="Alias for the national summary",
    )

    @api.get("/api/metrics", tags=["science"], summary="Historical evaluation metrics")
    def metrics(request: Request) -> dict:
        return request.app.state.store.metrics()

    @api.get("/api/metadata", tags=["science"], summary="Dataset and method metadata")
    def metadata(request: Request) -> dict:
        return request.app.state.store.metadata()

    # The packaged demo uses one origin for both the UI and API. This avoids
    # cross-port restrictions in embedded browsers while keeping the API routes
    # available exactly as documented.
    frontend_dir = Path(
        os.getenv("BADIA_FRONTEND_DIR", str(DEFAULT_FRONTEND_DIR))
    ).resolve()
    if (frontend_dir / "index.html").is_file():
        api.mount(
            "/",
            StaticFiles(directory=str(frontend_dir), html=True),
            name="frontend",
        )

    return api


app = create_app()
