# BADIA AI — Jordan Environmental Stress and Vegetation Outlook

> **Snapshot freshness:** This repository includes a saved daily forecast snapshot generated on **7 October 2026** (covering 7–14 October 2026). It is an **offline demonstration**, not a current live forecast. The +16/+32 vegetation layers are historical outlook demonstrations (2025 period 21). Refresh and verify source provenance before presenting data as current.

BADIA AI is a local, presentation-ready system for exploring daily environmental stress and medium-term vegetation-anomaly
risk across Jordan. It combines a real trained daily XGBoost model, the preserved +16/+32 vegetation models, transparent
relative risk indices, a FastAPI service, and a responsive React/Vite/Leaflet PWA.

> Each 0–100 score is a **relative historical risk index**, not a field-event probability. The system is not a
> desertification diagnosis, field truth or causal explanation. The daily layer is a forecast with explicit source
> freshness; delayed observations and satellite composites are never called live.

## What is included

- A real daily Environmental Stress Risk forecast for all 968 cells at exactly Today through +7, with confidence,
  contribution-based explanations and source freshness.
- 968 Jordan grid cells for **+16 days** and **+32 days**.
- Latest common model-evaluable input snapshot: **2025 period 21**, nominal period end **2 December 2025**.
- Risk score, Low/Moderate/High/N/A, saved-model prediction, local TreeSHAP factors, and input completeness for each cell.
- CSV, JSON, and GeoJSON datasets under `data/`.
- FastAPI endpoints, interactive API docs, React/Leaflet PWA, offline bundled data, source models, and smoke tests.
- Arabic-first, fully bilingual Arabic/English interface with correct RTL/LTR layouts.
- A geographically recognizable, lightweight Jordan illustration on the home page; the risk dots share the country outline's real-coordinate projection while the full Leaflet Explorer remains unchanged.
- Offline Arabic/English real-world location labels for all 968 cells, with governorate, nearby locality where defensible, and broad Badia labels for remote desert cells.
- A plain-language action guide that turns each level into safe next steps: review the inputs, verify in the field, check water delivery and losses, prioritise sensitive areas, and record the outcome.
- A restrained Jordan-inspired visual system using sandstone, basalt, Jordan red, and Jordan green.
- A three-minute Arabic demo script and a concise Definition of Done.
- A final test report covering API, browser, offline fallback, and launcher checks.

## Quick start on Windows

From PowerShell in this folder:

```powershell
.\setup_demo.ps1
.\start_demo.ps1
```

Open:

- App: `http://127.0.0.1:4173/`
- API docs: `http://127.0.0.1:4173/api/docs`

When finished:

```powershell
.\stop_demo.ps1
```

Requirements: Python 3.10+ and Node.js 18+. `setup_demo.ps1` also detects the Python runtime bundled with Codex on this
computer. The first setup needs internet access for packages. Viewing the included snapshots is local; refreshing the daily
snapshot uses the approved Open-Meteo endpoints and does not require Earth Engine.

## Manual run

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
cd frontend
npm install
npm run build
cd ..
```

Run the packaged single-origin demo server:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 4173
```

FastAPI serves both `frontend/dist/` and `/api` on the same local origin. This
keeps the packaged demo compatible with embedded browsers that restrict
cross-port requests.

## What the AI does

The saved XGBoost models combine recent vegetation condition, its seasonal anomaly, rainfall windows, temperature, soil moisture, and seasonal timing. For each grid cell they estimate the future vegetation anomaly at +16 or +32 days. The product then:

1. compares that prediction with the matching 2015–2022 seasonal distribution;
2. assigns a transparent 0–100 follow-up priority index;
3. highlights the model inputs that contributed most to that cell's result; and
4. helps users decide where to review data and conduct field checks first.

It does **not** diagnose drought or desertification, identify a physical cause, prescribe irrigation automatically, or replace local expertise. The action guide is decision support: current operational data and field verification are required before any intervention.

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Service and local-file readiness |
| `GET /api/areas?horizon=16` | Horizon-specific national summary |
| `GET /api/national-summary` | Both horizons in one response |
| `GET /api/cells?horizon=16` | Cell JSON for +16 or +32 days |
| `GET /api/cells?horizon=16&format=geojson` | Map-ready GeoJSON |
| `GET /api/cells/{id}?horizon=16` | One cell record |
| `GET /api/metrics` | XGBoost vs persistence evaluation |
| `GET /api/metadata` | Provenance, method, thresholds, and limitations |
| `GET /api/daily/status` | Daily champion, snapshot, source and freshness readiness |
| `GET /api/daily/forecast` | Daily risk for one lead or all eight leads |
| `GET /api/daily/cells/{id}` | One cell's complete Today-through-+7 detail |
| `GET /api/daily/summary` | National counts and mean score for all eight leads |
| `GET /api/daily/metrics` | Promoted daily champion's real held-out metrics |

## Risk method

For each horizon, the frozen XGBoost model estimates the future NDVI anomaly. The demo converts that prediction into a transparent index:

```text
risk score = empirical percentile of (-predicted anomaly)
             in the 2015–2022 training target distribution
             for the same source period and horizon
```

- Low: 0.0–39.9
- Moderate: 40.0–69.9
- High: 70.0–100.0
- N/A: current NDVI or its seasonal anomaly is unavailable

Negative predicted anomalies produce stronger stress signals. Per-cell top factors are the largest absolute TreeSHAP contributions from the saved model. They explain model behavior, not physical causes.

Map polygons are approximate squares reconstructed from each supplied centroid and area. They are visualization footprints, not official boundaries.

## Home illustration and offline cell locations

The small home-card illustration uses a simplified Natural Earth Admin-0 Jordan boundary rather than a freehand polygon. Its
historical risk dots use the same geographic projection and are clipped to the outline. This is intentionally separate from
the working Leaflet Explorer/Tracking map, whose layout and interaction model were not replaced.

The Explorer resolves each selected cell from its saved centroid without runtime geocoding. A reproducible builder assigns
governorates by point-in-polygon against a pinned geoBoundaries Jordan ADM1 dataset, then uses a significant GeoNames place
only when it is in the same governorate and within 18 km. Remote cells receive a broad Eastern, Central or Southern Badia
label where appropriate; otherwise only the governorate is shown.

- Coverage: **968/968 cells**.
- Display labels: **256 nearby locality**, **615 broad Badia region**, **97 governorate-only**.
- Governorate assignment: **962 point-in-polygon**, plus **6 unique nearest-boundary fallbacks within 2 km** for small
  differences between the grid and public boundary source.
- Runtime network requests: **none**. Source files, checksums, licences and the complete cached mapping are under
  `data/location_sources/` and `data/cell_locations.json`.

This mapping changes display context only. It does not alter model inputs, predictions, risk scores, the promoted champion,
Today-through-+7 forecasts, or the separate +16/+32 outlook.

## Evaluation

| Horizon | Split | XGBoost MAE | Persistence MAE | Improvement |
|---|---|---:|---:|---:|
| +16 | Validation 2023 | 0.005072 | 0.005446 | 6.9% |
| +16 | Test 2024–2025 | 0.004711 | 0.004840 | 2.7% |
| +32 | Validation 2023 | 0.006047 | 0.006907 | 12.4% |
| +32 | Test 2024–2025 | 0.005536 | 0.006193 | 10.6% |

Training used 2015–2022, model selection used 2023, and the frozen final test used 2024–2025. Targets stay inside each calendar year.

## Rebuild the saved snapshot

The final `data/` files are already included. To regenerate them from the original supplied artifacts:

```powershell
.\.venv\Scripts\python.exe scripts\prepare_demo_data.py `
  --source-dir "PATH_TO_EXTRACTED_ARTIFACTS" `
  --output-dir data `
  --frontend-public frontend\public
```

Expected artifact names are recorded in `data/provenance.json`. The script reuses the saved XGBoost models and verifies its predictions against the supplied prediction CSVs; it does not retrain.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests -q
cd frontend
npm run build
```

The smoke suite checks every endpoint against both fixture data and the included 968-cell snapshot. The frontend build verifies the full React bundle. Visual QA covers Arabic and English, RTL/LTR direction, desktop and mobile breakpoints, the action guide, and API/offline states.

Latest map/location verification: **46/46 frontend tests passed**, **15/15 relevant backend tests passed**, and the production
build passed with **104 modules transformed**. Browser E2E also passed for the corrected silhouette and selected-cell labels
in Arabic/RTL and English/LTR at desktop and 390 x 844 mobile sizes. Amman and a remote Eastern Badia/Mafraq cell were
selected through the real Explorer UI; the browser console reported **0 errors and 0 warnings**.

## Project structure

```text
BADIA_AI_MVP/
├─ backend/          FastAPI service and tests
├─ data/             API-ready CSV/JSON/GeoJSON + provenance
├─ frontend/         React/Vite/Leaflet PWA and production build
├─ models/           Saved XGBoost models and compact evaluation artifacts
├─ scripts/          Deterministic demo-data preparation
├─ DEMO_SCRIPT_AR.md Three-minute Arabic presentation script
├─ TEST_REPORT.md    Final automated and browser verification
└─ DEFINITION_OF_DONE.md
```

## Scope intentionally excluded

No Android app, IoT integration, user accounts, live Earth Engine dependency, complex MLOps, field-ground-truth claim, or causal interpretation is included.


## Daily forecast layer (eight dates: Today through +7 days)

The daily product is separate from the +16/+32-day vegetation outlook. Its 0-100 Environmental Stress Risk is a relative
severity index, not a probability.

The package now ships the first real promoted daily champion, **`v20261007T064409`**, trained on verified Open-Meteo
historical data from 24 deterministic Jordan anchors. Its chronological final test contains 14,400 rows and achieved MAE
0.063598 versus 0.137855 for persistence and 0.116524 for climatology. It passed the time-based, per-lead, baseline and
four-fold spatial promotion gates. Exact metrics and limitations are in `DAILY_METHODOLOGY.md`.

The included fresh production snapshot was generated on 7 October 2026. It contains all **968 cells x 8 leads** and covers
2026-10-07 through 2026-10-14. It preserves the provider's truth that the exact forecast issue timestamp was unavailable
(`issued_at: null`), reports the latest observation/satellite dates separately, and never substitutes fake zeros for
missing data.

Commands: `update` refreshes predictions without retraining; `retrain` runs the gated candidate/champion workflow;
`rollback` restores a prior valid champion; and `status` reports readiness. Acquisition/training commands and the complete
scientific record are documented in `HANDOFF_INCOMPLETE.md` and `DAILY_METHODOLOGY.md`.

See `DAILY_METHODOLOGY.md` (science) and `deploy/README_SCHEDULING.md` (automatic update/retrain).
