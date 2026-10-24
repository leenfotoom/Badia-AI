function finiteNumber(value) {
  if (value === null || value === undefined) return null
  if (typeof value === 'string' && value.trim() === '') return null
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

export function formatScore(value, fallback = 'N/A') {
  const number = finiteNumber(value)
  // Risk bands are evaluated on the unrounded score. Preserve that value so a
  // displayed 70 can never sit beside a Moderate label derived from 69.9.
  return number === null ? fallback : String(number)
}

export function formatAnomaly(value) {
  const number = finiteNumber(value)
  if (number === null) return 'N/A'
  return `${number > 0 ? '+' : ''}${number.toFixed(4)}`
}

export function formatDecimal(value, digits = 4) {
  const number = finiteNumber(value)
  return number === null ? '—' : number.toFixed(digits)
}

export function formatPercent(value, digits = 1) {
  const number = finiteNumber(value)
  return number === null ? '—' : `${number.toFixed(digits)}%`
}

export function formatCount(value, locale = 'en-GB') {
  const number = finiteNumber(value)
  return number === null ? '—' : new Intl.NumberFormat(locale).format(number)
}

export function formatDate(value, locale = 'en-GB') {
  if (!value) return null
  const date = new Date(`${value}T00:00:00`)
  if (Number.isNaN(date.getTime())) return String(value)
  return new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'short', year: 'numeric' }).format(date)
}

export function displayFeatureName(value) {
  return String(value ?? 'Factor')
    .replaceAll('_', ' ')
    .replace(/\b\w/g, (character) => character.toUpperCase())
}

export function metricFor(metrics, horizon) {
  return metrics?.horizons?.[String(horizon)] ?? metrics?.horizons?.[horizon] ?? null
}
