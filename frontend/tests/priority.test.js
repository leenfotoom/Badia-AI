import test from 'node:test'
import assert from 'node:assert/strict'
import {
  addNationalPriority,
  compareCellIds,
  priorityBand,
  priorityPercent,
  selectPriority,
  selectPriorityRows,
  topPriority,
} from '../src/priority.js'
import { normalizeFeatureCollection } from '../src/api.js'

const mk = (scores) => scores.map((risk_score, i) => ({ cell_id: `c${i}`, risk_score }))

test('ranks, ties share best rank, nulls excluded', () => {
  const r = addNationalPriority(mk([90, 90, 80, null, 70]))
  assert.deepEqual(r.map((x) => x.national_priority_rank), [1, 1, 3, null, 4])
  assert.equal(r[0].national_priority_total, 4)
  assert.equal(r[3].priority_band, null)
  assert.equal(r[0].national_priority_tied_count, 2)
  assert.equal(r[0].national_median_score, 85)
  assert.equal(r[0].risk_score, 90)
})

test('band boundaries (tie-inclusive, integer math)', () => {
  assert.equal(priorityBand(1, 100), 'Top 1%')
  assert.equal(priorityBand(2, 100), 'Top 5%')
  assert.equal(priorityBand(5, 100), 'Top 5%')
  assert.equal(priorityBand(6, 100), 'Top 10%')
  assert.equal(priorityBand(10, 100), 'Top 10%')
  assert.equal(priorityBand(11, 100), 'Remaining')
})

test('priority percentile uses backend-compatible half-up rounding', () => {
  assert.equal(priorityPercent(1, 32), 3.13)
  assert.equal(priorityPercent(2, 32), 6.25)
  assert.equal(priorityPercent(0, 0), null)
})

test('cell ID tie-break follows code-point order, not locale collation', () => {
  const ids = ['a_1', 'a-2', 'a,3', 'a2']
  assert.deepEqual([...ids].sort(compareCellIds), ['a,3', 'a-2', 'a2', 'a_1'])
})

test('topPriority deterministic and band-filtered', () => {
  const scores = Array.from({ length: 100 }, (_, i) => 100 - i)
  const p = addNationalPriority(mk(scores))
  assert.equal(topPriority(p, { band: 'Top 5%' }).length, 5)
  assert.equal(topPriority(p, { limit: 10 })[0].cell_id, 'c0')
  assert.deepEqual(topPriority(p, { limit: 0 }), [])
  assert.throws(() => topPriority(p, { limit: -1 }), /non-negative integer/)
  assert.throws(() => topPriority(p, { band: 'Top 3%' }), /Unknown priority band/)
})

test('all-null input', () => {
  const r = addNationalPriority(mk([null, null]))
  assert.equal(r[0].national_priority_rank, null)
  assert.equal(r[0].national_median_score, null)
})

test('Top 10 scope keeps the full tie group at its cutoff', () => {
  const p = addNationalPriority(mk([100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 91, 91, 90]))
  const rows = selectPriorityRows(p, 'top10', 'rank')
  assert.equal(rows.length, 12)
  assert.ok(rows.slice(9).every((row) => row.national_priority_rank === 10))
})

test('API normalization replaces incomplete ranks with complete consistent fields', () => {
  const raw = {
    type: 'FeatureCollection',
    features: [
      { type: 'Feature', geometry: null, properties: { cell_id: 'b', risk_score: 80, national_priority_rank: 99 } },
      { type: 'Feature', geometry: null, properties: { cell_id: 'a', risk_score: 90 } },
      { type: 'Feature', geometry: null, properties: { cell_id: 'n', risk_score: null } },
    ],
  }
  const normalized = normalizeFeatureCollection(raw, 16).features.map((feature) => feature.properties)
  assert.deepEqual(normalized.map((item) => item.national_priority_rank), [2, 1, null])
  assert.equal(normalized[0].national_priority_total, 2)
  assert.equal(normalized[0].national_median_score, 85)
  assert.equal(normalized[2].national_priority_total, 2)
})

test('API normalization derives canonical levels only when a valid-score label is missing', () => {
  const raw = [
    { cell_id: 'low', risk_score: 39.9 },
    { cell_id: 'moderate-low', risk_score: 40 },
    { cell_id: 'moderate-high', risk_score: 69.9 },
    { cell_id: 'high', risk_score: 70 },
    { cell_id: 'explicit-na', risk_score: 90, risk_level: 'N/A' },
    { cell_id: 'no-score', risk_score: null, risk_level: 'High' },
  ]
  const levels = normalizeFeatureCollection(raw, 16).features.map((feature) => feature.properties.risk_level)
  assert.deepEqual(levels, ['Low', 'Moderate', 'Moderate', 'High', 'N/A', 'N/A'])
})

import { readFileSync } from 'node:fs'

for (const h of ['16', '32']) {
  test(`real offline bundle +${h}: scopes, sort, original scores untouched`, () => {
    const bundle = JSON.parse(readFileSync(new URL('../public/demo-data.json', import.meta.url)))
    const raw = bundle.cells[h].features.map((f) => ({ cell_id: f.properties.cell_id, risk_score: f.properties.risk_score }))
    const ranked = addNationalPriority(raw)
    assert.deepEqual(ranked.map((r) => r.risk_score), raw.map((r) => r.risk_score))
    const total = ranked.filter((r) => r.national_priority_rank != null).length
    assert.equal(total, 962)
    const top10 = selectPriorityRows(ranked, 'top10', 'rank')
    assert.ok(top10.length >= 10)
    assert.equal(top10[0].national_priority_rank, 1)
    const cutoffRank = top10[9].national_priority_rank
    assert.ok(top10.slice(9).every((row) => row.national_priority_rank === cutoffRank))
    for (const [scope, pct] of [['band1', 1], ['band5', 5], ['band10', 10]]) {
      const rows = selectPriorityRows(ranked, scope, 'rank')
      assert.ok(rows.length > 0 && rows.every((r) => (r.national_priority_percentile * total) / 100 <= (pct * total) / 100 + 1e-6))
    }
    const byScore = selectPriorityRows(ranked, 'all', 'score')
    assert.equal(byScore.length, total)
    assert.ok(byScore.every((r, i) => i === 0 || byScore[i - 1].risk_score >= r.risk_score))
  })
}

test('selectPriority reports a split tie group by default and none with includeCutoffTies', () => {
  const props = addNationalPriority(mk([100, 90, 80, 80, 80, 70]))
  const split = selectPriority(props, { limit: 4 })
  assert.deepEqual(split.rows.map((r) => r.cell_id), ['c0', 'c1', 'c2', 'c3'])
  assert.equal(split.selection.cutoff_rank, 3)
  assert.equal(split.selection.cutoff_tie_group_size, 3)
  assert.equal(split.selection.cutoff_ties_included, 2)
  assert.equal(split.selection.cutoff_ties_omitted, 1)
  assert.equal(split.selection.cutoff_tie_group_split, true)

  const whole = selectPriority(props, { limit: 4, includeCutoffTies: true })
  assert.deepEqual(whole.rows.map((r) => r.cell_id), ['c0', 'c1', 'c2', 'c3', 'c4'])
  assert.equal(whole.selection.cutoff_tie_group_split, false)
  assert.equal(whole.selection.extra_cells_beyond_limit, 1)
  assert.equal(whole.selection.returned_count, 5)
})

test('selectPriority edge cases: limit 0, no limit, limit beyond candidates, invalid limit', () => {
  const props = addNationalPriority(mk([100, 90, 80, 80, 80, 70]))
  const zero = selectPriority(props, { limit: 0, includeCutoffTies: true })
  assert.deepEqual(zero.rows, [])
  assert.equal(zero.selection.cutoff_rank, null)
  assert.equal(selectPriority(props).rows.length, 6)
  assert.equal(selectPriority(props).selection.requested_limit, null)
  const beyond = selectPriority(props, { limit: 50, includeCutoffTies: true })
  assert.equal(beyond.rows.length, 6)
  assert.equal(beyond.selection.cutoff_rank, 6)
  assert.throws(() => selectPriority(props, { limit: -1 }), RangeError)
  assert.throws(() => selectPriority(props, { limit: 1.5 }), RangeError)
})

test('selectPriorityRows top10 still equals topPriority limit 10 with cutoff ties', () => {
  const props = addNationalPriority(mk([100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 91, 91, 50]))
  const rows = selectPriorityRows(props, 'top10', 'rank')
  assert.equal(rows.length, 12)
  assert.deepEqual(rows, topPriority(props, { band: null, limit: 10, includeCutoffTies: true }))
})
