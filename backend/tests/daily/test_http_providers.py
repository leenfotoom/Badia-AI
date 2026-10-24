import json
import os
import numpy as np
import pandas as pd
import pytest
from datetime import date
from urllib.parse import parse_qs, urlparse

from backend.app.daily import providers
from backend.app.daily.http import Client, HostNotAllowed, ProviderError


def hourly_payload(days=2, temp=30.0, dew=10.0, rain_hour=None, extra=()):
    t = pd.date_range("2026-01-01", periods=24 * days, freq="h").strftime("%Y-%m-%dT%H:%M").tolist()
    h = {"time": t, "temperature_2m": [temp] * len(t), "dew_point_2m": [dew] * len(t),
         "precipitation": [0.0] * len(t), "soil_moisture_0_to_7cm": [0.1] * len(t)}
    if rain_hour is not None:
        h["precipitation"][rain_hour] = 5.0
    for k in extra:
        h[k] = list(h[k.split("_previous_day")[0]])
    return h


def daily_payload(start="2026-01-01", days=2, temp=30.0, rain=0.0, soil=0.1):
    times = pd.date_range(start, periods=days, freq="D").strftime("%Y-%m-%d").tolist()
    return {"time": times, "temperature_2m_max": [temp + 5] * days,
            "temperature_2m_min": [temp - 5] * days, "temperature_2m_mean": [temp] * days,
            "precipitation_sum": [rain] * days, "vapour_pressure_deficit_max": [2.5] * days,
            "soil_moisture_0_to_7cm_mean": [soil] * days}


def test_host_allowlist_blocks_unknown_host():
    c = Client(transport=lambda u, t: (200, "{}"))
    with pytest.raises(HostNotAllowed):
        c.get_json("https://evil.example.com/v1", {})


def test_retry_then_success_and_non_retryable(tmp_path):
    calls = {"n": 0}

    def tr(url, timeout):
        calls["n"] += 1
        return (503, "") if calls["n"] < 3 else (200, json.dumps({"ok": 1}))
    c = Client(tmp_path, transport=tr, sleep=lambda s: None)
    payload, meta = c.get_json("https://api.open-meteo.com/v1/forecast", {"a": 1})
    assert payload == {"ok": 1} and calls["n"] == 3 and not meta["from_cache"]
    n = {"n": 0}

    def bad(url, timeout):
        n["n"] += 1
        return 400, "{}"
    with pytest.raises(ProviderError):
        Client(tmp_path / "x", transport=bad, sleep=lambda s: None).get_json("https://api.open-meteo.com/v1/forecast", {})
    assert n["n"] == 1  # 400 is not retried


def test_rate_limit_waits_for_provider_window(tmp_path):
    calls = {"n": 0}
    sleeps = []

    def tr(url, timeout):
        calls["n"] += 1
        return (429, '{"error":true,"reason":"Hourly API request limit exceeded"}') if calls["n"] == 1 else (200, '{"ok":true}')

    payload, _ = Client(tmp_path, transport=tr, sleep=sleeps.append, rate_limit_backoff=60).get_json(
        "https://archive-api.open-meteo.com/v1/archive", {"x": 1})
    assert payload == {"ok": True} and sleeps == [60]


def test_cache_hit_and_stale_fallback_flagged(tmp_path):
    ok = Client(tmp_path, transport=lambda u, t: (200, json.dumps({"v": 1})), sleep=lambda s: None, cache_ttl_s=0)
    ok.get_json("https://api.open-meteo.com/v1/forecast", {"q": 1})
    down = Client(tmp_path, transport=lambda u, t: (503, ""), sleep=lambda s: None, retries=1, cache_ttl_s=0)
    payload, meta = down.get_json("https://api.open-meteo.com/v1/forecast", {"q": 1})
    assert payload == {"v": 1} and meta.get("stale") is True
    with pytest.raises(ProviderError):
        down.get_json("https://api.open-meteo.com/v1/forecast", {"q": 2})  # nothing cached -> hard failure


def test_provider_error_payload_rejected(tmp_path):
    c = Client(tmp_path, transport=lambda u, t: (200, json.dumps({"error": True, "reason": "limit"})), sleep=lambda s: None, retries=0)
    with pytest.raises(ProviderError):
        c.get_json("https://archive-api.open-meteo.com/v1/archive", {})


def test_corrupt_cache_is_never_served(tmp_path):
    url = "https://api.open-meteo.com/v1/forecast"
    first = Client(tmp_path, transport=lambda u, t: (200, '{"v":1}'), sleep=lambda _: None)
    first.get_json(url, {"x": 1})
    cache_file = next(tmp_path.glob("*.json"))
    cache_file.write_text("not-json", encoding="utf-8")
    calls = {"n": 0}

    def replacement(u, t):
        calls["n"] += 1
        return 200, '{"v":2}'

    payload, meta = Client(tmp_path, transport=replacement, sleep=lambda _: None).get_json(url, {"x": 1})
    assert payload == {"v": 2} and calls["n"] == 1 and not meta["from_cache"]
    assert not list(tmp_path.glob("*.tmp"))


def test_provider_error_payload_retries_then_uses_stale_cache(tmp_path):
    url = "https://api.open-meteo.com/v1/forecast"
    Client(tmp_path, transport=lambda u, t: (200, '{"good":true}'), sleep=lambda _: None,
           cache_ttl_s=0).get_json(url, {"x": 7})
    cache_file = next(tmp_path.glob("*.json"))
    os.utime(cache_file, (1, 1))
    calls = {"n": 0}

    def provider_error(u, t):
        calls["n"] += 1
        return 200, '{"error":true,"reason":"temporary limit"}'

    payload, meta = Client(tmp_path, transport=provider_error, sleep=lambda _: None, retries=1,
                           cache_ttl_s=0).get_json(url, {"x": 7})
    assert payload == {"good": True} and meta["stale"] and calls["n"] == 2


def test_archive_parsing_vpd_and_daily_agg():
    cells = pd.DataFrame({"cell_id": ["a,1", "b,2"], "latitude": [31.0, 30.0], "longitude": [36.0, 37.0]})
    items = [{"daily": daily_payload(rain=5.0), "elevation": 800.0},
             {"daily": daily_payload(temp=40, soil=0.2), "elevation": 100.0}]
    requested = {}

    def transport(url, timeout):
        requested.update(parse_qs(urlparse(url).query))
        return 200, json.dumps(items)

    c = Client(transport=transport, sleep=lambda s: None)
    obs, static, _ = providers.fetch_archive(c, cells, date(2026, 1, 1), date(2026, 1, 2))
    assert set(obs["cell_id"]) == {"a,1", "b,2"} and len(obs) == 4
    first = obs[(obs.cell_id == "a,1")].iloc[0]
    assert first["precip_mm"] == 5.0 and first["sm_0_7"] == pytest.approx(0.1) and first["vpd_max_kpa"] == 2.5
    assert providers.vpd_kpa(np.array([40.0]), np.array([5.0]))[0] > providers.vpd_kpa(np.array([30.0]), np.array([10.0]))[0]
    assert dict(zip(static.cell_id, static.elevation_m)) == {"a,1": 800.0, "b,2": 100.0}
    assert requested["models"] == ["era5"] and "daily" in requested and "hourly" not in requested


def test_location_count_mismatch_is_an_error():
    cells = pd.DataFrame({"cell_id": ["a", "b"], "latitude": [31.0, 30.0], "longitude": [36.0, 37.0]})
    c = Client(transport=lambda u, t: (200, json.dumps({"daily": daily_payload(), "elevation": 1})), sleep=lambda s: None)
    with pytest.raises(ProviderError):
        providers.fetch_archive(c, cells, date(2026, 1, 1), date(2026, 1, 2))


def test_incomplete_days_are_dropped():
    h = hourly_payload(days=1)
    h["temperature_2m"][:10] = [None] * 10   # only 14 valid hours -> day rejected
    d = providers._daily_from_hourly({k: v for k, v in h.items()})
    assert d.empty


def test_metadata_is_oldest_and_worst_across_spatial_temporal_chunks():
    cells = pd.DataFrame({"cell_id": [str(i) for i in range(41)],
                          "latitude": np.linspace(30, 31, 41), "longitude": np.linspace(36, 37, 41)})
    calls = []

    class FakeClient:
        def get_json(self, url, params, **kwargs):
            calls.append(dict(params))
            start, end = date.fromisoformat(params["start_date"]), date.fromisoformat(params["end_date"])
            n_days = (end - start).days + 1
            count = len(params["latitude"].split(","))
            items = [{"daily": daily_payload(str(start), n_days), "elevation": 1.0} for _ in range(count)]
            number = len(calls)
            return items, {"host": "archive-api.open-meteo.com", "fetched_at": f"2026-01-0{5-number}T00:00:00+00:00",
                           "from_cache": number == 2, "stale": number == 4}

    _, _, meta = providers.fetch_archive(FakeClient(), cells, date(2026, 1, 1), date(2026, 1, 3), date_chunk_days=2)
    assert len(calls) == 4
    assert [(call["start_date"], call["end_date"]) for call in calls[::2]] == [
        ("2026-01-01", "2026-01-02"), ("2026-01-03", "2026-01-03")]
    assert meta["chunks"] == 4 and meta["stale"] is True and meta["from_cache"] is True
    assert meta["fetched_at"] == "2026-01-01T00:00:00+00:00"


def test_previous_runs_use_offsets_zero_through_seven():
    cells = pd.DataFrame({"cell_id": ["a"], "latitude": [31.0], "longitude": [36.0]})
    captured = {}

    class FakeClient:
        def get_json(self, url, params, **kwargs):
            captured.update(params)
            base = hourly_payload(days=1)
            for lead in range(1, 8):
                for variable in ("temperature_2m", "dew_point_2m", "precipitation"):
                    base[f"{variable}_previous_day{lead}"] = list(base[variable])
            return {"hourly": base}, {"host": "previous-runs-api.open-meteo.com",
                                      "fetched_at": "2026-01-02T00:00:00+00:00"}

    frame, meta = providers.fetch_previous_runs(FakeClient(), cells, date(2026, 1, 1), date(2026, 1, 1))
    assert sorted(frame["lead_days"].unique()) == list(range(8)) and len(frame) == 8
    assert "temperature_2m" in captured["hourly"]
    assert "temperature_2m_previous_day0" not in captured["hourly"]
    assert "temperature_2m_previous_day7" in captured["hourly"]
    assert meta["issue_time_contract"] == "fixed_24h_offset_approximation"
