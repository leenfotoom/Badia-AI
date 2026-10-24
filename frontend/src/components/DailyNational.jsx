import React, { useEffect, useState } from 'react'
import { useLanguage } from '../i18n.jsx'
import { dt } from '../dailyCopy.js'
import {
  bannerFor,
  dailyProvenance,
  formatDayLabel,
  formatIssued,
  loadDailyStatus,
  loadDailySummary,
  normalizeSummaryResult,
} from '../daily.js'

export default function DailyNational() {
  const { language, locale } = useLanguage()
  const T = (k, v) => dt(language, k, v)
  const [st, setSt] = useState({ loading: true, summary: null, status: null })
  useEffect(() => {
    let active = true
    Promise.all([loadDailySummary(), loadDailyStatus()]).then(([summary, status]) => active && setSt({ loading: false, summary, status }))
    return () => { active = false }
  }, [])
  if (st.loading) return null
  const state = st.summary?.state === 'unavailable' ? 'unavailable' : st.status?.state ?? st.summary?.state
  const timeline = normalizeSummaryResult(st.summary)
  const stateAllowsTimeline = !['not_initialized', 'unavailable', 'no_data'].includes(state)
  const banner = bannerFor({
    state,
    is_synthetic: st.summary?.is_synthetic ?? st.status?.is_synthetic,
    timeline_invalid: stateAllowsTimeline && !timeline.valid,
  })
  const rows = timeline.rows
  const provenance = dailyProvenance({
    ...(st.status ?? {}),
    ...(st.summary ?? {}),
    freshness: { ...(st.status?.freshness ?? {}), ...(st.summary?.freshness ?? {}) },
  })
  const leadLabel = (lead) => (lead === 0 ? T('today') : T('plusDay', { n: lead }))
  const servedLabel = provenance.isFallback ? T('servedFallback') : T('servedLatest')
  return (
    <section className="section-shell daily-national" aria-labelledby="daily-national-title">
      <span className="eyebrow">{T('nat.eyebrow')}</span>
      <h2 id="daily-national-title">{T('nat.title')}</h2>
      {banner && <div className={`daily-banner daily-banner--${banner}`} role="status"><strong>{T(`banners.${banner}.0`)}</strong> <span>{T(`banners.${banner}.1`)}</span></div>}
      {rows.length > 0 && (
        <>
          <ul className="daily-national__rows">
            {rows.map((r) => (
              <li key={r.lead}>
                <span className="daily-national__day">{leadLabel(r.lead)} <small>{formatDayLabel(r.date, locale)}</small></span>
                <span className="daily-national__bar" role="img" aria-label={`${T('nat.level.Low')} ${r.low}, ${T('nat.level.Moderate')} ${r.moderate}, ${T('nat.level.High')} ${r.high}`}>
                  <i className="lvl-low" style={{ width: `${r.share.low * 100}%` }} /><i className="lvl-moderate" style={{ width: `${r.share.moderate * 100}%` }} /><i className="lvl-high" style={{ width: `${r.share.high * 100}%` }} />
                </span>
                <span className="daily-national__mean">{T('nat.mean')}: <b dir="ltr">{r.meanScore ?? '—'}</b></span>
                <span className="daily-national__high">{T('nat.level.High')}: <b dir="ltr">{r.high}</b></span>
              </li>
            ))}
          </ul>
          <p className="card-footnote">
            {T('issued')}: {formatIssued(provenance.snapshotGeneratedAt, locale)}
            {st.status?.snapshot_age_hours != null && ` · ${T('nat.age', { h: st.status.snapshot_age_hours })}`}
            {provenance.lastSuccessfulUpdate && ` · ${T('lastSuccess')}: ${formatIssued(provenance.lastSuccessfulUpdate, locale)}`}
            {provenance.servedFrom && <> · {T('servedFrom')}: {servedLabel} <span dir="ltr">({provenance.servedFrom})</span></>}
            {' · '}{T('nat.note')}
          </p>
        </>
      )}
    </section>
  )
}
