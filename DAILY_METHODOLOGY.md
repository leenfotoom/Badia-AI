# BADIA Daily Environmental Stress Risk - methodology

## Implemented status and evidence

The first real daily model is trained and promoted. The active champion is
`v20261007T064409`, promoted on 7 October 2026 after passing the predefined candidate gates. Its immutable model,
climatology, calibration and metrics artifacts are under `models/daily/versions/v20261007T064409/`; the data evidence is
in `data/daily/dataset/manifest.json`. The production snapshot contains all 968 cells and all eight leads for
7-14 October 2026.

The measured values below come from that saved model's chronological holdout, not from demo or synthetic data. Tables
show six decimal places for readability; the exact full-precision values are preserved in `metrics.json` and
`backtest_summary.json` in the version directory.

## Five different layers - do not conflate

| Layer | What it is | Timeliness |
|---|---|---|
| Weather forecast | ECMWF IFS 0.25 degree forecast via Open-Meteo | Refreshed by the update job; retrieval age shown in the UI |
| Observations | ERA5 reanalysis daily aggregates via Open-Meteo Archive | Delayed; **not live** |
| Satellite vegetation state | MODIS MOD13Q1 16-day composite from the existing package | Latest available near-real-time composite; delayed, and not a daily-model input |
| Daily forecast (this layer) | Environmental stress for exactly Today, +1, +2, +3, +4, +5, +6 and +7 | Model output for eight target dates |
| +16/+32-day outlook | Existing XGBoost vegetation-anomaly models, unchanged | Separate medium-term vegetation outlook |

## Target and risk score

The model target is Environmental Stress Index (ESI, `target.py`) per cell and target date, constrained to [0,1]. It is a
fixed a-priori weighted composite of observed climatological percentiles: soil-moisture deficit 0.35, 30-day rain deficit
0.25, daily-maximum VPD 0.25 and daily-maximum temperature 0.15. The weights were fixed before validation and were not
tuned. All four components must exist. The ESI is meteorological environmental stress, not daily NDVI, measured vegetation
condition, desertification or field diagnosis.

The displayed 0-100 value is the predicted ESI's percentile in the training-period ESI distribution. Bands remain Low
below 40, Moderate from 40 through 69, and High from 70. It is a **relative severity index, not a probability**. The
evaluation AUC uses the frozen high-stress ESI threshold 0.7100837903361255; that classification diagnostic does not turn
the displayed score into a probability.

## Predictors and horizons

One XGBoost model uses `lead_days` 0..7 as one of 25 predictors. Reference day T is the user-visible Today and lead L
targets T+L, so a complete response always contains exactly eight dates. The other predictors are:

- day-of-year sine/cosine, latitude, longitude and elevation;
- antecedent soil moisture and percentile, seven-day change, 7/30/90-day rainfall, 30-day rainfall percentile, dry-spell
  length, and seven-day mean maximum temperature and VPD;
- target-day forecast precipitation, cumulative forecast precipitation through the target, forecast dry days,
  maximum/minimum/mean temperature, VPD, and forecast temperature/VPD percentiles.

TreeSHAP contributions are grouped into soil moisture, recent rain, forecast rain, heat and atmospheric dryness.
Explanations describe model contributions or associations, never causes; contributions below 0.01 ESI are not displayed.

## Real data and acquisition

| Artifact | Real coverage | Rows / cells | Provider and use |
|---|---:|---:|---|
| Fixed climatology | 2015-01-01 through 2023-12-31 | 78,888 rows at 24 deterministic anchors | Open-Meteo Archive ERA5; target percentiles and feature percentiles |
| Daily observations | 2023-11-28 through 2026-09-30 | 24,912 rows at 24 anchors | Open-Meteo Archive ERA5; labels and lagged antecedent state |
| Historical forecast inputs | 2024-03-07 through 2026-09-30 | 178,944 retained rows, 24 anchors, leads 0..7 | Open-Meteo Previous Runs, ECMWF IFS 0.25 degree |
| Production grid | snapshot generated 2026-10-07 | 968 cells x 8 leads = 7,744 predictions | Current ECMWF forecast plus delayed observation state |

The first provider date verified complete for every required variable and every lead is **2024-03-07**. Acquisition is
chunked, cached, checksummed and resumable. The final acquisition reused 3/3 archive parts; for Previous Runs it reused 24
of 31 parts and fetched 7. Local training and backtesting consume the consolidated verified files and do not redownload
provider data.

Six provider-wide outage dates were explicitly excluded: **2026-04-17, 2026-04-18, 2026-04-19, 2026-04-20,
2026-04-21 and 2026-04-22**. The rule is strict: a whole valid date may be excluded only when every missing
`(valid_date, lead_days)` combination is missing for all requested cells. Any partial-cell gap fails validation. Values are
never filled. Retained data must form the complete expected cell x valid-date x lead grid with exactly leads 0..7, and
feature construction keeps only complete cell x issue-day eight-lead cohorts.

The 24 anchors are a deterministic, spatially distributed acquisition set that keeps public-provider request volume
practical while supporting held-out spatial validation. The initial model passed every gate and four-fold spatial CV, so
there was no evidence-based reason to expand automatically to 48 or 96 anchors in this run. This choice limits local
resolution: it does not prove that all microclimates among the 968 production cells are represented.

Conservative validation rejects non-finite or physically impossible precipitation, VPD, soil moisture and temperature
values. Tiny ERA5 interpolation round-off in soil moisture, within 0.01 of the [0,1] range, is normalized to the boundary;
larger violations fail rather than being silently discarded.

## Leakage prevention

- Observed inputs for historical issue day T stop at T-5 days, matching the configured ERA5 availability lag.
- Historical weather inputs use the Open-Meteo Previous Runs reference run for lead 0 and `previous_day1..7` for leads
  1..7. They are fixed 24-hour-offset approximations, not exact archived model initialization timestamps. This limitation
  is recorded in the manifest. Reanalysis is not substituted as a forecast input.
- Cumulative forecast rain is the sum of forecast values from T through T+L, each at its own lead.
- Target-day observations are attached only as labels and never enter the predictor matrix.
- Chronological splits purge any row whose issue day or target date crosses a boundary. Seven-day embargoes separate train
  from validation and validation from test.
- Climatology is fixed to 2015-2023 and versioned with the model. Serving verifies the champion's immutable climatology
  artifacts instead of loading mutable acquisition output.

## Training and backtesting design

The promoted model used seed 42 and stopped at boosting iteration 178.

| Split | Issue-day period | Rows |
|---|---:|---:|
| Train | 2024-03-07 through 2026-04-27 | 147,048 |
| Validation | 2026-05-05 through 2026-07-03 | 10,848 |
| Final test | 2026-07-11 through 2026-09-23 | 14,400 |

The gaps 28 April-4 May and 4-10 July are embargoes. The final test has 1,800 observations per lead and uses the same set of
issue dates for every lead. Baselines are persistence and climatology, evaluated on the same rows as the model. MAE, RMSE
and R-squared use ESI units; Spearman measures rank agreement; AUC measures discrimination at the frozen high-stress target
threshold. Skill is `1 - model_MAE / baseline_MAE`, so positive values mean improvement over that baseline.

### Overall measured results

| Split | n | MAE | RMSE | R-squared | Spearman | High-stress AUC | Persistence MAE | Climatology MAE | Skill vs persistence | Skill vs climatology |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Validation | 10,848 | 0.068310 | 0.088417 | 0.650260 | 0.802956 | 0.901688 | 0.135969 | 0.110564 | 0.497603 | 0.382168 |
| Final test | 14,400 | 0.063598 | 0.085631 | 0.642085 | 0.804608 | 0.900131 | 0.137855 | 0.116524 | 0.538662 | 0.454208 |

### Final-test results by lead

| Lead | n | MAE | RMSE | R-squared | Spearman | AUC | Persistence MAE | Climatology MAE | Skill vs persistence | Skill vs climatology |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 1,800 | 0.049084 | 0.065142 | 0.776685 | 0.884211 | 0.943960 | 0.130270 | 0.115170 | 0.623211 | 0.573809 |
| 1 | 1,800 | 0.049463 | 0.064425 | 0.783420 | 0.893529 | 0.948662 | 0.132691 | 0.115041 | 0.627229 | 0.570035 |
| 2 | 1,800 | 0.055092 | 0.075211 | 0.721985 | 0.865383 | 0.935179 | 0.136965 | 0.116824 | 0.597764 | 0.528417 |
| 3 | 1,800 | 0.060704 | 0.081150 | 0.682570 | 0.837922 | 0.917029 | 0.141737 | 0.117132 | 0.571715 | 0.481748 |
| 4 | 1,800 | 0.066707 | 0.087551 | 0.632563 | 0.799715 | 0.899761 | 0.144083 | 0.116937 | 0.537023 | 0.429547 |
| 5 | 1,800 | 0.068631 | 0.092221 | 0.591753 | 0.773868 | 0.884499 | 0.140695 | 0.116517 | 0.512200 | 0.410980 |
| 6 | 1,800 | 0.075115 | 0.100300 | 0.520124 | 0.721141 | 0.847401 | 0.137350 | 0.116555 | 0.453115 | 0.355540 |
| 7 | 1,800 | 0.083985 | 0.108607 | 0.459556 | 0.674114 | 0.831525 | 0.139047 | 0.118015 | 0.395999 | 0.288354 |

Accuracy declines with horizon, but the model beats both baselines at every tested lead.

### Spatial and seasonal checks

Spatial cross-validation on the training window used four held-out latitude-band folds: mean MAE
**0.08053588152030673** and mean Spearman **0.8357786182707089**.

| Final-test season, by target date | n | MAE | RMSE | R-squared | Spearman | AUC | Persistence MAE | Climatology MAE | Skill vs persistence | Skill vs climatology |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| JJA | 9,312 | 0.062093 | 0.079170 | 0.673068 | 0.818859 | 0.908366 | 0.137723 | 0.125266 | 0.549144 | 0.504310 |
| SON | 5,088 | 0.066351 | 0.096341 | 0.583589 | 0.789349 | 0.892620 | 0.138096 | 0.100523 | 0.519530 | 0.339943 |
| DJF | 0 | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| MAM | 0 | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |

DJF and MAM are not estimated because the final-test target dates contain no samples from those seasons. No number is
imputed for them.

## Production snapshot, provenance and freshness

The successful update generated `forecast_2026-10-07.json` at **2026-10-07 10:00:49 +03:00**. It contains all 968
requested cells, no incomplete-horizon exclusions, and exactly leads 0..7 covering **2026-10-07 through 2026-10-14**.
The source and snapshot states are `fresh`.

- Forecast: ECMWF IFS 0.25 degree via Open-Meteo, retrieved 2026-10-07 10:02:00 +03:00. The provider response did not
  expose an exact issue timestamp, so it is recorded as `not_provided_by_provider`, never inferred.
- Antecedent observation state: ERA5 daily aggregates, latest available date 2026-10-02, retrieved
  2026-10-07 09:45:25 +03:00; delayed and not live.
- Satellite context: MODIS MOD13Q1 16-day composite dated 2026-08-28; latest available near-real-time context, delayed and
  not an input to this daily model.
- Last successful snapshot update: 2026-10-07 10:00:49 +03:00. Model version and promotion timestamp propagate with the
  output.

Freshness states are fresh (at most 18 hours), stale (18-72 hours or a fallback copy), expired (more than 72 hours),
not_initialized and unavailable. Missing, expired or unavailable inputs are represented as states; the system does not
invent zero values.

## Confidence and update policy

The displayed confidence/data-quality heuristic combines 0.4 x validated per-lead Spearman, 0.3 x input completeness and
0.3 x freshness. High is at least 0.70, medium is at least 0.45, otherwise low. This is not a calibrated probability.

Prediction refresh and model retraining are separate. The deployment templates refresh predictions every six hours without
retraining. A weekly retraining check first requires at least 30 days since the last promotion and at least 21 newly verified
label days; only then may it acquire increments, train a candidate, replay the fixed holdout and apply the promotion gates.
An invalid or inferior candidate is not promoted, and rollback remains available. Scheduling templates have passed
validation, but no host scheduler task was installed during this work session.

## Limitations

- Historical weather inputs are fixed-offset Previous Runs approximations, not exact archived initialization runs.
- Labels are gridded ERA5 reanalysis rather than station or field truth, and the ESI is meteorological stress rather than
  observed ecological damage.
- Only 24 deterministic spatial anchors were used for training. Their 2015-2023 climatologies are mapped to each of the 968
  target cells by nearest anchor and must not be presented as cell-specific climatology.
- The final independent test covers only JJA and SON; winter and spring performance remain unmeasured.
- Only one NWP model is used. Forecast uncertainty and systematic weather-model errors can propagate into the ESI forecast.
- Delayed ERA5 availability means the antecedent state is several days old. MODIS is still more delayed and is context only.
- Horizon performance degrades toward +7, as the per-lead results show.
- Open-Meteo data are CC BY 4.0 and its free tier is non-commercial; licensing and service terms must be reviewed before
  commercial deployment.
- The +16/+32 vegetation outlook remains a separate product and must not be interpreted as this daily forecast.
