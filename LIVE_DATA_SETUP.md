# BADIA AI — Near-real-time data pipeline

The packaged historical demo remains untouched. The experimental live updater writes to `data/near_real_time/`.

## Data sources

- `MODIS/061/MOD13Q1`: 16-day NDVI, `SummaryQA <= 1`, NDVI scale factor `0.0001`.
- `UCSB-CHG/CHIRPS/DAILY`: rainfall sums for 16, 30 and 90 days.
- `ECMWF/ERA5_LAND/DAILY_AGGR`: 30-day mean `temperature_2m` (K → °C) and `volumetric_soil_water_layer_1`.

The updater chooses the newest MODIS composite whose full 16-day period is covered by both daily sources. This avoids mixing partially available windows.

## One-time account step

Google Earth Engine requires an authenticated account/project. Once Earth Engine access is enabled, set:

```text
BADIA_EE_PROJECT=<your-project-id>
```

Authentication must be completed once in the user's Google account. Credentials are never stored in the frontend or committed to the repository.

## Run

From the repository root after installing backend requirements:

```text
python scripts/update_near_real_time.py
```

Generated files are kept separate from the competition-safe offline snapshot until source/preprocessing validation is completed.

## Important validation rule

Do **not** replace the packaged historical demo with generated live data until the live pipeline is back-tested against the known 2025 period-21 snapshot. The main uncertainty to verify is whether the original seasonal-anomaly and spatial aggregation preprocessing exactly matches the reconstructed Earth Engine implementation.
