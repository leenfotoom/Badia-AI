import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { cellLocation, cellLocationLabel } from '../src/location.js'

test('precomputed full labels are selected by language without geocoding', () => {
  const properties = {
    location_label_ar: 'عمّان — محافظة عمّان',
    location_label_en: 'Amman — Amman Governorate',
    cell_id: 'C315',
  }
  assert.equal(cellLocationLabel(properties, 'ar'), 'عمّان — محافظة عمّان')
  assert.equal(cellLocationLabel(properties, 'en'), 'Amman — Amman Governorate')
  assert.equal(cellLocationLabel(properties, 'fr'), 'Amman — Amman Governorate')
})

test('formatter composes only supplied locality/region and governorate names', () => {
  const urban = {
    locality_ar: 'جرش', locality_en: 'Jerash',
    governorate_ar: 'محافظة جرش', governorate_en: 'Jerash Governorate',
  }
  assert.equal(cellLocationLabel(urban, 'ar'), 'جرش — محافظة جرش')
  assert.equal(cellLocationLabel(urban, 'en'), 'Jerash — Jerash Governorate')

  const remote = {
    region_ar: 'البادية الشرقية', region_en: 'Eastern Badia',
    governorate_ar: 'محافظة المفرق', governorate_en: 'Mafraq Governorate',
    location_kind: 'region',
  }
  assert.equal(cellLocation(remote, 'ar').label, 'البادية الشرقية — محافظة المفرق')
  assert.equal(cellLocation(remote, 'en').label, 'Eastern Badia — Mafraq Governorate')
  assert.equal(cellLocation(remote, 'en').kind, 'region')
})

test('nested local mapping schema and explicit missing state are supported', () => {
  const nested = {
    location: {
      kind: 'locality',
      ar: { label: 'العقبة — محافظة العقبة', governorate: 'محافظة العقبة' },
      en: { label: 'Aqaba — Aqaba Governorate', governorate: 'Aqaba Governorate' },
    },
  }
  assert.equal(cellLocationLabel(nested, 'ar'), 'العقبة — محافظة العقبة')
  assert.equal(cellLocationLabel(nested, 'en'), 'Aqaba — Aqaba Governorate')
  assert.equal(cellLocationLabel({}, 'en'), null)
})

test('real offline mapping covers all 968 cells and requested reference areas', () => {
  const mapping = JSON.parse(readFileSync(new URL('../../data/cell_locations.json', import.meta.url), 'utf8'))
  const entries = Object.entries(mapping.cells)
  assert.equal(mapping.cell_count, 968)
  assert.equal(entries.length, 968)
  assert.ok(entries.every(([cellId, value]) => cellId && value.governorate_ar && value.governorate_en))
  assert.ok(entries.every(([, value]) => value.location_label_ar && value.location_label_en))

  const localities = new Set(entries.map(([, value]) => value.locality_en).filter(Boolean))
  for (const place of ['Amman', 'Jerash', 'Irbid', 'Mafraq', 'Aqaba', 'Karak', 'Tafileh']) {
    assert.ok(localities.has(place), `${place} has a coordinate-derived cell label`)
  }
  assert.ok(entries.some(([, value]) => (
    value.location_kind === 'broad_region'
    && value.location_label_en === 'Eastern Badia — Mafraq Governorate'
    && value.location_label_ar === 'البادية الشرقية — محافظة المفرق'
  )), 'remote eastern Badia cells use a broad region instead of a false city claim')
})

test('both offline +16/+32 collections embed the canonical bilingual mapping', () => {
  const mapping = JSON.parse(readFileSync(new URL('../../data/cell_locations.json', import.meta.url), 'utf8')).cells
  const bundle = JSON.parse(readFileSync(new URL('../public/demo-data.json', import.meta.url), 'utf8'))
  for (const horizon of ['16', '32']) {
    const features = bundle.cells[horizon].features
    assert.equal(features.length, 968)
    for (const feature of features) {
      const properties = feature.properties
      const expected = mapping[properties.cell_id]
      assert.ok(expected, `mapped ${horizon}-day cell ${properties.cell_id}`)
      assert.equal(properties.location_label_ar, expected.location_label_ar)
      assert.equal(properties.location_label_en, expected.location_label_en)
      assert.equal(properties.governorate_ar, expected.governorate_ar)
      assert.equal(properties.governorate_en, expected.governorate_en)
    }
  }
})

test('selected-cell UI makes location primary and keeps cell ID secondary', () => {
  const ui = readFileSync(new URL('../src/components/UI.jsx', import.meta.url), 'utf8')
  const map = readFileSync(new URL('../src/components/RiskMap.jsx', import.meta.url), 'utf8')
  const details = readFileSync(new URL('../src/pages/CellDetails.jsx', import.meta.url), 'utf8')
  const i18n = readFileSync(new URL('../src/i18n.jsx', import.meta.url), 'utf8')

  assert.match(ui, /cell-location[\s\S]*cell\.location[\s\S]*<h2>\{location\}<\/h2>[\s\S]*cell\.id/)
  assert.match(map, /cellLocationLabel\(properties, language\)[\s\S]*cellId\.textContent/)
  assert.match(map, /key=\{`\$\{dataSignature\}-\$\{selectedId \|\| 'none'\}-\$\{language\}`\}/)
  assert.match(details, /<h1>\{location \?\? cellId\}<\/h1>[\s\S]*cell-page__cell-id/)
  assert.match(i18n, /location: 'الموقع'/)
  assert.match(i18n, /location: 'Location'/)
})
