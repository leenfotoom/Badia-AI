// Simplified from Natural Earth 1:110m Admin-0 Countries (public domain).
// Source: https://www.naturalearthdata.com/downloads/110m-cultural-vectors/
// Keeping the geographic coordinates here lets the illustration and its data
// dots share one projection instead of approximating Jordan with a freehand SVG.
export const JORDAN_BOUNDARY = Object.freeze([
  [35.545665, 32.393992],
  [35.719918, 32.709192],
  [36.834062, 32.312938],
  [38.792341, 33.378686],
  [39.195468, 32.161009],
  [39.004886, 32.010217],
  [37.002166, 31.508413],
  [37.998849, 30.5085],
  [37.66812, 30.338665],
  [37.503582, 30.003776],
  [36.740528, 29.865283],
  [36.501214, 29.505254],
  [36.068941, 29.197495],
  [34.956037, 29.356555],
  [34.922603, 29.501326],
  [35.420918, 31.100066],
  [35.397561, 31.489086],
  [35.545252, 31.782505],
])

export const JORDAN_VIEWBOX = Object.freeze({ width: 280, height: 340 })

const BOUNDS = Object.freeze({
  minLon: 34.82,
  maxLon: 39.3,
  minLat: 29.1,
  maxLat: 33.48,
})
const PADDING = 9
const MID_LATITUDE_RADIANS = ((BOUNDS.minLat + BOUNDS.maxLat) / 2) * Math.PI / 180
const LONGITUDE_SCALE = Math.cos(MID_LATITUDE_RADIANS)
const projectedWidth = (BOUNDS.maxLon - BOUNDS.minLon) * LONGITUDE_SCALE
const projectedHeight = BOUNDS.maxLat - BOUNDS.minLat
const scale = Math.min(
  (JORDAN_VIEWBOX.width - PADDING * 2) / projectedWidth,
  (JORDAN_VIEWBOX.height - PADDING * 2) / projectedHeight,
)
const renderedWidth = projectedWidth * scale
const renderedHeight = projectedHeight * scale
const offsetX = (JORDAN_VIEWBOX.width - renderedWidth) / 2
const offsetY = (JORDAN_VIEWBOX.height - renderedHeight) / 2

export function projectJordanPoint(lon, lat) {
  const longitude = Number(lon)
  const latitude = Number(lat)
  if (!Number.isFinite(longitude) || !Number.isFinite(latitude)) return null
  return [
    offsetX + (longitude - BOUNDS.minLon) * LONGITUDE_SCALE * scale,
    offsetY + (BOUNDS.maxLat - latitude) * scale,
  ]
}

export const JORDAN_PATH = `${JORDAN_BOUNDARY.map(([lon, lat], index) => {
  const [x, y] = projectJordanPoint(lon, lat)
  return `${index ? 'L' : 'M'}${x.toFixed(2)} ${y.toFixed(2)}`
}).join(' ')} Z`

export function representativeJordanFeatures(features, count = 25) {
  const valid = (Array.isArray(features) ? features : []).filter(({ properties = {} }) => (
    properties.lon !== null && properties.lon !== ''
    && properties.lat !== null && properties.lat !== ''
    && Number.isFinite(Number(properties.lon)) && Number.isFinite(Number(properties.lat))
  ))
  const sampleSize = Math.max(0, Math.min(valid.length, Math.floor(count)))
  if (!sampleSize) return []
  if (sampleSize === 1) return [valid[Math.floor(valid.length / 2)]]
  if (valid.length <= sampleSize) return valid
  return Array.from({ length: sampleSize }, (_, index) => (
    valid[Math.round(index * (valid.length - 1) / (sampleSize - 1))]
  ))
}
