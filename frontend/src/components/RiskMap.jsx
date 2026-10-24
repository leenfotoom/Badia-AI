import React, { useEffect, useMemo, useRef, useState } from 'react'
import L from 'leaflet'
import { GeoJSON, MapContainer, Rectangle, TileLayer, ZoomControl, useMap } from 'react-leaflet'
import { JORDAN_BOUNDS, RISK_COLORS } from '../constants.js'
import { formatScore } from '../format.js'
import { useLanguage } from '../i18n.jsx'
import { cellLocationLabel } from '../location.js'
import { featureCollectionSignature } from '../mapData.js'
import { PRIORITY_COPY } from '../priorityCopy.js'

function MapFocus({ feature }) {
  const map = useMap()
  useEffect(() => {
    if (!feature?.geometry) return
    try {
      const layer = L.geoJSON(feature)
      const bounds = layer.getBounds()
      if (bounds.isValid()) map.fitBounds(bounds.pad(4), { maxZoom: 10, animate: false })
    } catch {
      // Keep the national view when a malformed optional geometry slips through.
    }
  }, [feature, map])
  return null
}

// Re-centres on a cell when the list / jump button asks for it (not on plain map clicks).
function FocusOnRequest({ feature, request }) {
  const map = useMap()
  useEffect(() => {
    if (!request || !feature?.geometry) return
    try {
      const center = L.geoJSON(feature).getBounds().getCenter()
      map.setView(center, Math.max(map.getZoom(), 9), { animate: false })
    } catch {
      // Ignore malformed optional geometry.
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [request?.n])
  return null
}

function featureStyle(feature, selectedId) {
  const properties = feature?.properties ?? {}
  const color = RISK_COLORS[properties.risk_level] ?? RISK_COLORS['N/A']
  const selected = properties.cell_id === selectedId
  return {
    color: selected ? '#ffffff' : '#101a31',
    fillColor: color,
    fillOpacity: selected ? 0.94 : 0.76,
    opacity: 1,
    weight: selected ? 2.8 : 1.1,
  }
}

export default function RiskMap({ collection, selectedId, onSelect, compact = false, focusRequest = null }) {
  const { t, riskLabel, language } = useLanguage()
  const [tilesFailed, setTilesFailed] = useState(() => typeof navigator !== 'undefined' && navigator.onLine === false)
  const failures = useRef(0)
  const safeCollection = useMemo(
    () => ({
      type: 'FeatureCollection',
      features: (collection?.features ?? []).filter((feature) => feature?.geometry?.coordinates),
    }),
    [collection],
  )
  const dataSignature = useMemo(() => featureCollectionSignature(safeCollection), [safeCollection])
  const selected = safeCollection.features.find((feature) => feature.properties?.cell_id === selectedId)
  const selectedLocation = selected
    ? cellLocationLabel(selected.properties, language) ?? t('cell.locationUnavailable')
    : null

  useEffect(() => {
    const handleOffline = () => setTilesFailed(true)
    const handleOnline = () => {
      failures.current = 0
      setTilesFailed(false)
    }
    window.addEventListener('offline', handleOffline)
    window.addEventListener('online', handleOnline)
    return () => {
      window.removeEventListener('offline', handleOffline)
      window.removeEventListener('online', handleOnline)
    }
  }, [])

  const onEachFeature = (feature, layer) => {
    const properties = feature.properties ?? {}
    const tooltip = document.createElement('div')
    const title = document.createElement('strong')
    const cellId = document.createElement('small')
    const detail = document.createElement('span')
    title.textContent = cellLocationLabel(properties, language) ?? t('cell.locationUnavailable')
    cellId.textContent = `${t('cell.id')}: ${properties.cell_id || '—'}`
    cellId.dir = 'auto'
    detail.textContent = `${riskLabel(properties.risk_level || 'N/A')} · ${formatScore(properties.risk_score)}/100`
    tooltip.append(title, cellId, detail)
    layer.bindTooltip(tooltip, { className: 'risk-tooltip', direction: 'top', offset: [0, -5] })
    layer.on('click', () => onSelect?.(feature))
  }

  return (
    <div className={`risk-map ${compact ? 'risk-map--compact' : ''} ${tilesFailed ? 'risk-map--no-tiles' : ''}`} role="region" aria-label={t('map.aria')}>
      <MapContainer
        bounds={JORDAN_BOUNDS}
        boundsOptions={{ padding: [18, 18] }}
        maxBounds={[[27.5, 32.8], [35.1, 41.2]]}
        minZoom={5}
        maxZoom={13}
        scrollWheelZoom
        zoomControl={false}
        preferCanvas
      >
        {tilesFailed && <Rectangle bounds={JORDAN_BOUNDS} pathOptions={{ color: '#d9af72', weight: 1, dashArray: '6 6', fillColor: '#2a241b', fillOpacity: 0.55, interactive: false }} />}
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          className="basemap-tiles"
          eventHandlers={{
            tileload: () => {
              failures.current = 0
              setTilesFailed(false)
            },
            tileerror: () => {
              failures.current += 1
              if (failures.current >= 3) setTilesFailed(true)
            },
          }}
        />
        <GeoJSON
          key={`${dataSignature}-${selectedId || 'none'}-${language}`}
          data={safeCollection}
          style={(feature) => featureStyle(feature, selectedId)}
          pointToLayer={(feature, latlng) =>
            L.circleMarker(latlng, {
              ...featureStyle(feature, selectedId),
              radius: feature.properties?.cell_id === selectedId ? 9 : compact ? 5 : 6.5,
            })
          }
          onEachFeature={onEachFeature}
        />
        {selected && (
          <>
            <GeoJSON
              key={`ring-${selectedId}`}
              data={selected}
              interactive={false}
              style={{ color: '#ffd34d', weight: 5, opacity: 1, fill: false }}
              pointToLayer={(_, latlng) => L.circleMarker(latlng, { radius: 12, color: '#ffd34d', weight: 4, fill: false, interactive: false })}
            />
            {Number.isFinite(selected.properties?.lat) && Number.isFinite(selected.properties?.lon) && (
              <GeoJSON
                key={`halo-${selectedId}`}
                data={{ type: 'Point', coordinates: [selected.properties.lon, selected.properties.lat] }}
                interactive={false}
                pointToLayer={(_, latlng) => L.circleMarker(latlng, { radius: 16, color: '#ffffff', weight: 2, dashArray: '3 4', fill: false, interactive: false })}
              />
            )}
          </>
        )}
        <ZoomControl position="bottomright" />
        {!compact && <FocusOnRequest feature={selected} request={focusRequest} />}
        {compact && selected && <MapFocus feature={selected} />}
      </MapContainer>
      <div className="map-grid-overlay" aria-hidden="true" />
      <span className="basemap-note">{t('map.offlineNote')}</span>
      {tilesFailed && <span className="basemap-failed" role="status">{PRIORITY_COPY[language].tilesFailed}</span>}
      {selected && (
        <span className="map-selected-chip" aria-live="polite">
          <strong>{selectedLocation}</strong>
          <small>{t('cell.id')} <b dir="ltr">{selectedId}</b></small>
        </span>
      )}
    </div>
  )
}
