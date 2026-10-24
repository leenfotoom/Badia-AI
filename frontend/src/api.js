import { addNationalPriority } from './priority.js'
import { API_BASE, DEFAULT_METADATA, PUBLISHED_METRICS } from './constants.js'

const TIMEOUT_MS = 6500
let demoBundlePromise

function cleanLevel(value, score) {
  if (!Number.isFinite(score)) return 'N/A'
  const raw = value == null ? '' : String(value).trim().toLowerCase()
  if (raw === 'low') return 'Low'
  if (raw === 'moderate' || raw === 'medium') return 'Moderate'
  if (raw === 'high') return 'High'
  if (raw === 'n/a' || raw === 'na' || raw === 'unknown') return 'N/A'
  if (score < 40) return 'Low'
  if (score < 70) return 'Moderate'
  return 'High'
}

function parseMaybeJson(value, fallback) {
  if (value == null || value === '') return fallback
  if (typeof value === 'object') return value
  try {
    return JSON.parse(value)
  } catch {
    return fallback
  }
}

function geometryCenter(geometry) {
  if (!geometry?.coordinates) return {}
  if (geometry.type === 'Point') {
    return { lon: Number(geometry.coordinates[0]), lat: Number(geometry.coordinates[1]) }
  }
  const points = geometry.type === 'Polygon' ? geometry.coordinates.flat(1) : geometry.coordinates.flat(2)
  if (!points.length) return {}
  const sums = points.reduce(
    (acc, coordinate) => ({ lon: acc.lon + Number(coordinate[0]), lat: acc.lat + Number(coordinate[1]) }),
    { lon: 0, lat: 0 },
  )
  return { lon: sums.lon / points.length, lat: sums.lat / points.length }
}

function normalizeTopFactors(raw) {
  const parsed = parseMaybeJson(raw, raw)
  if (Array.isArray(parsed)) {
    return parsed.slice(0, 5).map((item) => {
      if (typeof item === 'string') return { feature: item, display_name: item }
      return {
        feature: item.feature ?? item.name ?? item.display_name ?? 'Feature',
        display_name: item.display_name ?? item.label ?? item.feature ?? item.name ?? 'Feature',
        value: item.value ?? item.feature_value ?? item.importance,
        direction: item.direction ?? item.effect,
      }
    })
  }
  return []
}

function normalizeQuality(raw, properties = {}) {
  const parsed = parseMaybeJson(raw, {})
  if (typeof parsed === 'string') return { status: parsed, completeness_pct: null, missing_fields: [] }
  return {
    status: parsed.status ?? properties.data_quality_status ?? properties.quality_status ?? 'Not reported',
    completeness_pct:
      parsed.completeness_pct ?? properties.completeness_pct ?? properties.data_completeness_pct ?? null,
    missing_fields: parsed.missing_fields ?? properties.missing_fields ?? [],
  }
}

export function normalizeFeature(item, horizon) {
  const isFeature = item?.type === 'Feature'
  const sourceProperties = isFeature ? item.properties ?? {} : item ?? {}
  const geometry = isFeature
    ? item.geometry
    : item.geometry ??
      (sourceProperties.lon != null || sourceProperties.lng != null
        ? {
            type: 'Point',
            coordinates: [Number(sourceProperties.lon ?? sourceProperties.lng), Number(sourceProperties.lat)],
          }
        : null)
  const center = geometryCenter(geometry)
  const lat = Number(sourceProperties.lat ?? sourceProperties.latitude ?? center.lat)
  const lon = Number(sourceProperties.lon ?? sourceProperties.lng ?? sourceProperties.longitude ?? center.lon)
  const scoreValue = sourceProperties.risk_score ?? sourceProperties.score
  const riskScore = scoreValue == null || scoreValue === '' ? null : Number(scoreValue)
  const anomalyValue =
    sourceProperties.predicted_anomaly ?? sourceProperties.prediction ?? sourceProperties.y_pred ?? sourceProperties.anomaly_prediction

  const properties = {
    ...sourceProperties,
    cell_id: String(sourceProperties.cell_id ?? sourceProperties.id ?? sourceProperties.grid_id ?? 'unknown'),
    lat: Number.isFinite(lat) ? lat : null,
    lon: Number.isFinite(lon) ? lon : null,
    horizon_days: Number(sourceProperties.horizon_days ?? sourceProperties.horizon ?? horizon),
    predicted_anomaly: anomalyValue == null ? null : Number(anomalyValue),
    risk_score: riskScore,
    risk_level: cleanLevel(sourceProperties.risk_level ?? sourceProperties.level ?? sourceProperties.category, riskScore),
    snapshot_date: sourceProperties.snapshot_date ?? sourceProperties.date ?? null,
    snapshot_label: sourceProperties.snapshot_label ?? sourceProperties.temporal_label ?? null,
    top_factors: normalizeTopFactors(sourceProperties.top_factors ?? sourceProperties.factors),
    data_quality: normalizeQuality(sourceProperties.data_quality, sourceProperties),
  }

  return { type: 'Feature', geometry, properties }
}

export function normalizeFeatureCollection(raw, horizon) {
  const items = raw?.type === 'FeatureCollection' ? raw.features : raw?.features ?? raw?.cells ?? raw?.data ?? raw
  const features = Array.isArray(items) ? items.map((item) => normalizeFeature(item, horizon)) : []
  // Re-derive the complete priority fields from the normalized scores for both
  // sources. This makes old/incomplete API responses behave exactly like the
  // bundled offline snapshot without changing any scientific source value.
  const enriched = addNationalPriority(features.map((f) => f.properties))
  return { type: 'FeatureCollection', features: features.map((f, i) => ({ ...f, properties: enriched[i] })) }
}

function summarize(features) {
  const values = features.map((feature) => feature.properties).filter(Boolean)
  const available = values.filter((item) => Number.isFinite(item.risk_score))
  const count = (level) => values.filter((item) => item.risk_level === level).length
  return {
    total_cells: values.length,
    available_cells: available.length,
    mean_risk_score: available.length
      ? available.reduce((total, item) => total + item.risk_score, 0) / available.length
      : null,
    high_count: count('High'),
    moderate_count: count('Moderate'),
    low_count: count('Low'),
    na_count: count('N/A'),
  }
}

export function normalizeArea(raw, horizon, cells) {
  const source = raw?.national_summary ?? raw?.area ?? raw ?? {}
  const summary = source.summary ?? source
  const computed = summarize(cells.features)
  return {
    ...source,
    horizon_days: Number(source.horizon_days ?? horizon),
    snapshot_date: source.snapshot_date ?? cells.features[0]?.properties?.snapshot_date ?? null,
    snapshot_label:
      source.snapshot_label ?? cells.features[0]?.properties?.snapshot_label ?? 'Latest available historical demo',
    summary: {
      total_cells: summary.total_cells ?? computed.total_cells,
      available_cells: summary.available_cells ?? computed.available_cells,
      mean_risk_score: summary.mean_risk_score ?? computed.mean_risk_score,
      high_count: summary.high_count ?? computed.high_count,
      moderate_count: summary.moderate_count ?? computed.moderate_count,
      low_count: summary.low_count ?? computed.low_count,
      na_count: summary.na_count ?? computed.na_count,
    },
    levels: source.levels ?? {
      low: summary.low_count ?? computed.low_count,
      moderate: summary.moderate_count ?? computed.moderate_count,
      high: summary.high_count ?? computed.high_count,
      na: summary.na_count ?? computed.na_count,
    },
  }
}

async function requestJson(path) {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), TIMEOUT_MS)
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      headers: { Accept: 'application/json' },
      signal: controller.signal,
    })
    if (!response.ok) throw new Error(`Request failed (${response.status})`)
    return await response.json()
  } finally {
    window.clearTimeout(timer)
  }
}

async function loadDemoBundle() {
  if (!demoBundlePromise) {
    demoBundlePromise = fetch('/demo-data.json', { headers: { Accept: 'application/json' } }).then((response) => {
      if (!response.ok) throw new Error('Bundled demo data is not available')
      return response.json()
    })
  }
  return demoBundlePromise
}

function selectHorizon(bundle, key, horizon) {
  const collection = bundle?.[key]
  if (!collection) return null
  return collection[String(horizon)] ?? collection[horizon] ?? collection
}

export function chooseDashboardInputs(results, bundle, horizon) {
  const { cellsResult, areaResult, metricsResult, metadataResult } = results
  const allApi = [cellsResult, areaResult, metricsResult, metadataResult]
    .every((result) => result.status === 'fulfilled')

  if (allApi) {
    return {
      rawCells: cellsResult.value,
      rawArea: areaResult.value,
      rawMetrics: metricsResult.value,
      rawMetadata: metadataResult.value,
      source: 'api',
      apiAvailable: true,
      endpointSources: { cells: 'api', area: 'api', metrics: 'api', metadata: 'api' },
    }
  }

  // Use one coherent saved snapshot if any API endpoint failed. This avoids
  // silently combining current cells with a historical area or metadata file.
  if (bundle) {
    return {
      rawCells: selectHorizon(bundle, 'cells', horizon) ?? selectHorizon(bundle, 'geojson', horizon),
      rawArea: selectHorizon(bundle, 'areas', horizon) ?? selectHorizon(bundle, 'summaries', horizon),
      rawMetrics: bundle.metrics ?? bundle.evaluation ?? PUBLISHED_METRICS,
      rawMetadata: bundle.metadata ?? {},
      source: 'bundle',
      apiAvailable: false,
      endpointSources: { cells: 'bundle', area: 'bundle', metrics: 'bundle', metadata: 'bundle' },
    }
  }

  // The packaged bundle should normally make this unreachable. Retain any
  // independently available API values, but mark the result explicitly partial.
  const valueOrNull = (result) => (result.status === 'fulfilled' ? result.value : null)
  return {
    rawCells: valueOrNull(cellsResult),
    rawArea: valueOrNull(areaResult),
    rawMetrics: valueOrNull(metricsResult) ?? PUBLISHED_METRICS,
    rawMetadata: valueOrNull(metadataResult) ?? {},
    source: 'api-partial',
    apiAvailable: cellsResult.status === 'fulfilled',
    endpointSources: {
      cells: cellsResult.status === 'fulfilled' ? 'api' : 'unavailable',
      area: areaResult.status === 'fulfilled' ? 'api' : 'computed',
      metrics: metricsResult.status === 'fulfilled' ? 'api' : 'published-default',
      metadata: metadataResult.status === 'fulfilled' ? 'api' : 'published-default',
    },
  }
}

export async function loadDashboard(horizon) {
  const [cellsResult, areaResult, metricsResult, metadataResult] = await Promise.allSettled([
    requestJson(`/cells?horizon=${horizon}&format=geojson`),
    requestJson(`/areas?horizon=${horizon}`),
    requestJson('/metrics'),
    requestJson('/metadata'),
  ])

  let bundle = null
  const needsBundle = [cellsResult, areaResult, metricsResult, metadataResult].some((result) => result.status === 'rejected')
  if (needsBundle) {
    try {
      bundle = await loadDemoBundle()
    } catch {
      bundle = null
    }
  }

  const selected = chooseDashboardInputs(
    { cellsResult, areaResult, metricsResult, metadataResult },
    bundle,
    horizon,
  )
  const cells = normalizeFeatureCollection(selected.rawCells, horizon)

  if (!cells.features.length && cellsResult.status === 'rejected' && !bundle) {
    throw new Error('The API is offline and the bundled demo dataset could not be loaded.')
  }

  const area = normalizeArea(selected.rawArea, horizon, cells)
  const metrics = selected.rawMetrics
  const metadata = {
    ...DEFAULT_METADATA,
    ...(selected.rawMetadata ?? {}),
  }

  return {
    cells,
    area,
    metrics: metrics?.horizons ? metrics : PUBLISHED_METRICS,
    metadata,
    source: selected.source,
    apiAvailable: selected.apiAvailable,
    endpointSources: selected.endpointSources,
  }
}

export async function loadCell(cellId, horizon, localCells) {
  const local = localCells?.features?.find((feature) => feature.properties.cell_id === cellId) ?? null
  try {
    const raw = await requestJson(`/cells/${encodeURIComponent(cellId)}?horizon=${horizon}`)
    const normalized = normalizeFeature(raw?.feature ?? raw, horizon)
    if (!local) return normalized
    const localPriority = local.properties ?? {}
    return {
      ...normalized,
      geometry: normalized.geometry ?? local.geometry,
      properties: {
        ...normalized.properties,
        national_priority_rank: localPriority.national_priority_rank ?? normalized.properties.national_priority_rank ?? null,
        national_priority_total: localPriority.national_priority_total ?? normalized.properties.national_priority_total ?? null,
        national_priority_percentile:
          localPriority.national_priority_percentile ?? normalized.properties.national_priority_percentile ?? null,
        national_priority_tied_count:
          localPriority.national_priority_tied_count ?? normalized.properties.national_priority_tied_count ?? null,
        priority_band: localPriority.priority_band ?? normalized.properties.priority_band ?? null,
        national_median_score: localPriority.national_median_score ?? normalized.properties.national_median_score ?? null,
      },
    }
  } catch {
    return local
  }
}
