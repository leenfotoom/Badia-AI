import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { DAILY_COPY, dt } from '../src/dailyCopy.js'
import {
  DAILY_LEADS,
  REASON_KEYS,
  GROUP_KEYS,
  bannerFor,
  dailyLevel,
  dailyProvenance,
  formatDayLabel,
  loadDailyCell,
  loadDailyStatus,
  normalizeDay,
  normalizeDays,
  normalizeDaysResult,
  normalizeSummaryResult,
  summaryRows,
} from '../src/daily.js'
import { chooseDashboardInputs } from '../src/api.js'
import { formatAnomaly, formatCount, formatDecimal, formatPercent, formatScore } from '../src/format.js'
import { featureCollectionSignature } from '../src/mapData.js'
import { resolveDeepLinkedHorizon } from '../src/horizon.js'

// Node has no import.meta.env; daily.js -> constants.js uses optional chaining so this import works.
const keysOf = (o, p = '') => Object.entries(o).flatMap(([k, v]) => (v && typeof v === 'object' && !Array.isArray(v) ? keysOf(v, `${p}${k}.`) : [`${p}${k}`]))

test('Arabic and English daily copy have identical keys and no empty strings', () => {
  assert.deepEqual(keysOf(DAILY_COPY.ar).sort(), keysOf(DAILY_COPY.en).sort())
  for (const lang of ['ar', 'en']) for (const k of keysOf(DAILY_COPY[lang])) assert.ok(String(dt(lang, k)).trim().length > 0, `${lang}.${k}`)
})

test('every reason and change-driver group the backend can emit has copy in both languages', () => {
  const py = readFileSync(new URL('../../backend/app/daily/pipeline.py', import.meta.url), 'utf8')
  const modeling = readFileSync(new URL('../../backend/app/daily/modeling.py', import.meta.url), 'utf8')
  const emitted = [...py.matchAll(/"((?:soil_moisture|recent_rain|forecast_rain|heat|air_dryness)_[a-z_]+)"/g)].map((m) => m[1])
  assert.ok(emitted.length >= 10, 'found backend reason keys')
  for (const k of new Set(emitted)) {
    assert.ok(REASON_KEYS.includes(k), `REASON_KEYS missing ${k}`)
    for (const lang of ['ar', 'en']) assert.notEqual(dt(lang, `reasons.${k}`), `reasons.${k}`, `${lang} copy for ${k}`)
  }
  const groupBlock = modeling.match(/GROUPS\s*=\s*\{([\s\S]*?)\n\}/)?.[1] ?? ''
  const emittedGroups = [...groupBlock.matchAll(/^\s*"([a-z_]+)"\s*:/gm)].map((m) => m[1])
  assert.ok(emittedGroups.includes('dryness'), 'found backend dryness change-driver group')
  for (const g of new Set([...GROUP_KEYS, ...emittedGroups])) {
    assert.ok(GROUP_KEYS.includes(g), `GROUP_KEYS missing ${g}`)
    for (const lang of ['ar', 'en']) assert.notEqual(dt(lang, `groups.${g}`), `groups.${g}`, `${lang} copy for ${g}`)
  }
})

test('level thresholds match the backend (40 / 70)', () => {
  assert.equal(dailyLevel(39.9), 'Low'); assert.equal(dailyLevel(40), 'Moderate')
  assert.equal(dailyLevel(69.9), 'Moderate'); assert.equal(dailyLevel(70), 'High')
  assert.equal(dailyLevel(null), 'N/A'); assert.equal(dailyLevel(undefined), 'N/A'); assert.equal(dailyLevel('x'), 'N/A')
})

test('normalizeDay keeps missing numbers null instead of inventing them', () => {
  const d = normalizeDay({ lead_days: 3, date: '2026-10-08', score: 82.4, change_vs_today: 11.2, confidence: { level: 'medium', value: 0.6 } })
  assert.equal(d.score, 82.4); assert.equal(d.level, 'High'); assert.equal(d.change, 11.2); assert.equal(d.confidence, 'medium')
  const empty = normalizeDay({ lead_days: 2 })
  assert.equal(empty.score, null); assert.equal(empty.level, 'N/A'); assert.equal(empty.change, null); assert.equal(empty.confidence, 'unknown')
  assert.equal(normalizeDay(null), null)
})

test('daily timeline accepts exactly the canonical Today-through-+7 leads and sorts them', () => {
  const cell = { days: [...DAILY_LEADS].reverse().map((lead) => ({ lead_days: lead, score: 50 + lead })) }
  assert.deepEqual(normalizeDays(cell).map((d) => d.lead), DAILY_LEADS)
  assert.equal(normalizeDaysResult(cell).valid, true)
  assert.deepEqual(normalizeDays(null), [])
})

test('daily timeline rejects missing, duplicate and out-of-range leads without inventing rows', () => {
  const canonical = DAILY_LEADS.map((lead) => ({ lead_days: lead, score: 50 }))
  const missing = normalizeDaysResult({ days: canonical.slice(0, -1) })
  const duplicate = normalizeDaysResult({ days: [...canonical.slice(0, -1), { lead_days: 6, score: 50 }] })
  const outOfRange = normalizeDaysResult({ days: [...canonical.slice(0, -1), { lead_days: 8, score: 50 }] })
  assert.deepEqual([missing.error, duplicate.error, outOfRange.error], ['missing_lead', 'duplicate_lead', 'out_of_range_lead'])
  assert.deepEqual(missing.days, []); assert.deepEqual(duplicate.days, []); assert.deepEqual(outOfRange.days, [])
})

test('banners: synthetic / stale / expired / not initialised / unavailable are never silent', () => {
  assert.equal(bannerFor({ state: 'fresh', is_synthetic: true }), 'synthetic')
  assert.equal(bannerFor({ state: 'fresh' }), null)
  assert.equal(bannerFor({ state: 'stale' }), 'stale')
  assert.equal(bannerFor({ state: 'fallback' }), 'stale')
  assert.equal(bannerFor({ state: 'fresh', served_from: 'last_good.json' }), 'stale')
  assert.equal(bannerFor({ state: 'expired' }), 'expired')
  assert.equal(bannerFor({ state: 'not_initialized' }), 'notInitialized')
  assert.equal(bannerFor({ state: 'unavailable' }), 'unavailable')
  assert.equal(bannerFor({ state: 'no_data' }), 'noData')
  assert.equal(bannerFor({ state: 'fresh', timeline_invalid: true }), 'invalidData')
  for (const b of ['synthetic', 'stale', 'expired', 'notInitialized', 'unavailable', 'noData', 'invalidData']) {
    for (const lang of ['ar', 'en']) assert.equal(DAILY_COPY[lang].banners[b].length, 2)
  }
})

test('loaders degrade to explicit states when the API is offline, missing, or has no model', async () => {
  const offline = async () => { throw new Error('network down') }
  assert.equal((await loadDailyStatus(offline)).state, 'unavailable')
  assert.equal((await loadDailyCell('C1', offline)).state, 'unavailable')
  const notFound = async () => ({ ok: false, status: 404, json: async () => ({}) })
  assert.equal((await loadDailyCell('C1', notFound)).state, 'no_data')
  const noModel = async () => ({ ok: false, status: 503, json: async () => ({}) })
  assert.equal((await loadDailyCell('C1', noModel)).state, 'not_initialized')
  const ok = async (url) => ({ ok: true, status: 200, json: async () => ({ state: 'fresh', url }) })
  const r = await loadDailyCell('a b/c', ok)
  assert.ok(r.url.endsWith('/daily/cells/a%20b%2Fc'))
})

test('all public formatters preserve missing values instead of converting them to zero', () => {
  for (const missing of [null, undefined, '', '   ']) {
    assert.equal(formatScore(missing), 'N/A')
    assert.equal(formatAnomaly(missing), 'N/A')
    assert.equal(formatDecimal(missing), '—')
    assert.equal(formatPercent(missing), '—')
    assert.equal(formatCount(missing), '—')
  }
  assert.equal(formatScore(0), '0')
  assert.equal(formatScore(69.9), '69.9')
})

test('date label is timezone-stable and locale-aware', () => {
  assert.match(formatDayLabel('2026-10-06', 'en-GB'), /6/)
  assert.equal(formatDayLabel(null, 'en-GB'), '—')
  assert.notEqual(formatDayLabel('2026-10-06', 'ar-JO'), formatDayLabel('2026-10-06', 'en-GB'))
})

test('component never labels delayed data as live and states the score is not a probability', () => {
  const src = readFileSync(new URL('../src/components/DailyForecast.jsx', import.meta.url), 'utf8')
  assert.ok(!/real[- ]time|live/i.test(src.replace(/\/\/.*$/gm, '')), 'no live/real-time wording in component code')
  for (const lang of ['ar', 'en']) assert.ok(/(probab|احتمال)/i.test(DAILY_COPY[lang].intro))
})

test('national summary requires all eight leads and preserves real zero counts', () => {
  const leads = Object.fromEntries(DAILY_LEADS.map((lead) => [lead, {
    date: `2026-10-${String(lead + 6).padStart(2, '0')}`,
    Low: lead === 0 ? 0 : 1,
    Moderate: 1,
    High: lead === 7 ? 2 : 0,
    mean_score: lead === 0 ? null : 55.4,
  }]))
  const result = normalizeSummaryResult({ leads })
  assert.equal(result.valid, true)
  const rows = result.rows
  assert.deepEqual(rows.map((r) => r.lead), DAILY_LEADS)
  assert.equal(rows[0].low, 0); assert.equal(rows[0].meanScore, null)
  assert.equal(rows[7].total, 4); assert.equal(rows[7].share.high, 0.5); assert.equal(rows[7].meanScore, 55.4); assert.equal(rows[7].meanLevel, 'Moderate')
  assert.deepEqual(summaryRows({ state: 'unavailable', leads: {} }), [])
  assert.deepEqual(summaryRows(null), [])
  const missingLead = { ...leads }; delete missingLead[7]
  assert.equal(normalizeSummaryResult({ leads: missingLead }).valid, false)
  const missingCount = structuredClone(leads); delete missingCount[3].High
  assert.equal(normalizeSummaryResult({ leads: missingCount }).error, 'missing_counts')
  assert.deepEqual(summaryRows({ leads: missingCount }), [])
})
test('national component keys exist in both languages', () => {
  for (const k of ['nat.eyebrow', 'nat.title', 'nat.mean', 'nat.note', 'nat.level.High', 'nat.age']) for (const l of ['ar', 'en']) assert.notEqual(dt(l, k), k)
})

test('provenance normalisation exposes retrieval, source and fallback fields', () => {
  const p = dailyProvenance({
    issued_at: '2026-10-06T03:00:00Z',
    issue_day: '2026-10-06',
    served_from: 'last_good.json',
    freshness: {
      forecast_reference_time: '2026-10-06T00:00:00Z',
      forecast_fetched_at: '2026-10-06T03:01:00Z',
      forecast_provider: 'ECMWF IFS',
      latest_observation_date: '2026-10-01',
      observation_source: 'ERA5-Land',
      satellite_source: 'MODIS',
      last_successful_update: '2026-10-06T03:02:00Z',
    },
  })
  assert.equal(p.forecastProvider, 'ECMWF IFS')
  assert.equal(p.forecastRetrievedAt, '2026-10-06T03:01:00Z')
  assert.equal(p.observationSource, 'ERA5-Land')
  assert.equal(p.lastSuccessfulUpdate, '2026-10-06T03:02:00Z')
  assert.equal(p.isFallback, true)
})

test('GeoJSON signature changes for equal-size horizon, score, filter and geometry changes', () => {
  const feature = (id, horizon, score, x = 36) => ({
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [x, 31] },
    properties: { cell_id: id, horizon_days: horizon, risk_score: score, risk_level: 'Moderate' },
  })
  const base = { type: 'FeatureCollection', features: [feature('a', 16, 50)] }
  const variants = [
    { type: 'FeatureCollection', features: [feature('a', 32, 50)] },
    { type: 'FeatureCollection', features: [feature('a', 16, 51)] },
    { type: 'FeatureCollection', features: [feature('b', 16, 50)] },
    { type: 'FeatureCollection', features: [feature('a', 16, 50, 37)] },
  ]
  const signature = featureCollectionSignature(base)
  for (const variant of variants) assert.notEqual(featureCollectionSignature(variant), signature)
})

test('dashboard fallback is coherent and never mixes API cells with bundle metadata', () => {
  const fulfilled = (value) => ({ status: 'fulfilled', value })
  const rejected = { status: 'rejected', reason: new Error('offline') }
  const api = { id: 'api' }, bundleCells = { id: 'bundle' }
  const bundle = {
    cells: { 16: bundleCells }, areas: { 16: { id: 'bundle-area' } },
    metrics: { id: 'bundle-metrics' }, metadata: { id: 'bundle-meta' },
  }
  const selected = chooseDashboardInputs({
    cellsResult: fulfilled(api), areaResult: rejected,
    metricsResult: fulfilled({ id: 'api-metrics' }), metadataResult: fulfilled({ id: 'api-meta' }),
  }, bundle, 16)
  assert.equal(selected.source, 'bundle')
  assert.equal(selected.rawCells, bundleCells)
  assert.equal(selected.rawMetadata.id, 'bundle-meta')

  const complete = chooseDashboardInputs({
    cellsResult: fulfilled(api), areaResult: fulfilled({}), metricsResult: fulfilled({}), metadataResult: fulfilled({}),
  }, bundle, 16)
  assert.equal(complete.source, 'api')
  assert.equal(complete.rawCells, api)
})

test('cell deep-link horizon is applied once and does not undo a user toggle', () => {
  const initial = resolveDeepLinkedHorizon('16', 32, null)
  assert.deepEqual(initial, { applied: 16, next: 16 })

  // The URL still contains horizon=16 after the user deliberately selects +32.
  const afterUserToggle = resolveDeepLinkedHorizon('16', 32, initial.applied)
  assert.deepEqual(afterUserToggle, { applied: 16, next: null })

  // Leaving the query behind resets the guard so a later deep-link is applied again.
  const withoutQuery = resolveDeepLinkedHorizon(null, 32, afterUserToggle.applied)
  assert.deepEqual(withoutQuery, { applied: null, next: null })
  assert.deepEqual(resolveDeepLinkedHorizon('16', 32, withoutQuery.applied), { applied: 16, next: 16 })
})
