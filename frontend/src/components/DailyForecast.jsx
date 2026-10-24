import React, { useEffect, useState } from 'react'
import { useLanguage } from '../i18n.jsx'
import { dt } from '../dailyCopy.js'
import {
  bannerFor,
  dailyProvenance,
  formatDayLabel,
  formatIssued,
  loadDailyCell,
  loadDailyStatus,
  normalizeDaysResult,
} from '../daily.js'
import { RiskPill } from './UI.jsx'

function useDailyCell(cellId) {
  const [state, setState] = useState({ loading: true, payload: null })
  useEffect(() => {
    let active = true
    setState({ loading: true, payload: null })
    Promise.all([loadDailyCell(cellId), loadDailyStatus()]).then(([cell, status]) => {
      if (!active) return
      setState({
        loading: false,
        payload: {
          ...status,
          ...cell,
          freshness: { ...(status?.freshness ?? {}), ...(cell?.freshness ?? {}) },
        },
      })
    })
    return () => { active = false }
  }, [cellId])
  return state
}

function Reasons({ items, tone, lang }) {
  if (!items.length) return null
  return (
    <ul className={`daily-reasons daily-reasons--${tone}`}>
      {items.map((r) => <li key={r.key}>{dt(lang, `reasons.${r.key}`)}</li>)}
    </ul>
  )
}

export default function DailyForecast({ cellId }) {
  const { language, locale } = useLanguage()
  const { loading, payload } = useDailyCell(cellId)
  const [selectedLead, setSelectedLead] = useState(0)
  const T = (k, v) => dt(language, k, v)

  useEffect(() => setSelectedLead(0), [cellId])

  if (loading) return <section className="daily-card" aria-busy="true"><p>{T('loading')}</p></section>

  const timeline = normalizeDaysResult(payload)
  const days = timeline.days
  const stateAllowsTimeline = !['not_initialized', 'unavailable', 'no_data'].includes(payload?.state)
  const banner = bannerFor({ ...payload, timeline_invalid: stateAllowsTimeline && !timeline.valid })
  const bannerBlock = banner && (
    <div className={`daily-banner daily-banner--${banner}`} role="status">
      <strong>{T(`banners.${banner}.0`)}</strong> <span>{T(`banners.${banner}.1`)}</span>
    </div>
  )
  if (!days.length) {
    return <section className="daily-card"><header><span className="eyebrow">{T('eyebrow')}</span><h2>{T('title')}</h2></header>{bannerBlock}</section>
  }

  const day = days.find((item) => item.lead === selectedLead) ?? days[0]
  const provenance = dailyProvenance(payload)
  const veg = payload.vegetation
  const leadLabel = (lead) => (lead === 0 ? T('today') : T('plusDay', { n: lead }))
  const changeText = day.change == null ? '—' : day.change === 0 ? T('noChange') : `${day.change > 0 ? '+' : ''}${day.change}`
  const sourceLine = (...items) => items.filter((item) => item !== null && item !== undefined && item !== '').join(' · ') || '—'
  const servedLabel = provenance.isFallback ? T('servedFallback') : T('servedLatest')

  return (
    <section className="daily-card" aria-labelledby="daily-title">
      <header><span className="eyebrow">{T('eyebrow')}</span><h2 id="daily-title">{T('title')}</h2><p>{T('intro')}</p></header>
      {bannerBlock}

      <div className="daily-timeline" role="tablist" aria-label={T('title')}>
        {days.map((d) => (
          <button key={d.lead} role="tab" aria-selected={d.lead === day.lead} type="button"
            className={`daily-tab daily-tab--${d.level.toLowerCase().replace('/', '-')}${d.lead === day.lead ? ' is-active' : ''}`}
            onClick={() => setSelectedLead(d.lead)}>
            <span className="daily-tab__lead">{leadLabel(d.lead)}</span>
            <span className="daily-tab__date">{formatDayLabel(d.date, locale)}</span>
            <strong>{d.score ?? '—'}</strong>
          </button>
        ))}
      </div>

      <div className="daily-detail" role="tabpanel">
        <div className="daily-detail__score">
          <strong>{day.score ?? '—'}</strong><span>{T('outOf')}</span>
          <RiskPill level={day.level} />
        </div>
        <p className="daily-detail__change">{T('changeVsToday')}: <b dir="ltr">{changeText}</b></p>

        <h3>{T('whyTitle')}</h3>
        {day.drivers.length || day.offsets.length ? (
          <div className="daily-why">
            {day.drivers.length > 0 && <div><span>{T('raises')}</span><Reasons items={day.drivers} tone="up" lang={language} /></div>}
            {day.offsets.length > 0 && <div><span>{T('lowers')}</span><Reasons items={day.offsets} tone="down" lang={language} /></div>}
          </div>
        ) : <p>{T('noReasons')}</p>}
        {day.changeDrivers.length > 0 && (
          <p className="daily-changewhy">{T('changeWhy')}: {day.changeDrivers.map((c) => `${T(`groups.${c.group}`)} (${c.delta > 0 ? '+' : ''}${c.delta})`).join(' · ')}</p>
        )}
        <p className="card-footnote">{T('whyNote')}</p>

        <div className={`daily-confidence daily-confidence--${day.confidence}`}>
          <span>{T('confidence')}</span><strong>{T(`conf.${day.confidence}`)}</strong>
          {day.confidenceParts && (
            <ul>{Object.entries(day.confidenceParts).map(([k, v]) => <li key={k}>{T(`confParts.${k}`)}: <b dir="ltr">{Math.round(v * 100)}%</b></li>)}</ul>
          )}
        </div>
      </div>

      <dl className="daily-sources">
        <div><dt>{T('issued')}</dt><dd>{formatIssued(provenance.snapshotGeneratedAt, locale)}</dd></div>
        {provenance.issueDay && <div><dt>{T('issueDay')}</dt><dd dir="ltr">{provenance.issueDay}</dd></div>}
        {provenance.forecastReferenceAt && <div><dt>{T('forecastReference')}</dt><dd>{formatIssued(provenance.forecastReferenceAt, locale)}</dd></div>}
        <div><dt>{T('weatherSrc')}</dt><dd>{sourceLine(provenance.forecastProvider, provenance.forecastAgeHours == null ? null : T('weatherAge', { h: provenance.forecastAgeHours }))}{provenance.forecastRetrievedAt && <small>{T('retrieved')}: {formatIssued(provenance.forecastRetrievedAt, locale)}</small>}</dd></div>
        <div><dt>{T('obsSrc')}</dt><dd>{sourceLine(provenance.observationDate, provenance.observationSource)}<small>{T('obsNote')}</small>{provenance.observationRetrievedAt && <small>{T('retrieved')}: {formatIssued(provenance.observationRetrievedAt, locale)}</small>}</dd></div>
        <div><dt>{T('satSrc')}</dt><dd>{sourceLine(provenance.satelliteDate ?? T('satNone'), provenance.satelliteSource)}<small>{T('satNote')}</small>{provenance.satelliteRetrievedAt && <small>{T('retrieved')}: {formatIssued(provenance.satelliteRetrievedAt, locale)}</small>}</dd></div>
        <div><dt>{T('model')}</dt><dd dir="ltr">{payload.model?.version ?? '—'}</dd></div>
        {provenance.lastSuccessfulUpdate && <div><dt>{T('lastSuccess')}</dt><dd>{formatIssued(provenance.lastSuccessfulUpdate, locale)}</dd></div>}
        {provenance.servedFrom && <div><dt>{T('servedFrom')}</dt><dd>{servedLabel} <small dir="ltr">{provenance.servedFrom}</small></dd></div>}
      </dl>

      {veg && (
        <p className="daily-veg"><b>{T('veg')}:</b> {T(`vegState.${veg.state}`)} <small>{T('vegNote')}</small></p>
      )}
    </section>
  )
}
