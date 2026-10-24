const SUPPORTED_HORIZONS = new Set([16, 32])

export function resolveDeepLinkedHorizon(rawRequested, currentHorizon, lastApplied) {
  const requested = rawRequested == null ? null : Number(rawRequested)

  if (!SUPPORTED_HORIZONS.has(requested)) {
    return { applied: null, next: null }
  }
  if (lastApplied === requested) {
    return { applied: lastApplied, next: null }
  }
  return {
    applied: requested,
    next: requested === currentHorizon ? null : requested,
  }
}
