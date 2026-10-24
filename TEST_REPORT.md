# Verification report

## Home Jordan illustration and offline cell locations - 7 October 2026

### Implemented and data-checked

- The home-page card's freehand polygon was replaced with a simplified Natural Earth Jordan Admin-0 outline. Risk dots use
  the same real-coordinate projection and are clipped to the country silhouette. The full Leaflet Explorer/Tracking map
  was not redesigned or replaced.
- The saved offline lookup maps **968/968 cells** to bilingual Arabic/English governorate labels. Of these, **256** use a
  nearby locality, **615** use a broad Badia regional label, and **97** use only the governorate.
- **962** governorate assignments are point-in-polygon results against the pinned geoBoundaries ADM1 geometry. The remaining
  **6** are explicit unique-nearest-boundary fallbacks no farther than 2 km, covering small differences between source
  boundaries; the mapping fails rather than guessing beyond that limit or on an ambiguous tie.
- Nearby names come from the pinned GeoNames Jordan dump, must be in the same governorate, and are shown only within 18 km.
  Remote desert cells use a broad Badia region where appropriate instead of an invented city name.
- The mapping, source files and hashes are saved locally, so clicking a cell makes no geocoding request. No trained model,
  champion, prediction, risk score, daily horizon, or +16/+32 outlook was changed.

### Automated checks

- Frontend suite: **46 passed, 0 failed, 0 skipped**.
- Relevant backend location/API suite: **15 passed, 0 failed**.
- Production build: **passed** with Vite 5.4.21; **104 modules transformed**.

### Browser E2E for the new map/location work

- **Passed** in the real packaged application on 7 October 2026.
- The home-card Jordan silhouette, retained risk dots, mean score and legend rendered cleanly in Arabic/RTL and English/LTR
  on desktop and at a 390 x 844 mobile viewport.
- The unchanged Explorer selected cell `21,354` and visibly displayed `عمّان — محافظة عمّان` / `Amman — Amman Governorate`
  as the primary heading, with the cell ID secondary. The same location appeared in the map selection chip.
- Remote cell `27,355` displayed `البادية الشرقية — محافظة المفرق` / `Eastern Badia — Mafraq Governorate`; it was not
  falsely assigned to Mafraq city. The mobile selected-cell layout remained usable.
- Automated mapping/API checks covered Amman, Jerash, Irbid, Mafraq, Aqaba, Karak, Tafileh and the remote Badia sample.
- Browser console result: **0 errors, 0 warnings**.

## Daily completion checks - 7 October 2026

### Real data, model and update

- Historical acquisition resumed from the saved 2024-07-09 boundary and completed through 2026-09-30 without deleting
  or redownloading completed parts.
- Verified dataset: 78,888 climatology rows, 24,912 observation rows and 178,944 retained historical forecast rows at 24
  anchors. Leads are exactly 0..7; the expected retained grid has no duplicates, missing rows or unexpected rows.
- Six provider-wide forecast outage dates, 2026-04-17 through 2026-04-22, are explicitly excluded and never filled.
- Real champion **`v20261007T064409`** passed all configured gates. The 14,400-row chronological final test measured MAE
  0.063598, RMSE 0.085631, R-squared 0.642085 and Spearman 0.804608, versus persistence MAE 0.137855 and climatology MAE
  0.116524. It beat both baselines for every lead 0..7.
- Four-fold held-out latitude-band spatial CV measured mean MAE 0.080536 and mean Spearman 0.835779.
- The real update produced a fresh **968-cell x 8-lead** snapshot covering 2026-10-07 through 2026-10-14. The exact provider
  issue timestamp was unavailable and remains null rather than inferred.

### Automated checks

- Final backend full suite: **132 passed, 0 failed**; one upstream Starlette deprecation warning.
- Latest frontend suite after the map/location work: **46 passed, 0 failed, 0 skipped**.
- Relevant backend location/API checks: **15 passed, 0 failed**.
- Frontend production build: **passed** with Vite 5.4.21; **104 modules transformed**.
- Real API smoke checks passed for health, daily status, the eight-lead national summary and multiple real cells. Health
  reported both model and snapshot ready; every national-summary lead represented all 968 cells.
- Windows scheduling definition: **validation passed**; no host tasks were registered.

### Browser checks completed for the real daily product

- The Arabic home rendered exactly eight national daily entries from Today through +7.
- Cell `19,356` rendered eight daily tabs from Today through +7. The selected +7 view displayed risk score, change from
  today, contribution-based explanation, confidence and source provenance.
- The fixed +32 button stayed selected, displayed the medium-term definition `+32 يوم`, and requested the horizon-32 API.
  The +16 view remained available.
- English switched the document to `lang=en` and LTR; Arabic switched it to `lang=ar` and RTL.
- Mobile was checked at 390 x 844. The collapsed navigation and all eight tabs were visible, English and Arabic screenshots
  were visually clean, and there was no horizontal overflow (`scrollWidth = clientWidth = 375`).
- Map/cell interaction passed; the cell route and map rendered; the browser console reported **0 errors**.

The findings below are the earlier +16/+32 MVP verification from 2 October 2026. Only the overlapping checks explicitly
listed in the 7 October section above were rerun in this continuation.

Verified on 2 October 2026 in the local Windows workspace.

## Automated checks

- FastAPI test suite: **8 passed**.
- Frontend production build: **passed** (92 modules; production assets and local Cairo Arabic font files emitted to `frontend/dist/`).
- PowerShell launcher scripts: **syntax valid**.
- Full launcher lifecycle: `start_demo.ps1` served the UI and API on one local origin; `stop_demo.ps1` removed the listener cleanly.
- Live API smoke check: health `ok`, HTTP 200 frontend, and **968** GeoJSON features at +16.

## Browser checks

- Arabic is the default interface; the English toggle switches the full UI and document direction between RTL and LTR.
- Arabic text uses the locally bundled Cairo family; English retains the original Segoe UI/system stack.
- Desktop explorer loaded all 968 cells and switched correctly between +16 and +32 days.
- Cell detail record rendered risk index, predicted anomaly, model signals, and data quality.
- Action guide rendered plain-language AI boundaries and safe next steps for every risk level.
- Science/methodology page rendered the risk formula, evaluation metrics, and limitations in both languages.
- Mobile layout checked at 390 × 844.
- Offline fallback checked after stopping the API: the bundled snapshot loaded all 968 cells.
- Embedded-browser compatibility checked: the live UI used `/api` on the same `127.0.0.1:4173` origin, with no offline banner while the service was active.
- Fresh final browser pass reported no console errors or warnings.

## Data integrity checks

- Saved-model predictions reproduced the supplied prediction files to floating-point tolerance:
  - +16 maximum absolute difference: approximately `8.08e-10`.
  - +32 maximum absolute difference: approximately `1.74e-9`.
- Both horizon snapshots contain 968 cells; six cells are labeled N/A because core vegetation input is unavailable.

## Non-blocking note

Pytest emits one upstream Starlette deprecation warning about its test client dependency. It does not affect the API, build, or demo runtime.
