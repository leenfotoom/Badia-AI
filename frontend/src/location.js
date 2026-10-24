const clean = (value) => (typeof value === 'string' && value.trim() ? value.trim() : null)

function first(...values) {
  for (const value of values) {
    const cleaned = clean(value)
    if (cleaned) return cleaned
  }
  return null
}

function localized(properties, key, language) {
  const safeLanguage = language === 'ar' ? 'ar' : 'en'
  const location = properties?.location
  const languageBlock = location && typeof location === 'object' ? location[safeLanguage] : null

  return first(
    properties?.[`${key}_${safeLanguage}`],
    properties?.[`${key}_name_${safeLanguage}`],
    location?.[`${key}_${safeLanguage}`],
    languageBlock && typeof languageBlock === 'object' ? languageBlock[key] : null,
  )
}

/**
 * Resolve the locally precomputed bilingual label attached to a grid cell.
 *
 * The formatter deliberately does no geocoding and never derives a place name
 * from coordinates in the browser. That keeps clicks instant/offline and avoids
 * presenting a guessed city. A prepared full label wins; otherwise only the
 * supplied locality/region and governorate fields are joined.
 */
export function cellLocation(properties, language = 'en') {
  const safeLanguage = language === 'ar' ? 'ar' : 'en'
  const location = properties?.location
  const languageBlock = location && typeof location === 'object' ? location[safeLanguage] : null
  const label = first(
    properties?.[`location_label_${safeLanguage}`],
    properties?.[`location_${safeLanguage}`],
    location?.[`label_${safeLanguage}`],
    languageBlock && typeof languageBlock === 'object' ? languageBlock.label : null,
    typeof languageBlock === 'string' ? languageBlock : null,
  )
  const locality = localized(properties, 'locality', safeLanguage)
  const region = localized(properties, 'region', safeLanguage)
  const governorate = localized(properties, 'governorate', safeLanguage)
  const primary = locality ?? region
  const composed = primary && governorate && primary !== governorate
    ? `${primary} — ${governorate}`
    : primary ?? governorate

  return {
    label: label ?? composed ?? null,
    locality,
    region,
    governorate,
    kind: first(properties?.location_kind, location?.kind),
  }
}

export function cellLocationLabel(properties, language = 'en') {
  return cellLocation(properties, language).label
}
