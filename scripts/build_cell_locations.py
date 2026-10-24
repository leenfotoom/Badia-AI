"""Build the offline bilingual lookup from BADIA cell centroids to real places.

This script retains its compact public sources under ``data/location_sources``
and makes no runtime geocoding calls. Run it from the repository root with
``python scripts/build_cell_locations.py``.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import re
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SOURCES = DATA / "location_sources"
GRID_PATH = DATA / "near_real_time_2026_08_28" / "BADIA_968_GRID.geojson"
OUTPUT_PATH = DATA / "cell_locations.json"

GEOBOUNDARIES_URL = (
    "https://github.com/wmgeolab/geoBoundaries/raw/"
    "9469f09592ced973a3448cf66b6100b741b64c0d/releaseData/gbOpen/JOR/ADM1/"
    "geoBoundaries-JOR-ADM1.geojson"
)
GEONAMES_URL = "https://download.geonames.org/export/dump/JO.zip"
BOUNDARY_PATH = SOURCES / "geoBoundaries-JOR-ADM1.geojson"
GEONAMES_PATH = SOURCES / "GeoNames-JO.zip"
MAX_LOCALITY_DISTANCE_KM = 18.0
MAX_BOUNDARY_FALLBACK_KM = 2.0
AMBIGUOUS_BOUNDARY_TIE_KM = 0.05

GOVERNORATES = {
    "JO-AJ": ("Ajloun", "عجلون"),
    "JO-AM": ("Amman", "عمّان"),
    "JO-AQ": ("Aqaba", "العقبة"),
    "JO-AT": ("Tafileh", "الطفيلة"),
    "JO-AZ": ("Zarqa", "الزرقاء"),
    "JO-BA": ("Balqa", "البلقاء"),
    "JO-IR": ("Irbid", "إربد"),
    "JO-JA": ("Jerash", "جرش"),
    "JO-KA": ("Karak", "الكرك"),
    "JO-MA": ("Mafraq", "المفرق"),
    "JO-MD": ("Madaba", "مادبا"),
    "JO-MN": ("Ma'an", "معان"),
}

# Canonical spellings for governorate capitals whose first GeoNames alternate
# can be uncommon. This corrects names only; cells are still assigned
# geometrically and never by a handwritten cell list.
LOCALITY_OVERRIDES = {
    "amman": ("Amman", "عمّان"),
    "zarqa": ("Zarqa", "الزرقاء"),
    "irbid": ("Irbid", "إربد"),
    "'ajlun": ("Ajloun", "عجلون"),
    "ajlun": ("Ajloun", "عجلون"),
    "aqaba": ("Aqaba", "العقبة"),
    "madaba": ("Madaba", "مادبا"),
    "mafraq": ("Mafraq", "المفرق"),
    "jarash": ("Jerash", "جرش"),
    "at tafilah": ("Tafileh", "الطفيلة"),
    "karak city": ("Karak", "الكرك"),
    "qir moav": ("Karak", "الكرك"),
    "ma'an": ("Ma'an", "معان"),
    "as salt": ("Salt", "السلط"),
}

ARABIC_RE = re.compile(r"[\u0600-\u06ff]")
PERSIAN_FORM_RE = re.compile(r"[\u067e\u0686\u0698\u06a9\u06cc]")


def _download(url: str, destination: Path) -> None:
    """Download once; a saved valid source is always reused."""
    if destination.is_file():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "BADIA-AI/1.0"})
    with urllib.request.urlopen(request, timeout=90) as response:
        content = response.read()
    destination.write_bytes(content)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _point_on_segment(x: float, y: float, a: list[float], b: list[float]) -> bool:
    ax, ay = float(a[0]), float(a[1])
    bx, by = float(b[0]), float(b[1])
    cross = (x - ax) * (by - ay) - (y - ay) * (bx - ax)
    if abs(cross) > 1e-10:
        return False
    return min(ax, bx) - 1e-10 <= x <= max(ax, bx) + 1e-10 and min(
        ay, by
    ) - 1e-10 <= y <= max(ay, by) + 1e-10


def _ring_contains(ring: list[list[float]], x: float, y: float) -> bool:
    inside = False
    previous = ring[-1]
    for current in ring:
        if _point_on_segment(x, y, previous, current):
            return True
        x1, y1 = float(previous[0]), float(previous[1])
        x2, y2 = float(current[0]), float(current[1])
        if (y1 > y) != (y2 > y):
            crossing_x = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < crossing_x:
                inside = not inside
        previous = current
    return inside


def _polygon_contains(polygon: list[list[list[float]]], x: float, y: float) -> bool:
    return bool(polygon) and _ring_contains(polygon[0], x, y) and not any(
        _ring_contains(hole, x, y) for hole in polygon[1:]
    )


def _geometry_contains(geometry: dict[str, Any], x: float, y: float) -> bool:
    if geometry.get("type") == "Polygon":
        return _polygon_contains(geometry.get("coordinates", []), x, y)
    if geometry.get("type") == "MultiPolygon":
        return any(
            _polygon_contains(polygon, x, y)
            for polygon in geometry.get("coordinates", [])
        )
    return False


def _governorate_for(
    longitude: float, latitude: float, boundaries: list[dict[str, Any]]
) -> str | None:
    matches = [
        feature["properties"]["shapeISO"]
        for feature in boundaries
        if _geometry_contains(feature["geometry"], longitude, latitude)
    ]
    if len(matches) > 1:
        raise ValueError(f"point ({latitude}, {longitude}) matched multiple governorates")
    return matches[0] if matches else None


def _segment_distance_km(
    longitude: float,
    latitude: float,
    start: list[float],
    end: list[float],
) -> float:
    """Local equirectangular point-to-segment distance (sufficient below 2 km)."""
    lon_scale = 111.320 * math.cos(math.radians(latitude))
    lat_scale = 110.574
    ax = (float(start[0]) - longitude) * lon_scale
    ay = (float(start[1]) - latitude) * lat_scale
    bx = (float(end[0]) - longitude) * lon_scale
    by = (float(end[1]) - latitude) * lat_scale
    dx, dy = bx - ax, by - ay
    denominator = dx * dx + dy * dy
    if denominator == 0:
        return math.hypot(ax, ay)
    projection = max(0.0, min(1.0, -(ax * dx + ay * dy) / denominator))
    return math.hypot(ax + projection * dx, ay + projection * dy)


def _geometry_boundary_distance_km(
    geometry: dict[str, Any], longitude: float, latitude: float
) -> float:
    if geometry.get("type") == "Polygon":
        polygons = [geometry.get("coordinates", [])]
    elif geometry.get("type") == "MultiPolygon":
        polygons = geometry.get("coordinates", [])
    else:
        return math.inf
    distances: list[float] = []
    for polygon in polygons:
        for ring in polygon:
            for start, end in zip(ring, ring[1:]):
                distances.append(
                    _segment_distance_km(longitude, latitude, start, end)
                )
    return min(distances, default=math.inf)


def _governorate_assignment(
    longitude: float, latitude: float, boundaries: list[dict[str, Any]]
) -> tuple[str | None, str, float | None]:
    """Assign ADM1 by PIP, with a documented <=2 km dataset-edge fallback."""
    contained = _governorate_for(longitude, latitude, boundaries)
    if contained is not None:
        return contained, "point_in_polygon", 0.0
    ranked = sorted(
        (
            _geometry_boundary_distance_km(feature["geometry"], longitude, latitude),
            feature["properties"]["shapeISO"],
        )
        for feature in boundaries
    )
    nearest_distance, nearest_code = ranked[0]
    if nearest_distance > MAX_BOUNDARY_FALLBACK_KM:
        return None, "unmatched", nearest_distance
    if len(ranked) > 1 and ranked[1][0] - nearest_distance <= AMBIGUOUS_BOUNDARY_TIE_KM:
        raise ValueError(
            f"ambiguous nearest governorate at ({latitude}, {longitude}): {ranked[:2]}"
        )
    return nearest_code, "nearest_boundary_within_2km", nearest_distance


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    value = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(
        dlambda / 2
    ) ** 2
    return 2 * radius * math.asin(math.sqrt(value))


def _arabic_name(alternates: str) -> str | None:
    choices = [value.strip() for value in alternates.split(",") if ARABIC_RE.search(value)]
    if not choices:
        return None
    ranked = sorted(
        enumerate(choices),
        key=lambda item: (
            bool(PERSIAN_FORM_RE.search(item[1])),
            "محافظة" in item[1],
            item[0],
        ),
    )
    return ranked[0][1]


def _load_localities(
    path: Path, boundaries: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    with zipfile.ZipFile(io.BytesIO(path.read_bytes())) as archive:
        lines = archive.read("JO.txt").decode("utf-8").splitlines()
    places: list[dict[str, Any]] = []
    for line in lines:
        fields = line.split("\t")
        if len(fields) < 19 or fields[6] != "P":
            continue
        feature_code = fields[7]
        population = int(fields[14] or 0)
        significant = feature_code in {"PPLC", "PPLA", "PPLA2", "PPLA3", "PPLA4"}
        significant = significant or (feature_code == "PPL" and population >= 10_000)
        if not significant:
            continue
        latitude, longitude = float(fields[4]), float(fields[5])
        governorate_code = _governorate_for(longitude, latitude, boundaries)
        if governorate_code is None:
            continue
        raw_en = fields[2] or fields[1]
        override = LOCALITY_OVERRIDES.get(raw_en.casefold())
        name_en, name_ar = override or (raw_en, _arabic_name(fields[3]))
        if not name_ar:
            continue
        places.append(
            {
                "geoname_id": fields[0],
                "name_en": name_en,
                "name_ar": name_ar,
                "latitude": latitude,
                "longitude": longitude,
                "governorate_code": governorate_code,
                "feature_code": feature_code,
                "population": population,
            }
        )
    unique: dict[tuple[str, str, str], dict[str, Any]] = {}
    for place in places:
        key = (
            place["governorate_code"],
            place["name_en"].casefold(),
            place["name_ar"],
        )
        current = unique.get(key)
        rank = (place["feature_code"] in {"PPLC", "PPLA"}, place["population"])
        current_rank = (
            current["feature_code"] in {"PPLC", "PPLA"}, current["population"]
        ) if current else (False, -1)
        if current is None or rank > current_rank:
            unique[key] = place
    return sorted(unique.values(), key=lambda place: int(place["geoname_id"]))


def _nearest_locality(
    latitude: float,
    longitude: float,
    governorate_code: str,
    places: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, float | None]:
    candidates = [p for p in places if p["governorate_code"] == governorate_code]
    if not candidates:
        return None, None
    distances = [
        (_haversine_km(latitude, longitude, p["latitude"], p["longitude"]), p)
        for p in candidates
    ]
    distance, place = min(distances, key=lambda item: (item[0], -item[1]["population"]))
    if distance > MAX_LOCALITY_DISTANCE_KM:
        return None, distance
    return place, distance


def _regional_label(
    governorate_code: str, longitude: float
) -> tuple[str, str] | None:
    """Return a truthful broad desert region only for remote cells."""
    if governorate_code == "JO-MA" and longitude >= 36.45:
        return "Eastern Badia", "البادية الشرقية"
    if governorate_code == "JO-AZ" and longitude >= 36.55:
        return "Eastern Badia", "البادية الشرقية"
    if governorate_code == "JO-AM" and longitude >= 36.25:
        return "Central Badia", "البادية الوسطى"
    if governorate_code in {"JO-MN", "JO-AQ", "JO-AT", "JO-KA"} and longitude >= 35.90:
        return "Southern Badia", "البادية الجنوبية"
    return None


def _location_fields(
    latitude: float,
    longitude: float,
    governorate_code: str,
    places: list[dict[str, Any]],
    assignment_method: str,
    boundary_distance_km: float,
) -> dict[str, Any]:
    governorate_name_en, governorate_name_ar = GOVERNORATES[governorate_code]
    governorate_en = f"{governorate_name_en} Governorate"
    governorate_ar = f"محافظة {governorate_name_ar}"
    locality, distance = _nearest_locality(
        latitude, longitude, governorate_code, places
    )
    base: dict[str, Any] = {
        "governorate_code": governorate_code,
        "governorate_en": governorate_en,
        "governorate_ar": governorate_ar,
        "locality_en": None,
        "locality_ar": None,
        "region_en": None,
        "region_ar": None,
        "locality_distance_km": None,
        "locality_geoname_id": None,
        "governorate_assignment_method": assignment_method,
        "governorate_boundary_distance_km": round(boundary_distance_km, 3),
    }
    if locality is not None and distance is not None:
        base.update(
            {
                "location_label_en": f"{locality['name_en']} — {governorate_en}",
                "location_label_ar": f"{locality['name_ar']} — {governorate_ar}",
                "locality_en": locality["name_en"],
                "locality_ar": locality["name_ar"],
                "locality_distance_km": round(distance, 1),
                "locality_geoname_id": locality["geoname_id"],
                "location_kind": "nearby_locality",
            }
        )
        return base
    region = _regional_label(governorate_code, longitude)
    if region is not None:
        region_en, region_ar = region
        base.update(
            {
                "location_label_en": f"{region_en} — {governorate_en}",
                "location_label_ar": f"{region_ar} — {governorate_ar}",
                "region_en": region_en,
                "region_ar": region_ar,
                "location_kind": "broad_region",
            }
        )
        return base
    base.update(
        {
            "location_label_en": governorate_en,
            "location_label_ar": governorate_ar,
            "location_kind": "governorate_only",
        }
    )
    return base


def _iter_cells(payload: dict[str, Any]) -> Iterable[dict[str, Any]]:
    if payload.get("type") == "FeatureCollection":
        for feature in payload.get("features", []):
            yield feature.setdefault("properties", {})
        return
    for cell in payload.get("cells", []):
        yield cell


def _embed_locations(path: Path, lookup: dict[str, dict[str, Any]]) -> None:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    seen: set[str] = set()
    for properties in _iter_cells(payload):
        cell_id = str(properties.get("cell_id"))
        if cell_id not in lookup:
            raise ValueError(f"{path} contains unmapped cell {cell_id}")
        properties.update(lookup[cell_id])
        seen.add(cell_id)
    if seen != set(lookup):
        raise ValueError(f"{path} is missing {len(set(lookup) - seen)} mapped cells")
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _embed_demo_bundle(path: Path, lookup: dict[str, dict[str, Any]]) -> None:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    for horizon, collection in payload.get("cells", {}).items():
        seen: set[str] = set()
        for properties in _iter_cells(collection):
            cell_id = str(properties.get("cell_id"))
            if cell_id not in lookup:
                raise ValueError(f"demo horizon {horizon} has unmapped cell {cell_id}")
            properties.update(lookup[cell_id])
            seen.add(cell_id)
        if seen != set(lookup):
            raise ValueError(f"demo horizon {horizon} does not contain every mapped cell")
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def build() -> dict[str, Any]:
    _download(GEOBOUNDARIES_URL, BOUNDARY_PATH)
    _download(GEONAMES_URL, GEONAMES_PATH)
    boundaries_payload = json.loads(BOUNDARY_PATH.read_text(encoding="utf-8-sig"))
    boundaries = boundaries_payload["features"]
    codes = {feature["properties"].get("shapeISO") for feature in boundaries}
    if codes != set(GOVERNORATES):
        raise ValueError(f"unexpected governorate codes: {sorted(codes)}")
    places = _load_localities(GEONAMES_PATH, boundaries)

    grid = json.loads(GRID_PATH.read_text(encoding="utf-8-sig"))
    features = grid.get("features", [])
    if len(features) != 968:
        raise ValueError(f"expected 968 cells, found {len(features)}")
    lookup: dict[str, dict[str, Any]] = {}
    unmatched: list[str] = []
    for feature in features:
        properties = feature.get("properties", {})
        cell_id = str(properties.get("cell_id") or feature.get("id"))
        latitude = float(properties["lat"])
        longitude = float(properties["lon"])
        governorate_code, assignment_method, boundary_distance = _governorate_assignment(
            longitude, latitude, boundaries
        )
        if governorate_code is None:
            unmatched.append(cell_id)
            continue
        lookup[cell_id] = _location_fields(
            latitude,
            longitude,
            governorate_code,
            places,
            assignment_method,
            float(boundary_distance or 0.0),
        )
    if unmatched:
        raise ValueError(
            f"{len(unmatched)} cell centroids did not match an ADM1 polygon: {unmatched[:10]}"
        )
    if len(lookup) != 968:
        raise ValueError(f"expected 968 mapped cells, found {len(lookup)}")

    counts: dict[str, int] = {}
    governorate_counts: dict[str, int] = {}
    assignment_counts: dict[str, int] = {}
    for location in lookup.values():
        kind = location["location_kind"]
        counts[kind] = counts.get(kind, 0) + 1
        code = location["governorate_code"]
        governorate_counts[code] = governorate_counts.get(code, 0) + 1
        assignment = location["governorate_assignment_method"]
        assignment_counts[assignment] = assignment_counts.get(assignment, 0) + 1

    payload = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "cell_count": len(lookup),
        "method": {
            "governorate": "cell-centroid point-in-polygon against geoBoundaries ADM1",
            "governorate_boundary_fallback": (
                "only when no polygon contains the centroid: unique nearest ADM1 boundary "
                f"within {MAX_BOUNDARY_FALLBACK_KM:.0f} km; fail beyond that or on a "
                f"tie within {AMBIGUOUS_BOUNDARY_TIE_KM:.2f} km"
            ),
            "locality": (
                "nearest significant GeoNames populated place in the same governorate, "
                f"used only within {MAX_LOCALITY_DISTANCE_KM:.0f} km"
            ),
            "remote_cells": (
                "broad Badia regional label where geographically applicable; otherwise "
                "governorate only"
            ),
            "runtime_network_requests": False,
        },
        "counts_by_location_kind": dict(sorted(counts.items())),
        "counts_by_governorate_code": dict(sorted(governorate_counts.items())),
        "counts_by_governorate_assignment_method": dict(sorted(assignment_counts.items())),
        "sources": {
            "governorates": {
                "name": "geoBoundaries JOR ADM1",
                "url": GEOBOUNDARIES_URL,
                "release_commit": "9469f09592ced973a3448cf66b6100b741b64c0d",
                "boundary_year_represented": "2006",
                "license": "Creative Commons Attribution 2.5 Generic",
                "sha256": _sha256(BOUNDARY_PATH),
            },
            "localities": {
                "name": "GeoNames Jordan country dump",
                "url": GEONAMES_URL,
                "license": "Creative Commons Attribution 4.0",
                "sha256": _sha256(GEONAMES_PATH),
                "retained_significant_places": len(places),
            },
        },
        "cells": dict(sorted(lookup.items())),
    }
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for path in (
        DATA / "cells_16.json",
        DATA / "cells_32.json",
        DATA / "cells_16.geojson",
        DATA / "cells_32.geojson",
    ):
        _embed_locations(path, lookup)
    _embed_demo_bundle(ROOT / "frontend" / "public" / "demo-data.json", lookup)
    return payload


if __name__ == "__main__":
    result = build()
    print(
        json.dumps(
            {
                "output": str(OUTPUT_PATH.relative_to(ROOT)),
                "cell_count": result["cell_count"],
                "counts_by_location_kind": result["counts_by_location_kind"],
                "counts_by_governorate_code": result["counts_by_governorate_code"],
                "counts_by_governorate_assignment_method": result[
                    "counts_by_governorate_assignment_method"
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
