// Prints JS-computed ranks for the bundled offline data (used by backend consistency test).
import { readFileSync } from 'node:fs'
import { addNationalPriority } from '../src/priority.js'
const bundle = JSON.parse(readFileSync(new URL('../public/demo-data.json', import.meta.url)))
const out = {}
for (const h of ['16', '32']) {
  const props = bundle.cells[h].features.map((f) => ({ cell_id: f.properties.cell_id, risk_score: f.properties.risk_score }))
  out[h] = Object.fromEntries(addNationalPriority(props).map((p) => [p.cell_id, [p.national_priority_rank, p.national_priority_percentile, p.priority_band]]))
}
console.log(JSON.stringify(out))
