from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.main import app, create_app  # noqa: E402
from app.priority import (  # noqa: E402
    add_national_priority,
    priority_band,
    priority_percentile,
    select_priority,
    top_priority,
)

ROOT = BACKEND_DIR.parent


def _cells(scores):
    return [{"cell_id": f"c{i}", "risk_score": s} for i, s in enumerate(scores)]


def test_rank_ties_and_nulls():
    source = _cells([90.0, 90.0, 80.0, None, 70.0])
    original = [dict(cell) for cell in source]
    out = add_national_priority(source)
    assert [c["national_priority_rank"] for c in out] == [1, 1, 3, None, 4]
    assert out[0]["national_priority_total"] == 4
    assert out[0]["national_priority_tied_count"] == 2
    assert out[0]["national_priority_percentile"] == 50.0  # tie-inclusive
    assert out[0]["national_median_score"] == 85.0
    assert out[3]["priority_band"] is None
    assert [c["risk_score"] for c in out] == [90.0, 90.0, 80.0, None, 70.0]
    assert source == original  # derived fields never mutate source/scientific values


def test_nan_and_all_null():
    out = add_national_priority(_cells([float("nan"), None, True]))
    assert all(c["national_priority_rank"] is None for c in out)
    assert out[0]["national_median_score"] is None


@pytest.mark.parametrize(
    "n,band",
    [(1, "Top 1%"), (2, "Top 5%"), (5, "Top 5%"), (6, "Top 10%"), (10, "Top 10%"), (11, "Remaining")],
)
def test_band_boundaries(n, band):
    assert priority_band(n, 100) == band


def test_percentile_uses_cross_language_half_up_rounding():
    # 1/32 = 3.125%; Python's built-in round would incorrectly produce 3.12,
    # while the shared backend/frontend rule must produce 3.13.
    assert priority_percentile(1, 32) == 3.13
    assert priority_percentile(3, 32) == 9.38

    out = add_national_priority(_cells([float(32 - i) for i in range(32)]))
    assert out[0]["national_priority_percentile"] == 3.13
    assert out[2]["national_priority_percentile"] == 9.38


def test_large_tie_group_not_promoted():
    # 100 cells all tied: nobody may claim Top 1/5/10%.
    out = add_national_priority(_cells([50.0] * 100))
    assert {c["priority_band"] for c in out} == {"Remaining"}
    assert {c["national_priority_rank"] for c in out} == {1}


def test_top_priority_deterministic():
    out = add_national_priority(_cells([float(100 - i) for i in range(100)]))
    assert len(top_priority(out, "Top 5%")) == 5
    assert [c["cell_id"] for c in top_priority(out, limit=3)] == ["c0", "c1", "c2"]
    assert top_priority(out, limit=0) == []
    with pytest.raises(ValueError, match="band must be one of"):
        top_priority(out, "Top 50%")
    with pytest.raises(ValueError, match="zero or greater"):
        top_priority(out, limit=-1)


@pytest.mark.parametrize("horizon", [16, 32])
def test_real_data_api_ranks(horizon):
    client = TestClient(app)
    payload = client.get("/api/cells", params={"horizon": horizon}).json()
    ranked = [c for c in payload["cells"] if c["risk_score"] is not None]
    assert ranked and all(c["national_priority_total"] == len(ranked) for c in ranked)
    assert min(c["national_priority_rank"] for c in ranked) == 1
    assert all(c["national_priority_rank"] is None for c in payload["cells"] if c["risk_score"] is None)
    # higher score never ranks worse
    ranked.sort(key=lambda c: -c["risk_score"])
    assert all(a["national_priority_rank"] <= b["national_priority_rank"] for a, b in zip(ranked, ranked[1:]))
    # detail + geojson agree with list
    first = ranked[0]
    detail = client.get(f"/api/cells/{first['cell_id']}", params={"horizon": horizon}).json()
    assert detail["national_priority_rank"] == first["national_priority_rank"]
    gj = client.get("/api/cells", params={"horizon": horizon, "format": "geojson"}).json()
    props = next(f["properties"] for f in gj["features"] if f["id"] == first["cell_id"])
    assert props["priority_band"] == first["priority_band"]


@pytest.mark.parametrize("horizon", [16, 32])
def test_priorities_endpoint(horizon):
    client = TestClient(app)
    r = client.get("/api/priorities", params={"horizon": horizon, "limit": 10}).json()
    assert r["count"] == 10 and r["cells"][0]["national_priority_rank"] == 1
    assert r["is_live"] is False
    band = client.get("/api/priorities", params={"horizon": horizon, "band": "Top 5%", "limit": 2000}).json()
    assert 0 < band["count"] <= r["ranked_total"] * 0.05 + 14
    assert client.get("/api/priorities?band=Top 50%").status_code == 422


def test_existing_cells_contract_unchanged():
    client = TestClient(app)
    c = client.get("/api/cells", params={"horizon": 16}).json()["cells"][0]
    for key in ("cell_id", "risk_score", "risk_level", "top_factors", "data_quality", "risk_percentile"):
        assert key in c


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_api_and_offline_bundle_ranks_match():
    out = subprocess.run(
        ["node", str(ROOT / "frontend" / "tests" / "dump_ranks.mjs")],
        capture_output=True, text=True, check=True,
    ).stdout
    js = json.loads(out)
    client = TestClient(app)
    for horizon in ("16", "32"):
        cells = client.get("/api/cells", params={"horizon": horizon}).json()["cells"]
        assert len(cells) == len(js[horizon])
        for c in cells:
            rank, pct, band = js[horizon][c["cell_id"]]
            assert rank == c["national_priority_rank"]
            assert band == c["priority_band"]
            assert pct == c["national_priority_percentile"]


def _tied_cells():
    # ranks: 1,2,3,3,3,6  (three cells tie at the rank-3 cutoff)
    return add_national_priority(_cells([100.0, 90.0, 80.0, 80.0, 80.0, 70.0]))


def test_limit_splits_tie_group_by_default_and_reports_it():
    rows, meta = select_priority(_tied_cells(), limit=4)
    assert [c["cell_id"] for c in rows] == ["c0", "c1", "c2", "c3"]
    assert meta["requested_limit"] == 4 and meta["include_cutoff_ties"] is False
    assert meta["returned_count"] == 4 and meta["cutoff_rank"] == 3
    assert meta["cutoff_tie_group_size"] == 3
    assert meta["cutoff_ties_included"] == 2 and meta["cutoff_ties_omitted"] == 1
    assert meta["cutoff_tie_group_split"] is True
    assert meta["extra_cells_beyond_limit"] == 0


def test_include_cutoff_ties_returns_whole_group():
    rows, meta = select_priority(_tied_cells(), limit=4, include_cutoff_ties=True)
    assert [c["cell_id"] for c in rows] == ["c0", "c1", "c2", "c3", "c4"]
    assert all(c["national_priority_rank"] <= 3 for c in rows)
    assert meta["returned_count"] == 5 and meta["cutoff_rank"] == 3
    assert meta["cutoff_tie_group_size"] == 3 and meta["cutoff_ties_included"] == 3
    assert meta["cutoff_ties_omitted"] == 0 and meta["cutoff_tie_group_split"] is False
    assert meta["extra_cells_beyond_limit"] == 1


def test_cutoff_without_tie_and_limit_beyond_candidates():
    cells = _tied_cells()
    rows, meta = select_priority(cells, limit=2, include_cutoff_ties=True)
    assert len(rows) == 2 and meta["cutoff_rank"] == 2
    assert meta["cutoff_tie_group_size"] == 1 and meta["cutoff_tie_group_split"] is False
    rows, meta = select_priority(cells, limit=50, include_cutoff_ties=True)
    assert len(rows) == 6 and meta["cutoff_rank"] == 6
    assert meta["extra_cells_beyond_limit"] == 0


def test_cutoff_selection_edge_cases():
    rows, meta = select_priority(_tied_cells(), limit=0, include_cutoff_ties=True)
    assert rows == [] and meta["cutoff_rank"] is None and meta["cutoff_tie_group_size"] == 0
    rows, meta = select_priority(_tied_cells())  # no limit -> everything
    assert len(rows) == 6 and meta["requested_limit"] is None
    assert select_priority([], limit=3)[1]["cutoff_rank"] is None


def test_top_priority_default_unchanged_and_values_untouched():
    cells = _tied_cells()
    snapshot = [dict(c) for c in cells]
    assert [c["cell_id"] for c in top_priority(cells, limit=4)] == ["c0", "c1", "c2", "c3"]
    assert len(top_priority(cells, limit=4, include_cutoff_ties=True)) == 5
    assert cells == snapshot


def test_tie_group_split_never_across_band_filter():
    out = add_national_priority(_cells([50.0] * 20 + [float(i) for i in range(80)]))
    rows, meta = select_priority(out, band="Top 10%", limit=5, include_cutoff_ties=True)
    assert meta["cutoff_tie_group_split"] is False
    assert all(c["priority_band"] in ("Top 1%", "Top 5%", "Top 10%") for c in rows)


@pytest.mark.parametrize("horizon", [16, 32])
def test_priorities_endpoint_cutoff_ties(horizon):
    client = TestClient(app)
    plain = client.get("/api/priorities", params={"horizon": horizon, "limit": 10}).json()
    tied = client.get(
        "/api/priorities",
        params={"horizon": horizon, "limit": 10, "include_cutoff_ties": "true"},
    ).json()
    # default stays an exact limit, but is transparent about any split
    assert plain["count"] == 10 and plain["selection"]["include_cutoff_ties"] is False
    assert plain["selection"]["requested_limit"] == 10
    # opt-in never splits the cutoff tie group and keeps the same ordering prefix
    sel = tied["selection"]
    assert sel["include_cutoff_ties"] is True and sel["cutoff_tie_group_split"] is False
    assert sel["returned_count"] == tied["count"] == len(tied["cells"]) >= 10
    assert tied["cells"][: plain["count"]] == plain["cells"]
    assert all(c["national_priority_rank"] <= sel["cutoff_rank"] for c in tied["cells"])
    every = client.get("/api/priorities", params={"horizon": horizon, "limit": 2000}).json()["cells"]
    assert tied["count"] == sum(1 for c in every if c["national_priority_rank"] <= sel["cutoff_rank"])
    assert plain["selection"]["cutoff_ties_omitted"] == sel["cutoff_tie_group_size"] - plain["selection"]["cutoff_ties_included"]
    assert client.get("/api/priorities", params={"include_cutoff_ties": "maybe"}).status_code == 422


def test_priorities_endpoint_known_tie_at_plus_16():
    # +16: rank 10 is shared, so Top 10 + ties is 13 cells (previously verified)
    client = TestClient(app)
    tied = client.get(
        "/api/priorities",
        params={"horizon": 16, "limit": 10, "include_cutoff_ties": "true"},
    ).json()
    assert tied["count"] == 13 and tied["selection"]["cutoff_rank"] == 10
    assert tied["selection"]["cutoff_ties_included"] == tied["selection"]["cutoff_tie_group_size"] == 4
    plain = client.get("/api/priorities", params={"horizon": 16, "limit": 10}).json()
    assert plain["selection"]["cutoff_ties_omitted"] == 3
    assert plain["selection"]["cutoff_tie_group_split"] is True


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_api_and_offline_cutoff_tie_selection_match():
    out = subprocess.run(
        ["node", str(ROOT / "frontend" / "tests" / "dump_selection.mjs")],
        capture_output=True, text=True, check=True,
    ).stdout
    js = json.loads(out)
    client = TestClient(app)
    for horizon in ("16", "32"):
        for key, expected in js[horizon].items():
            limit, ties = key.split("-")
            api = client.get(
                "/api/priorities",
                params={"horizon": horizon, "limit": int(limit), "include_cutoff_ties": ties},
            ).json()
            assert [c["cell_id"] for c in api["cells"]] == expected["ids"], (horizon, key)
            assert api["selection"] == expected["selection"], (horizon, key)
