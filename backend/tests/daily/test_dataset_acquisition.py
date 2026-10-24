from datetime import date

import numpy as np
import pandas as pd
import pytest

from backend.app.daily import dataset, providers
from backend.app.daily.climatology import Climatology, N_BINS, VARS
from backend.app.daily.config import LEADS, QUANTILE_NODES
from backend.app.daily.store import Paths, read_json, sha256_file, write_csv_atomic, write_json_atomic


def _cells():
    return pd.DataFrame({"cell_id": ["a", "b"], "latitude": [30.0, 31.0], "longitude": [36.0, 37.0]})


def _fake_archive(calls):
    def fetch(client, cells, start, end, **kwargs):
        calls.append((start, end))
        rows = []
        for cell in cells.itertuples(index=False):
            for when in pd.date_range(start, end, freq="D"):
                rows.append({"cell_id": str(cell.cell_id), "date": when, "precip_mm": 1.0,
                             "tmax_c": 30.0, "tmin_c": 20.0, "tmean_c": 25.0,
                             "vpd_max_kpa": 2.0, "sm_0_7": 0.2})
        static = pd.DataFrame({"cell_id": cells["cell_id"].astype(str), "elevation_m": 500.0})
        return pd.DataFrame(rows), static, {"host": "archive-api.open-meteo.com",
                                            "fetched_at": "2026-01-05T00:00:00+00:00"}
    return fetch


def _fake_forecasts(calls):
    def fetch(client, cells, start, end, leads=LEADS, **kwargs):
        calls.append((start, end))
        rows = []
        for cell in cells.itertuples(index=False):
            for when in pd.date_range(start, end, freq="D"):
                for lead in leads:
                    rows.append({"cell_id": str(cell.cell_id), "valid_date": when, "lead_days": lead,
                                 "precip_mm": float(lead), "tmax_c": 30.0, "tmin_c": 20.0,
                                 "tmean_c": 25.0, "vpd_max_kpa": 2.0})
        return pd.DataFrame(rows), {"host": "previous-runs-api.open-meteo.com",
                                    "fetched_at": "2026-01-04T00:00:00+00:00",
                                    "issue_time_contract": "fixed_24h_offset_approximation"}
    return fetch


def _valid_observations(cells, start, end):
    rows = []
    for cell in cells.itertuples(index=False):
        for when in pd.date_range(start, end, freq="D"):
            rows.append({"cell_id": str(cell.cell_id), "date": when, "precip_mm": 1.0,
                         "tmax_c": 30.0, "tmin_c": 20.0, "tmean_c": 25.0,
                         "vpd_max_kpa": 2.0, "sm_0_7": 0.2})
    return pd.DataFrame(rows)


def _valid_forecasts(cells, start, end):
    rows = []
    for cell in cells.itertuples(index=False):
        for when in pd.date_range(start, end, freq="D"):
            for lead in LEADS:
                rows.append({"cell_id": str(cell.cell_id), "valid_date": when, "lead_days": lead,
                             "precip_mm": float(lead), "tmax_c": 30.0, "tmin_c": 20.0,
                             "tmean_c": 25.0, "vpd_max_kpa": 2.0})
    return pd.DataFrame(rows)


def _fake_forecasts_with_provider_wide_outage(calls, outage_date, missing_leads):
    complete_fetch = _fake_forecasts(calls)

    def fetch(client, cells, start, end, leads=LEADS, **kwargs):
        frame, meta = complete_fetch(client, cells, start, end, leads, **kwargs)
        outage = pd.Timestamp(outage_date)
        frame = frame[~((frame["valid_date"] == outage) & frame["lead_days"].isin(missing_leads))]
        return frame.reset_index(drop=True), meta

    return fetch


def test_refresh_is_chunked_resumable_incremental_and_manifest_verified(tmp_path, monkeypatch):
    paths = Paths(tmp_path / "data", tmp_path / "models").ensure()
    archive_calls, forecast_calls = [], []
    monkeypatch.setattr(providers, "fetch_archive", _fake_archive(archive_calls))
    monkeypatch.setattr(providers, "fetch_previous_runs", _fake_forecasts(forecast_calls))
    kwargs = dict(start=date(2026, 1, 1), end=date(2026, 1, 3),
                  observation_chunk_days=50, forecast_chunk_days=2)

    manifest = dataset.refresh_training_data(object(), _cells(), paths, **kwargs)
    assert len(archive_calls) == 3 and len(forecast_calls) == 2
    assert manifest["leads"] == list(range(8)) and manifest["n_cells"] == 2
    assert manifest["provider_fetch_metadata"]["archive"]["parts_fetched"] == 3
    loaded = dataset.load_training_data(paths)
    assert set(loaded[2]["lead_days"]) == set(range(8))

    # Complete parts written before outage metadata existed remain reusable.
    legacy_sidecar = sorted(paths.forecast_parts.glob("*.meta.json"))[0]
    legacy_meta = read_json(legacy_sidecar)
    legacy_meta.pop(dataset.FORECAST_EXCLUDED_DATES_FIELD, None)
    legacy_meta.pop("forecast_outage_policy", None)
    write_json_atomic(legacy_sidecar, legacy_meta)

    archive_calls.clear()
    forecast_calls.clear()
    dataset.refresh_training_data(object(), _cells(), paths, **kwargs)
    assert archive_calls == [] and forecast_calls == []

    archive_calls.clear()
    forecast_calls.clear()
    dataset.refresh_training_data(
        object(), _cells(), paths, start=date(2026, 1, 1), end=date(2026, 1, 4),
        observation_chunk_days=50, forecast_chunk_days=2)
    assert len(archive_calls) == 1 and len(forecast_calls) == 1

    # A bad part sidecar invalidates only that temporal part.
    sidecar = sorted(paths.forecast_parts.glob("*.meta.json"))[0]
    meta = read_json(sidecar)
    meta["sha256"] = "0" * 64
    write_json_atomic(sidecar, meta)
    archive_calls.clear()
    forecast_calls.clear()
    dataset.refresh_training_data(
        object(), _cells(), paths, start=date(2026, 1, 1), end=date(2026, 1, 4),
        observation_chunk_days=50, forecast_chunk_days=2)
    assert archive_calls == [] and len(forecast_calls) == 1

    # Final artifacts are verified before pandas is allowed to parse them.
    final = paths.dataset / dataset.FORECAST_FILE
    final.write_bytes(final.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="checksum mismatch"):
        dataset.load_training_data(paths)


def test_atomic_gzip_output_is_byte_deterministic(tmp_path):
    frame = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    first, second = tmp_path / "first.csv.gz", tmp_path / "second.csv.gz"
    write_csv_atomic(frame, first)
    write_csv_atomic(frame, second)
    assert sha256_file(first) == sha256_file(second)


def test_climatology_nearest_anchor_mapping_is_deterministic_and_persisted(tmp_path):
    shape = (2, N_BINS, len(VARS), QUANTILE_NODES)
    nodes = np.empty(shape, dtype=np.float32)
    nodes[0].fill(20.0)  # b
    nodes[1].fill(10.0)  # a
    fitted = Climatology(["b", "a"], nodes, (2015, 2023))
    anchors = pd.DataFrame({"cell_id": ["b", "a"], "latitude": [0.0, 0.0], "longitude": [2.0, 0.0]})
    targets = pd.DataFrame({"cell_id": ["x", "b", "a"], "latitude": [0.0, 0.0, 0.0],
                            "longitude": [1.0, 2.0, 0.0]})
    expanded, mapping = fitted.expand_nearest(anchors, targets)
    mapped = dict(zip(mapping["cell_id"], mapping["climatology_anchor_cell_id"]))
    assert mapped == {"a": "a", "b": "b", "x": "a"}  # sorted anchor id breaks exact tie
    assert np.all(expanded.nodes[expanded.index["a"]] == 10.0)
    assert np.all(expanded.nodes[expanded.index["b"]] == 20.0)
    path = tmp_path / "climatology.npz"
    expanded.save(path)
    restored = Climatology.load(path)
    assert restored.anchor_for_cell == expanded.anchor_for_cell
    np.testing.assert_array_equal(restored.nodes, expanded.nodes)


def test_build_climatology_fits_anchors_and_records_spatial_limitation(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(providers, "fetch_archive", _fake_archive(calls))
    anchors = _cells()
    all_cells = pd.concat([anchors, pd.DataFrame({"cell_id": ["c"], "latitude": [30.2],
                                                  "longitude": [36.1]})], ignore_index=True)
    out = tmp_path / "models" / "climatology.npz"
    climatology = dataset.build_climatology(
        object(), anchors, out, all_cells=all_cells, parts_dir=tmp_path / "parts", date_chunk_days=4000)
    assert set(climatology.cell_ids) == {"a", "b", "c"} and len(calls) == 1
    metadata = read_json(out.with_name("climatology_metadata.json"))
    mapping = pd.read_csv(out.with_name("climatology_mapping.csv"), dtype={"cell_id": str})
    assert metadata["n_anchor_cells"] == 2 and metadata["n_target_cells"] == 3
    assert "approximation" in metadata["limitation"] and set(mapping["cell_id"]) == {"a", "b", "c"}


def test_verified_previous_runs_start_is_enforced(tmp_path):
    assert dataset.FC_ARCHIVE_START == date(2024, 3, 7)
    paths = Paths(tmp_path / "data", tmp_path / "models").ensure()
    with pytest.raises(ValueError, match="first verified complete"):
        dataset.refresh_training_data(
            object(), _cells(), paths, start=date(2024, 3, 6), end=date(2024, 3, 7)
        )


def test_validators_reject_missing_whole_days_and_individual_leads():
    cells = _cells()
    start, end = date(2026, 1, 1), date(2026, 1, 2)

    observations = _valid_observations(cells, start, end)
    missing_day = observations[~((observations["cell_id"] == "a") &
                                 (observations["date"] == pd.Timestamp(end)))]
    with pytest.raises(ValueError, match="coverage is missing"):
        dataset._validate_observations(missing_day, cells, start, end)

    forecasts = _valid_forecasts(cells, start, end)
    missing_day = forecasts[~((forecasts["cell_id"] == "a") &
                              (forecasts["valid_date"] == pd.Timestamp(end)))]
    with pytest.raises(ValueError, match="coverage is missing"):
        dataset._validate_forecasts(missing_day, cells, start, end)

    missing_lead = forecasts.drop(
        forecasts[(forecasts["cell_id"] == "a") &
                  (forecasts["valid_date"] == pd.Timestamp(end)) &
                  (forecasts["lead_days"] == max(LEADS))].index
    )
    with pytest.raises(ValueError, match="cell/date/lead"):
        dataset._validate_forecasts(missing_lead, cells, start, end)


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("precip_mm", -0.01, "negative precipitation"),
        ("vpd_max_kpa", -0.01, "negative VPD"),
        ("sm_0_7", 1.02, "soil moisture"),
        ("tmax_c", 71.0, "temperatures outside"),
        ("tmin_c", 31.0, "tmin greater than tmax"),
        ("tmean_c", 31.0, "tmean outside"),
        ("precip_mm", np.nan, "non-finite"),
        ("vpd_max_kpa", np.inf, "non-finite"),
    ],
)
def test_observation_validator_rejects_nonfinite_or_impossible_values(column, value, message):
    cells = _cells().iloc[:1]
    when = date(2026, 1, 1)
    observations = _valid_observations(cells, when, when)
    observations.loc[0, column] = value
    with pytest.raises(ValueError, match=message):
        dataset._validate_observations(observations, cells, when, when)


def test_observation_validator_clips_only_small_era5_soil_roundoff():
    cells = _cells().iloc[:1]
    when = date(2026, 1, 1)
    observations = _valid_observations(cells, when, when)
    observations.loc[0, "sm_0_7"] = -0.004
    validated = dataset._validate_observations(observations, cells, when, when)
    assert validated.loc[0, "sm_0_7"] == 0.0

    observations.loc[0, "sm_0_7"] = -0.02
    with pytest.raises(ValueError, match="soil moisture"):
        dataset._validate_observations(observations, cells, when, when)


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("precip_mm", -0.01, "negative precipitation"),
        ("vpd_max_kpa", -0.01, "negative VPD"),
        ("tmin_c", -101.0, "temperatures outside"),
        ("tmin_c", 31.0, "tmin greater than tmax"),
        ("tmean_c", 31.0, "tmean outside"),
        ("tmax_c", np.nan, "non-finite"),
    ],
)
def test_forecast_validator_rejects_nonfinite_or_impossible_values(column, value, message):
    cells = _cells().iloc[:1]
    when = date(2026, 1, 1)
    forecasts = _valid_forecasts(cells, when, when)
    forecasts.loc[0, column] = value
    with pytest.raises(ValueError, match=message):
        dataset._validate_forecasts(forecasts, cells, when, when)


def test_provider_wide_outage_drops_whole_date_and_persists_through_load(tmp_path, monkeypatch):
    paths = Paths(tmp_path / "data", tmp_path / "models").ensure()
    archive_calls, forecast_calls = [], []
    outage_date = date(2026, 1, 2)
    monkeypatch.setattr(providers, "fetch_archive", _fake_archive(archive_calls))
    monkeypatch.setattr(
        providers,
        "fetch_previous_runs",
        _fake_forecasts_with_provider_wide_outage(forecast_calls, outage_date, {5, 6, 7}),
    )

    manifest = dataset.refresh_training_data(
        object(), _cells(), paths, start=date(2026, 1, 1), end=date(2026, 1, 3),
        observation_chunk_days=200, forecast_chunk_days=2,
    )
    field = dataset.FORECAST_EXCLUDED_DATES_FIELD
    assert manifest[field] == ["2026-01-02"]
    previous_runs = manifest["provider_fetch_metadata"]["previous_runs"]
    assert previous_runs[field] == ["2026-01-02"]
    assert previous_runs["excluded_forecast_valid_date_count"] == 1

    first_part = read_json(sorted(paths.forecast_parts.glob("*.meta.json"))[0])
    assert first_part[field] == ["2026-01-02"]
    cells, observations, forecasts, static, loaded_manifest = dataset.load_training_data(paths)
    assert loaded_manifest[field] == ["2026-01-02"]
    assert set(forecasts["valid_date"].dt.date) == {date(2026, 1, 1), date(2026, 1, 3)}
    assert len(forecasts) == len(cells) * 2 * len(LEADS)

    # An identical rerun reuses both legacy-compatible part files and their outage metadata.
    archive_calls.clear()
    forecast_calls.clear()
    rerun = dataset.refresh_training_data(
        object(), _cells(), paths, start=date(2026, 1, 1), end=date(2026, 1, 3),
        observation_chunk_days=200, forecast_chunk_days=2,
    )
    assert archive_calls == [] and forecast_calls == []
    assert rerun[field] == ["2026-01-02"]


def test_provider_wide_outage_rejects_one_cell_gap():
    cells = _cells()
    start, end = date(2026, 1, 1), date(2026, 1, 2)
    forecasts = _valid_forecasts(cells, start, end)
    one_cell_gap = (
        (forecasts["cell_id"] == "a")
        & (forecasts["valid_date"] == pd.Timestamp(end))
        & (forecasts["lead_days"] == 7)
    )
    forecasts = forecasts.loc[~one_cell_gap]
    with pytest.raises(ValueError, match="not provider-wide"):
        dataset._exclude_provider_wide_forecast_outages(forecasts, cells, start, end)


def test_provider_wide_outage_can_exclude_an_entire_one_day_part():
    cells = _cells()
    when = date(2026, 1, 1)
    forecasts = _valid_forecasts(cells, when, when).iloc[0:0]
    retained, excluded = dataset._exclude_provider_wide_forecast_outages(
        forecasts, cells, when, when
    )
    assert retained.empty
    assert excluded == ["2026-01-01"]


def test_manifest_and_provider_metadata_must_agree_on_excluded_dates(tmp_path, monkeypatch):
    paths = Paths(tmp_path / "data", tmp_path / "models").ensure()
    monkeypatch.setattr(providers, "fetch_archive", _fake_archive([]))
    monkeypatch.setattr(
        providers,
        "fetch_previous_runs",
        _fake_forecasts_with_provider_wide_outage([], date(2026, 1, 2), {7}),
    )
    dataset.refresh_training_data(
        object(), _cells(), paths, start=date(2026, 1, 1), end=date(2026, 1, 3),
        observation_chunk_days=200, forecast_chunk_days=3,
    )
    manifest_path = paths.dataset / "manifest.json"
    manifest = read_json(manifest_path)
    manifest[dataset.FORECAST_EXCLUDED_DATES_FIELD] = []
    write_json_atomic(manifest_path, manifest)
    with pytest.raises(ValueError, match="disagree on excluded dates"):
        dataset.load_training_data(paths)
