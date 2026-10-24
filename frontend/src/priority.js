// National-priority ranking. Mirrors backend/app/priority.py exactly.
// Derived ordering of the existing historical risk_score; never changes it.
// Not a probability and not a field diagnosis.

export const PRIORITY_BANDS = [
  [1, 'Top 1%'],
  [5, 'Top 5%'],
  [10, 'Top 10%'],
]
export const REMAINING_BAND = 'Remaining'

const valid = (score) => typeof score === 'number' && Number.isFinite(score)

export function priorityBand(atOrAbove, total) {
  for (const [pct, label] of PRIORITY_BANDS) if (atOrAbove * 100 <= pct * total) return label
  return REMAINING_BAND
}

export function median(values) {
  const sorted = values.filter(valid).sort((a, b) => a - b)
  if (!sorted.length) return null
  const mid = Math.floor(sorted.length / 2)
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2
}

// Positive half-up rounding using integer arithmetic, matching backend/app/priority.py.
export function priorityPercent(atOrAbove, total) {
  if (!Number.isInteger(atOrAbove) || !Number.isInteger(total) || atOrAbove < 0 || total <= 0) return null
  const numerator = atOrAbove * 10000
  return Math.floor((2 * numerator + total) / (2 * total)) / 100
}

// Python-style Unicode code-point ordering; avoids locale-dependent tie order.
export function compareCellIds(leftValue, rightValue) {
  const left = Array.from(String(leftValue), (character) => character.codePointAt(0))
  const right = Array.from(String(rightValue), (character) => character.codePointAt(0))
  const length = Math.min(left.length, right.length)
  for (let index = 0; index < length; index += 1) {
    if (left[index] !== right[index]) return left[index] - right[index]
  }
  return left.length - right.length
}

// Takes plain property objects, returns new objects (same order) with rank fields.
export function addNationalPriority(items) {
  const scores = items.map((i) => i.risk_score).filter(valid).sort((a, b) => b - a)
  const total = scores.length
  const med = median(scores)
  const first = new Map()
  const last = new Map()
  scores.forEach((s, i) => {
    if (!first.has(s)) first.set(s, i)
    last.set(s, i)
  })
  return items.map((item) => {
    const score = item.risk_score
    if (valid(score) && total) {
      const atOrAbove = last.get(score) + 1
      return {
        ...item,
        national_priority_rank: first.get(score) + 1,
        national_priority_total: total,
        national_priority_percentile: priorityPercent(atOrAbove, total),
        national_priority_tied_count: atOrAbove - first.get(score),
        priority_band: priorityBand(atOrAbove, total),
        national_median_score: med,
      }
    }
    return {
      ...item,
      national_priority_rank: null,
      national_priority_total: total || null,
      national_priority_percentile: null,
      national_priority_tied_count: null,
      priority_band: null,
      national_median_score: med,
    }
  })
}

const BAND_ORDER = PRIORITY_BANDS.map(([, label]) => label)

// Mirrors backend select_priority(): deterministic order by rank, then cell_id.
// band = null -> all ranked cells. Returns { rows, selection } where selection
// reports how the limit cutoff was applied (competition-ranking ties).
export function selectPriority(properties, { band = null, limit = null, includeCutoffTies = false } = {}) {
  let ranked = properties.filter((p) => p.national_priority_rank != null)
  if (band) {
    const bandIndex = BAND_ORDER.indexOf(band)
    if (bandIndex < 0) throw new RangeError(`Unknown priority band: ${band}`)
    const keep = BAND_ORDER.slice(0, bandIndex + 1)
    ranked = ranked.filter((p) => keep.includes(p.priority_band))
  }
  ranked.sort((a, b) => a.national_priority_rank - b.national_priority_rank || compareCellIds(a.cell_id, b.cell_id))
  if (limit !== null && (!Number.isInteger(limit) || limit < 0)) {
    throw new RangeError('Priority limit must be a non-negative integer')
  }

  let rows = limit === null || limit >= ranked.length ? ranked : ranked.slice(0, limit)
  const cutoffRank = rows.length ? rows[rows.length - 1].national_priority_rank : null
  if (includeCutoffTies && limit !== null && rows.length && rows.length < ranked.length) {
    rows = ranked.filter((p) => p.national_priority_rank <= cutoffRank)
  }
  const groupSize = cutoffRank === null ? 0 : ranked.filter((p) => p.national_priority_rank === cutoffRank).length
  const included = cutoffRank === null ? 0 : rows.filter((p) => p.national_priority_rank === cutoffRank).length
  return {
    rows,
    selection: {
      requested_limit: limit,
      include_cutoff_ties: includeCutoffTies,
      returned_count: rows.length,
      cutoff_rank: cutoffRank,
      cutoff_tie_group_size: groupSize,
      cutoff_ties_included: included,
      cutoff_ties_omitted: groupSize - included,
      cutoff_tie_group_split: groupSize - included > 0,
      extra_cells_beyond_limit: limit === null ? 0 : Math.max(rows.length - limit, 0),
    },
  }
}

export function topPriority(properties, { band = null, limit = null, includeCutoffTies = false } = {}) {
  return selectPriority(properties, { band, limit, includeCutoffTies }).rows
}

export const SCOPE_BAND = { band1: 'Top 1%', band5: 'Top 5%', band10: 'Top 10%' }

// Rows for the Explorer list. scope: top10 | band1 | band5 | band10 | all; sort: rank | score.
export function selectPriorityRows(properties, scope, sort) {
  const band = SCOPE_BAND[scope] ?? null
  const rows =
    scope === 'top10'
      ? topPriority(properties, { band, limit: 10, includeCutoffTies: true })
      : topPriority(properties, { band })
  if (sort === 'score') {
    return [...rows].sort((a, b) => b.risk_score - a.risk_score || a.national_priority_rank - b.national_priority_rank || compareCellIds(a.cell_id, b.cell_id))
  }
  return rows
}
