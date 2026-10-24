import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const css = readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8')
const token = (name) => css.match(new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})`))[1]

const lum = (hex) => {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4))
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}
const ratio = (a, b) => {
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

test('red text token meets 4.5:1 on every surface it is used on', () => {
  for (const surface of ['night', 'night-2', 'panel', 'panel-2']) {
    assert.ok(ratio(token('high-text'), token(surface)) >= 4.5, `high-text on ${surface}`)
  }
  assert.match(css, /\.summary-card--danger strong \{ color: var\(--high-text\)/)
  assert.match(css, /\.limits-list__no > span \{ color: var\(--high-text\)/)
})

test('risk-level colours themselves are untouched', () => {
  assert.equal(token('high'), '#e05a4f')
  assert.equal(token('moderate'), '#e0ad50')
  assert.equal(token('low'), '#5cad7d')
})

test('step numerals are no longer near-invisible (alpha >= .6)', () => {
  const alphas = [...css.matchAll(/(?:method-card__number|pipeline-grid article > b|role-grid article > b)[^{]*\{[^}]*color:\s*rgba\(217,\s*175,\s*114,\s*([.\d]+)\)/g)].map((m) => Number(m[1]))
  assert.ok(alphas.length >= 2)
  assert.ok(alphas.every((a) => a >= 0.6), `alphas: ${alphas}`)
})

test('RTL priority row values align to the column header side', () => {
  assert.match(css, /\[dir="rtl"\] \.priority-row__rank,[\s\S]*?\[dir="rtl"\] \.priority-row__score \{ text-align: right; \}/)
})

test('text links and breadcrumbs keep a 24px minimum target', () => {
  assert.match(css, /\.text-link, \.page-breadcrumbs a \{ min-height: 24px; \}/)
})

test('desktop explorer workspace is height-capped so the map stays in view', () => {
  assert.match(css, /@media \(min-width: 921px\) \{\s*\.explorer-workspace \{ height: clamp\(690px, calc\(100vh - 110px\), 820px\); \}/)
})

test('cell search shows a visible focus ring on its container', () => {
  assert.match(css, /\.map-search input \{[^}]*outline: 0/)
  assert.match(css, /\.map-search:focus-within \{ outline: 2px solid var\(--sand\)/)
})

test('priority row label describes the real action (show on map), not "open details"', () => {
  const copy = readFileSync(new URL('../src/priorityCopy.js', import.meta.url), 'utf8')
  assert.match(copy, /score \{score\}, show on map/)
  assert.match(copy, /اعرضها على الخريطة/)
  assert.doesNotMatch(copy, /open details|افتح التفاصيل/)
})

test('home illustration uses Jordan geography for both outline and risk dots', async () => {
  const { JORDAN_BOUNDARY, JORDAN_PATH, projectJordanPoint, representativeJordanFeatures } = await import('../src/jordanSilhouette.js')
  const landing = readFileSync(new URL('../src/pages/Landing.jsx', import.meta.url), 'utf8')

  assert.ok(JORDAN_BOUNDARY.length >= 18, 'recognizable country boundary has sufficient vertices')
  assert.match(JORDAN_PATH, /^M[\d.]+ [\d.]+ L/)
  assert.match(landing, /clipPath="url\(#jordan-clip\)"/)
  assert.match(landing, /projectJordanPoint\(properties\.lon, properties\.lat\)/)
  assert.doesNotMatch(landing, /<MapContainer|from ['"]react-leaflet/)

  const aqaba = projectJordanPoint(35, 29.5)
  const irbid = projectJordanPoint(35.85, 32.55)
  const easternBadia = projectJordanPoint(38.8, 32.2)
  assert.ok(aqaba[1] > irbid[1], 'south projects below north')
  assert.ok(easternBadia[0] > irbid[0], 'east projects right of west')

  const features = Array.from({ length: 100 }, (_, i) => ({ properties: { cell_id: i, lon: 35 + i / 30, lat: 29.3 + i / 35 } }))
  const sampled = representativeJordanFeatures(features, 25)
  assert.equal(sampled.length, 25)
  assert.equal(sampled[0], features[0])
  assert.equal(sampled.at(-1), features.at(-1))
})
