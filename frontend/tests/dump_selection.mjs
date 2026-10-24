// Prints JS-computed Top-N selection metadata for the bundled offline data
// (used by the backend API-vs-offline consistency test).
import { readFileSync } from 'node:fs'
import { addNationalPriority, selectPriority } from '../src/priority.js'
const bundle = JSON.parse(readFileSync(new URL('../public/demo-data.json', import.meta.url)))
const out = {}
for (const h of ['16', '32']) {
  const props = addNationalPriority(
    bundle.cells[h].features.map((f) => ({ cell_id: f.properties.cell_id, risk_score: f.properties.risk_score })),
  )
  out[h] = {}
  for (const [limit, ties] of [[10, false], [10, true], [25, true], [1, true]]) {
    const { rows, selection } = selectPriority(props, { limit, includeCutoffTies: ties })
    out[h][`${limit}-${ties}`] = { ids: rows.map((r) => r.cell_id), selection }
  }
}
console.log(JSON.stringify(out))
