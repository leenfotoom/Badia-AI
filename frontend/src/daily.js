// Daily Environmental Stress Risk: data access + pure view-model helpers (no React, unit-testable).
import { API_BASE } from './constants.js'

const TIMEOUT_MS = 6500
export const DAILY_LEADS = Object.freeze([0, 1, 2, 3, 4, 5, 6, 7])
export const DAILY_STATES = ['fresh', 'stale', 'expired', 'fallback', 'not_initialized', 'unavailable', 'no_data']

const num = (v) => (v === null || v === undefined || v === '' ? NaN : Number(v))
const firstPresent = (...values) => values.find((value) => value !== null && value !== undefined && value !== '') ?? null

export function dailyLevel(score) {
  const s = num(score)
  if (!Number.isFinite(s)) return 'N/A'
  return s < 40 ? 'Low' : s < 70 ? 'Moderate' : 'High'
}

async function getJson(path, fetchImpl = globalThis.fetch) {
  const ctl = new AbortController()
  const timer = setTimeout(() => ctl.abort(), TIMEOUT_MS)
  try {
    const res = await fetchImpl(`${API_BASE}/daily${path}`, { signal: ctl.signal, headers: { Accept: 'application/json' } })
    if (!res.ok) {
      const error = new Error(`HTTP ${res.status}`)
      error.status = res.status
      throw error
    }
    return await res.json()
  } finally {
    clearTimeout(timer)
  }
}

/** Never throws: a missing/offline daily service becomes an explicit `unavailable` state (no fake data). */
export async function loadDailyStatus(fetchImpl) {
  try {
    return await getJson('/status', fetchImpl)
  } catch {
    return { state: 'unavailable' }
  }
}

export async function loadDailyCell(cellId, fetchImpl) {
  try {
    return await getJson(`/cells/${encodeURIComponent(cellId)}`, fetchImpl)
  } catch (error) {
    if (error?.status === 404) return { state: 'no_data' }
    if (error?.status === 503) return { state: 'not_initialized' }
    return { state: 'unavailable' }
  }
}

export async function loadDailySummary(fetchImpl) {
  try {
    return await getJson('/summary', fetchImpl)
  } catch {
    return { state: 'unavailable', leads: {} }
  }
}

/** One normalised day for rendering. Missing numbers stay null (rendered as "—"), never invented. */
export function normalizeDay(day) {
  if (!day) return null
  const score = num(day.score)
  const change = num(day.change_vs_today)
  const confidenceLevel = ['high', 'medium', 'low'].includes(day.confidence?.level)
    ? day.confidence.level
    : 'unknown'
  const confidenceParts = day.confidence?.components && typeof day.confidence.components === 'object'
    ? Object.fromEntries(
        Object.entries(day.confidence.components)
          .map(([key, value]) => [key, num(value)])
          .filter(([, value]) => Number.isFinite(value)),
      )
    : null
  return {
    lead: Number(day.lead_days),
    date: day.date ?? null,
    score: Number.isFinite(score) ? score : null,
    level: Number.isFinite(score) ? dailyLevel(score) : 'N/A',
    change: Number.isFinite(change) ? change : null,
    drivers: Array.isArray(day.drivers) ? day.drivers : [],
    offsets: Array.isArray(day.offsets) ? day.offsets : [],
    changeDrivers: Array.isArray(day.change_drivers) ? day.change_drivers : [],
    confidence: confidenceLevel,
    confidenceValue: Number.isFinite(num(day.confidence?.value)) ? num(day.confidence.value) : null,
    confidenceParts: confidenceParts && Object.keys(confidenceParts).length ? confidenceParts : null,
  }
}

export function normalizeDaysResult(cell) {
  if (!Array.isArray(cell?.days)) return { valid: false, error: 'missing_days', days: [] }
  const days = cell.days.map(normalizeDay).filter(Boolean)
  if (days.some((day) => !Number.isInteger(day.lead) || !DAILY_LEADS.includes(day.lead))) {
    return { valid: false, error: 'out_of_range_lead', days: [] }
  }
  const unique = new Set(days.map((day) => day.lead))
  if (unique.size !== days.length) return { valid: false, error: 'duplicate_lead', days: [] }
  if (days.length !== DAILY_LEADS.length || DAILY_LEADS.some((lead) => !unique.has(lead))) {
    return { valid: false, error: 'missing_lead', days: [] }
  }
  return { valid: true, error: null, days: days.sort((a, b) => a.lead - b.lead) }
}

export function normalizeDays(cell) {
  return normalizeDaysResult(cell).days
}

/** Which banner (if any) must be shown. Delayed/stale/synthetic data is never shown as plain live data. */
export function bannerFor(payload) {
  if (!payload) return null
  if (payload.timeline_invalid) return 'invalidData'
  if (payload.is_synthetic) return 'synthetic'
  const s = payload.state
  if (s === 'not_initialized') return 'notInitialized'
  if (s === 'unavailable') return 'unavailable'
  if (s === 'no_data') return 'noData'
  if (s === 'expired') return 'expired'
  const servedFrom = String(payload.served_from ?? payload.freshness?.served_from ?? '').toLowerCase()
  if (s === 'stale' || s === 'fallback' || servedFrom.includes('last_good')) return 'stale'
  return null
}

/** Dates are Amman-local calendar days from the backend; format without timezone shifts. */
export function formatDayLabel(dateStr, locale) {
  if (!dateStr) return '—'
  const d = new Date(`${dateStr}T12:00:00Z`)
  if (Number.isNaN(d.getTime())) return String(dateStr)
  return new Intl.DateTimeFormat(locale, { weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC' }).format(d)
}

export function formatIssued(iso, locale) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Amman' }).format(d)
}

/** Normalise optional provenance names while accepting older snapshot schemas. */
export function dailyProvenance(payload) {
  const freshness = payload?.freshness ?? {}
  const servedFrom = firstPresent(payload?.served_from, freshness.served_from)
  return {
    snapshotGeneratedAt: firstPresent(payload?.generated_at, payload?.issued_at),
    issueDay: firstPresent(payload?.issue_day, freshness.issue_day),
    forecastReferenceAt: firstPresent(
      freshness.forecast_reference_time,
      freshness.forecast_reference_at,
      freshness.forecast_issued_at,
      payload?.forecast_reference_time,
    ),
    forecastRetrievedAt: firstPresent(
      freshness.forecast_retrieved_at,
      freshness.forecast_fetched_at,
      freshness.retrieved_at,
    ),
    forecastProvider: firstPresent(
      freshness.forecast_provider,
      freshness.weather_provider,
      freshness.forecast_model,
    ),
    forecastAgeHours: firstPresent(freshness.forecast_age_hours, payload?.forecast_age_hours),
    observationDate: firstPresent(freshness.latest_observation_date, freshness.observation_date),
    observationRetrievedAt: firstPresent(
      freshness.observation_retrieved_at,
      freshness.observations_fetched_at,
      freshness.observation_fetched_at,
    ),
    observationSource: firstPresent(freshness.observation_source, freshness.observation_provider),
    satelliteDate: firstPresent(
      payload?.vegetation?.composite_end,
      freshness.latest_satellite_date,
      freshness.satellite_observation_date,
    ),
    satelliteRetrievedAt: firstPresent(freshness.satellite_retrieved_at, freshness.satellite_fetched_at),
    satelliteSource: firstPresent(freshness.satellite_source, freshness.satellite_provider),
    lastSuccessfulUpdate: firstPresent(
      payload?.last_successful_update,
      freshness.last_successful_update,
      freshness.last_success_at,
    ),
    servedFrom,
    isFallback: payload?.state === 'fallback' || String(servedFrom ?? '').toLowerCase().includes('last_good'),
  }
}

/** Reason keys emitted by backend/_reasons plus the group keys of change_drivers. */
export const REASON_KEYS = [
  'soil_moisture_below_normal', 'soil_moisture_state', 'recent_rain_low', 'recent_rain_state',
  'forecast_rain_low', 'forecast_rain_state', 'heat_elevated', 'heat_state',
  'air_dryness_elevated', 'air_dryness_state',
]
export const GROUP_KEYS = ['soil_moisture', 'recent_rain', 'forecast_rain', 'heat', 'dryness', 'air_dryness']

/** National summary -> ordered rows. Counts are passed through; shares derived only when cells > 0. */
const count = (value) => {
  const n = num(value)
  return Number.isInteger(n) && n >= 0 ? n : null
}

export function normalizeSummaryResult(summary) {
  const leads = summary?.leads ?? {}
  if (!leads || typeof leads !== 'object' || Array.isArray(leads)) {
    return { valid: false, error: 'missing_leads', rows: [] }
  }
  const rawKeys = Object.keys(leads)
  const numericKeys = rawKeys.map(Number)
  if (
    rawKeys.length !== DAILY_LEADS.length
    || numericKeys.some((lead) => !Number.isInteger(lead) || !DAILY_LEADS.includes(lead))
    || new Set(numericKeys).size !== DAILY_LEADS.length
    || DAILY_LEADS.some((lead) => !numericKeys.includes(lead))
  ) {
    return { valid: false, error: 'invalid_leads', rows: [] }
  }
  const rows = DAILY_LEADS.map((lead) => {
    const o = leads[String(lead)] ?? leads[lead]
    const low = count(o?.Low), moderate = count(o?.Moderate), high = count(o?.High)
    if (low === null || moderate === null || high === null) return null
    const total = low + moderate + high
    const mean = num(o?.mean_score)
    return {
      lead, date: o.date ?? null, low, moderate, high, total,
      meanScore: Number.isFinite(mean) ? mean : null,
      meanLevel: dailyLevel(mean),
      share: total > 0 ? { low: low / total, moderate: moderate / total, high: high / total } : { low: 0, moderate: 0, high: 0 },
    }
  })
  if (rows.some((row) => row === null)) return { valid: false, error: 'missing_counts', rows: [] }
  return { valid: true, error: null, rows }
}

export function summaryRows(summary) {
  return normalizeSummaryResult(summary).rows
}
