# BADIA AI API

Read-only FastAPI service for the MVP's saved local snapshots. It never calls
Earth Engine and does not represent the data as a live forecast.

## Run

From this `backend` directory:

```powershell
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 4173
```

The default data directory is `../data`. Override it when needed with
`BADIA_DATA_DIR`. Interactive API documentation is at
`http://localhost:4173/api/docs`.

## Test

```powershell
python -m pytest -q
```

## Endpoints

- `GET /api/health`
- `GET /api/areas` (alias: `/api/national-summary`)
- `GET /api/cells?horizon=16|32&format=json|geojson`
- `GET /api/cells/{cell_id}?horizon=16|32`
- `GET /api/metrics`
- `GET /api/metadata`
