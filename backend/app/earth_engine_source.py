"""Google Earth Engine adapter for BADIA AI environmental inputs.

The adapter uses the same dataset families chosen for the project:
- MODIS/061/MOD13Q1 for 16-day NDVI
- UCSB-CHG/CHIRPS/DAILY for rainfall
- ECMWF/ERA5_LAND/DAILY_AGGR for temperature and top-layer soil moisture

It does not authenticate interactively. Authentication is a one-time user/account
step and must happen before this module is used in an automated update job.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .live_features import (
    COMPOSITE_DAYS,
    NDVI_BASELINE_YEARS,
    TRAIN_YEARS,
    period_end,
    period_index_for_date,
    period_start,
    shift_period,
)

try:  # Kept optional so the saved/offline demo remains runnable without EE.
    import ee  # type: ignore
except ImportError:  # pragma: no cover - exercised only when dependency is absent.
    ee = None


MODIS_COLLECTION = "MODIS/061/MOD13Q1"
CHIRPS_COLLECTION = "UCSB-CHG/CHIRPS/DAILY"
ERA5_COLLECTION = "ECMWF/ERA5_LAND/DAILY_AGGR"


class EarthEngineUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class AnchorPeriod:
    year: int
    period_index: int
    composite_start: date
    snapshot_date: date
    latest_chirps_date: date
    latest_era5_date: date


class EarthEngineSource:
    def __init__(self, project: str) -> None:
        if ee is None:
            raise EarthEngineUnavailable(
                "earthengine-api is not installed. Install backend requirements first."
            )
        if not project.strip():
            raise EarthEngineUnavailable("A Google Earth Engine project ID is required")
        try:
            ee.Initialize(project=project.strip())
        except Exception as exc:  # Earth Engine raises several auth-specific exceptions.
            raise EarthEngineUnavailable(
                "Google Earth Engine is not authenticated for this account/project. "
                "Complete the one-time Earth Engine sign-in, then rerun the updater."
            ) from exc
        self.project = project.strip()

    @staticmethod
    def _millis_to_date(value: int | float) -> date:
        return datetime.fromtimestamp(float(value) / 1000.0, tz=timezone.utc).date()

    @staticmethod
    def _latest_collection_date(collection_id: str) -> date:
        collection = ee.ImageCollection(collection_id)
        millis = collection.aggregate_max("system:time_start").getInfo()
        if millis is None:
            raise EarthEngineUnavailable(f"No dated images found in {collection_id}")
        return EarthEngineSource._millis_to_date(millis)

    def latest_common_anchor(self) -> AnchorPeriod:
        """Choose the newest MODIS period fully covered by CHIRPS and ERA5."""
        latest_chirps = self._latest_collection_date(CHIRPS_COLLECTION)
        latest_era5 = self._latest_collection_date(ERA5_COLLECTION)
        latest_common_daily = min(latest_chirps, latest_era5)
        latest_allowed_start = latest_common_daily - timedelta(days=COMPOSITE_DAYS - 1)

        modis = (
            ee.ImageCollection(MODIS_COLLECTION)
            # Earth Engine's filterDate end is exclusive. Include a composite whose
            # start is exactly the newest fully covered start date.
            .filterDate("2015-01-01", (latest_allowed_start + timedelta(days=1)).isoformat())
            .sort("system:time_start", False)
        )
        first = ee.Image(modis.first())
        millis = first.get("system:time_start").getInfo()
        if millis is None:
            raise EarthEngineUnavailable("No MODIS composite is available for a common source period")
        start = self._millis_to_date(millis)
        pidx = period_index_for_date(start)
        end = start + timedelta(days=COMPOSITE_DAYS - 1)
        return AnchorPeriod(
            year=start.year,
            period_index=pidx,
            composite_start=start,
            snapshot_date=end,
            latest_chirps_date=latest_chirps,
            latest_era5_date=latest_era5,
        )

    @staticmethod
    def _mask_modis(image: Any) -> Any:
        qa = image.select("SummaryQA")
        # SummaryQA 0=good, 1=marginal; 2=snow/ice, 3=cloudy.
        return image.select("NDVI").updateMask(qa.lte(1)).multiply(0.0001).rename("ndvi")

    def _modis_period_image(self, year: int, period_index: int) -> Any:
        start = period_start(year, period_index)
        end_exclusive = start + timedelta(days=COMPOSITE_DAYS)
        image = ee.ImageCollection(MODIS_COLLECTION).filterDate(
            start.isoformat(), end_exclusive.isoformat()
        ).first()
        return self._mask_modis(ee.Image(image))

    def _seasonal_baseline(self, period_index: int) -> Any:
        images = [self._modis_period_image(year, period_index) for year in NDVI_BASELINE_YEARS]
        # The validated 2026 feature artifacts use the 2003-2022 same-period
        # arithmetic mean. Keeping that exact feature meaning is required by the
        # frozen +16/+32 models.
        return ee.ImageCollection.fromImages(images).mean().rename("ndvi_baseline")

    @staticmethod
    def _feature_collection_from_geojson(path: Path) -> Any:
        import json

        payload = json.loads(path.read_text(encoding="utf-8"))
        features = []
        for raw in payload.get("features", []):
            props = raw.get("properties") or {}
            cell_id = str(raw.get("id") or props.get("cell_id"))
            geometry = raw.get("geometry")
            if not cell_id or not geometry:
                continue
            features.append(ee.Feature(ee.Geometry(geometry), {"cell_id": cell_id}))
        if not features:
            raise EarthEngineUnavailable(f"No cell geometries found in {path}")
        return ee.FeatureCollection(features)

    @staticmethod
    def _reduce(image: Any, cells: Any, scale: int) -> dict[str, dict[str, Any]]:
        reduced = image.reduceRegions(
            collection=cells,
            reducer=ee.Reducer.mean(),
            scale=scale,
            tileScale=4,
        ).getInfo()
        result: dict[str, dict[str, Any]] = {}
        for feature in reduced.get("features", []):
            props = feature.get("properties") or {}
            cell_id = str(props.get("cell_id"))
            if cell_id and cell_id != "None":
                result[cell_id] = props
        return result

    def current_features(self, geojson_path: Path, anchor: AnchorPeriod) -> dict[str, dict[str, Any]]:
        cells = self._feature_collection_from_geojson(geojson_path)
        current_ndvi = self._modis_period_image(anchor.year, anchor.period_index)
        baseline = self._seasonal_baseline(anchor.period_index)
        anomaly = current_ndvi.subtract(baseline).rename("ndvi_anomaly_current")
        ndvi_image = current_ndvi.addBands(anomaly)
        ndvi_rows = self._reduce(ndvi_image, cells, 250)

        end_exclusive = anchor.snapshot_date + timedelta(days=1)
        rain_bands = []
        for days, name in ((16, "rain_16d_mm"), (30, "rain_30d_mm"), (90, "rain_90d_mm")):
            start = end_exclusive - timedelta(days=days)
            band = (
                ee.ImageCollection(CHIRPS_COLLECTION)
                .filterDate(start.isoformat(), end_exclusive.isoformat())
                .select("precipitation")
                .sum()
                .rename(name)
            )
            rain_bands.append(band)
        rain_image = rain_bands[0].addBands(rain_bands[1:])
        rain_rows = self._reduce(rain_image, cells, 5566)

        climate_start = end_exclusive - timedelta(days=30)
        era = ee.ImageCollection(ERA5_COLLECTION).filterDate(
            climate_start.isoformat(), end_exclusive.isoformat()
        )
        temp = era.select("temperature_2m").mean().subtract(273.15).rename("temperature_30d_c")
        soil = era.select("volumetric_soil_water_layer_1").mean().rename("soil_moisture_30d")
        climate_rows = self._reduce(temp.addBands(soil), cells, 11132)

        merged: dict[str, dict[str, Any]] = {}
        ids = set(ndvi_rows) | set(rain_rows) | set(climate_rows)
        for cell_id in ids:
            merged[cell_id] = {
                **ndvi_rows.get(cell_id, {}),
                **rain_rows.get(cell_id, {}),
                **climate_rows.get(cell_id, {}),
            }
        return merged

    def target_reference(
        self,
        geojson_path: Path,
        source_period_index: int,
        horizon_days: int,
    ) -> list[float]:
        """Rebuild the 2015-2022 target-anomaly reference for one source period."""
        if horizon_days not in (16, 32):
            raise ValueError("horizon_days must be 16 or 32")
        cells = self._feature_collection_from_geojson(geojson_path)
        step_count = horizon_days // COMPOSITE_DAYS

        # Determine target seasonal period and its year shift from an arbitrary source year.
        base_year = TRAIN_YEARS[0]
        target_year0, target_period = shift_period(base_year, source_period_index, step_count)
        year_shift = target_year0 - base_year
        baseline = self._seasonal_baseline(target_period)

        bands = []
        band_names = []
        for source_year in TRAIN_YEARS:
            target_year = source_year + year_shift
            anomaly = self._modis_period_image(target_year, target_period).subtract(baseline)
            name = f"target_{source_year}"
            bands.append(anomaly.rename(name))
            band_names.append(name)
        stack = bands[0].addBands(bands[1:])
        rows = self._reduce(stack, cells, 250)

        reference: list[float] = []
        for props in rows.values():
            for name in band_names:
                value = props.get(name)
                if isinstance(value, (int, float)):
                    reference.append(float(value))
        return reference
