from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.main import create_app  # noqa: E402


DATA = ROOT / "data"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_offline_location_lookup_covers_exactly_the_968_grid_cells() -> None:
    payload = _load(DATA / "cell_locations.json")
    grid = _load(DATA / "near_real_time_2026_08_28" / "BADIA_968_GRID.geojson")
    grid_ids = {str(feature["properties"]["cell_id"]) for feature in grid["features"]}
    assert payload["cell_count"] == 968
    assert set(payload["cells"]) == grid_ids
    assert sum(payload["counts_by_location_kind"].values()) == 968
    assert payload["counts_by_governorate_assignment_method"] == {
        "nearest_boundary_within_2km": 6,
        "point_in_polygon": 962,
    }
    for location in payload["cells"].values():
        assert location["governorate_code"]
        assert location["governorate_en"].endswith(" Governorate")
        assert location["governorate_ar"].startswith("محافظة ")
        assert location["location_label_en"]
        assert location["location_label_ar"]


def test_boundary_mismatch_fallback_is_small_explicit_and_auditable() -> None:
    cells = _load(DATA / "cell_locations.json")["cells"]
    fallback = {
        cell_id: location
        for cell_id, location in cells.items()
        if location["governorate_assignment_method"] == "nearest_boundary_within_2km"
    }
    assert set(fallback) == {"12,334", "12,335", "22,361", "31,348", "31,359", "33,360"}
    assert all(0 < row["governorate_boundary_distance_km"] <= 2.0 for row in fallback.values())
    assert fallback["12,334"]["governorate_code"] == "JO-AQ"
    assert fallback["22,361"]["governorate_code"] == "JO-IR"
    assert fallback["31,348"]["governorate_code"] == "JO-AM"
    assert fallback["31,359"]["governorate_code"] == "JO-MA"


def test_representative_city_and_remote_badia_labels_are_sensible() -> None:
    cells = _load(DATA / "cell_locations.json")["cells"]
    expected = {
        "21,354": ("Amman", "JO-AM"),
        "20,357": ("Jerash", "JO-JA"),
        "20,360": ("Irbid", "JO-IR"),
        "23,358": ("Mafraq", "JO-MA"),
        "11,327": ("Aqaba", "JO-AQ"),
        "19,345": ("Karak", "JO-KA"),
        "17,341": ("Tafileh", "JO-AT"),
    }
    for cell_id, (locality, governorate_code) in expected.items():
        assert cells[cell_id]["locality_en"] == locality
        assert cells[cell_id]["governorate_code"] == governorate_code
        assert cells[cell_id]["location_kind"] == "nearby_locality"
        assert cells[cell_id]["locality_distance_km"] <= 8.0

    remote = cells["27,355"]
    assert remote["location_label_en"] == "Eastern Badia — Mafraq Governorate"
    assert remote["location_label_ar"] == "البادية الشرقية — محافظة المفرق"
    assert remote["locality_en"] is None
    assert remote["location_kind"] == "broad_region"


def test_source_hashes_and_embedded_medium_term_files_match_lookup() -> None:
    payload = _load(DATA / "cell_locations.json")
    assert payload["sources"]["governorates"]["sha256"] == _sha256(
        DATA / "location_sources" / "geoBoundaries-JOR-ADM1.geojson"
    )
    assert payload["sources"]["localities"]["sha256"] == _sha256(
        DATA / "location_sources" / "GeoNames-JO.zip"
    )
    lookup = payload["cells"]
    for name in ("cells_16.json", "cells_32.json"):
        rows = _load(DATA / name)["cells"]
        assert len(rows) == 968
        assert all(row["location_label_en"] == lookup[row["cell_id"]]["location_label_en"] for row in rows)
    for name in ("cells_16.geojson", "cells_32.geojson"):
        features = _load(DATA / name)["features"]
        assert len(features) == 968
        assert all(
            feature["properties"]["location_label_en"]
            == lookup[feature["properties"]["cell_id"]]["location_label_en"]
            for feature in features
        )
    demo = _load(ROOT / "frontend" / "public" / "demo-data.json")
    for collection in demo["cells"].values():
        features = collection["features"]
        assert len(features) == 968
        assert all(
            feature["properties"]["location_label_ar"]
            == lookup[feature["properties"]["cell_id"]]["location_label_ar"]
            for feature in features
        )


def test_cell_detail_api_preserves_the_bilingual_location_contract() -> None:
    client = TestClient(create_app(data_dir=DATA))
    response = client.get("/api/cells/20%2C357", params={"horizon": "16"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["cell_id"] == "20,357"
    assert payload["location_label_en"] == "Jerash — Jerash Governorate"
    assert payload["location_label_ar"] == "جرش — محافظة جرش"
    assert payload["location_kind"] == "nearby_locality"
    assert payload["governorate_assignment_method"] == "point_in_polygon"
