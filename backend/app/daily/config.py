"""Configuration, provider allowlist and provenance for the BADIA daily engine.

Only providers declared in PROVIDERS may be contacted. Adding a provider is a code
change that must pass review; no runtime input can extend the allowlist.
"""
from __future__ import annotations

from dataclasses import dataclass

SCHEMA_VERSION = "daily-v2"
CLIMATOLOGY_BUNDLE_FILES = (
    "climatology.npz",
    "climatology_mapping.csv",
    "climatology_metadata.json",
)
# Reference day T is the user-visible "Today" in a generated forecast.  lead_days L
# targets T+L, so the product always contains exactly Today through +7.  Open-Meteo's
# Previous Runs API exposes the reference run under the ordinary variable name and
# older runs as ``*_previous_day1`` through ``*_previous_day7``.  These fixed
# offsets approximate this reference-day contract; they are not exact archived
# initialization timestamps.
LEADS = tuple(range(0, 8))
ISSUE_TIME_CONTRACT = "fixed_24h_offset_approximation"
OBS_LAG_DAYS = 5                      # ERA5 archive is normally several days behind real time
CLIM_YEARS = (2015, 2023)             # fixed reference period for percentiles (inclusive)
CLIM_BIN_DAYS = 5
CLIM_WINDOW_DAYS = 10                 # +/- days pooled around each bin centre
QUANTILE_NODES = 21                   # 0,5,...,100 %
TIMEZONE = "Asia/Amman"
FORECAST_MODEL = "ecmwf_ifs025"       # one fixed NWP model for training AND serving
HIGH_THRESHOLD = 70.0                 # same bands as the medium-term layer
MODERATE_THRESHOLD = 40.0

# Fixed a-priori ESI weights (never tuned on validation/test data).
ESI_WEIGHTS = {"sm": 0.35, "rain": 0.25, "vpd": 0.25, "heat": 0.15}

# Provider-native ERA5 daily aggregates avoid downloading 24 hourly values per variable
# merely to reconstruct daily training observations locally.
DAILY_OBS_VARS = [
    "temperature_2m_max", "temperature_2m_min", "temperature_2m_mean",
    "precipitation_sum", "vapour_pressure_deficit_max", "soil_moisture_0_to_7cm_mean",
]
# Retained as a compatibility name for callers that imported it; archive acquisition uses
# DAILY_OBS_VARS exclusively as of daily-v2.
HOURLY_OBS_VARS = ["temperature_2m", "dew_point_2m", "precipitation", "soil_moisture_0_to_7cm"]
HOURLY_FC_VARS = ["temperature_2m", "dew_point_2m", "precipitation"]

FEATURES_V1 = [
    "lead_days", "doy_sin", "doy_cos", "latitude", "longitude", "elevation_m",
    "obs_sm_last", "obs_sm_pct_last", "obs_sm_change_7d",
    "obs_rain_7d_mm", "obs_rain_30d_mm", "obs_rain_90d_mm", "obs_rain_30d_pct",
    "obs_dry_spell_days", "obs_tmax_7d_mean_c", "obs_vpd_max_7d_mean_kpa",
    "fc_precip_day_mm", "fc_precip_cum_mm", "fc_dry_days",
    "fc_tmax_c", "fc_tmin_c", "fc_tmean_c", "fc_vpd_max_kpa", "fc_tmax_pct", "fc_vpd_pct",
]


@dataclass(frozen=True)
class Provider:
    key: str
    host: str
    role: str
    license: str
    notes: str


PROVIDERS = {
    "open_meteo_forecast": Provider(
        "open_meteo_forecast", "api.open-meteo.com", "live weather forecast + recent analysis",
        "CC BY 4.0 data; free tier is non-commercial", f"model={FORECAST_MODEL}"),
    "open_meteo_previous_runs": Provider(
        "open_meteo_previous_runs", "previous-runs-api.open-meteo.com",
        "archived forecast values at fixed 0-7 day offsets for leakage-safe backtesting",
        "CC BY 4.0 data; free tier is non-commercial",
        "hourly; the reference run plus previous_day1..7 are fixed-offset approximations, "
        "not exact issue timestamps; "
        "most models from Jan 2024"),
    "open_meteo_archive": Provider(
        "open_meteo_archive", "archive-api.open-meteo.com",
        "ERA5 daily reanalysis observations (labels, climatology, antecedent state)",
        "CC BY 4.0 data; free tier is non-commercial", "provider-native daily aggregates; delayed archive"),
}
ALLOWED_HOSTS = frozenset(p.host for p in PROVIDERS.values())


def risk_level(score: float | None) -> str:
    if score is None or score != score:
        return "N/A"
    if score < MODERATE_THRESHOLD:
        return "Low"
    if score < HIGH_THRESHOLD:
        return "Moderate"
    return "High"
