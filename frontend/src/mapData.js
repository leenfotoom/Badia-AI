// React-Leaflet's GeoJSON `data` prop is immutable after layer creation.
// A deterministic content fingerprint lets callers remount the layer whenever
// a horizon, filter result, score, or geometry changes—even if the cell count
// happens to stay the same.
export function featureCollectionSignature(collection) {
  let hash = 2166136261
  const update = (value) => {
    const text = String(value ?? '')
    for (let i = 0; i < text.length; i += 1) {
      hash ^= text.charCodeAt(i)
      hash = Math.imul(hash, 16777619)
    }
  }

  const features = collection?.features ?? []
  for (const feature of features) {
    const properties = feature?.properties ?? {}
    update(properties.cell_id)
    update(properties.horizon_days)
    update(properties.risk_score)
    update(properties.risk_level)
    update(feature?.geometry?.type)
    update(JSON.stringify(feature?.geometry?.coordinates ?? null))
  }
  return `${features.length}-${(hash >>> 0).toString(36)}`
}
