import React from 'react'
import Icon from './Icons.jsx'
import { formatCount, formatDecimal } from '../format.js'
import { useLanguage } from '../i18n.jsx'
import { PRIORITY_COPY, fill } from '../priorityCopy.js'

const BAND_CLASS = { 'Top 1%': 'band-1', 'Top 5%': 'band-5', 'Top 10%': 'band-10', Remaining: 'band-rest' }

export function BandPill({ band }) {
  const { language } = useLanguage()
  if (!band) return null
  return <span className={`band-pill ${BAND_CLASS[band] ?? ''}`}>{PRIORITY_COPY[language].bands[band] ?? band}</span>
}

// Builds the "why" sentences only from real fields of the cell.
export function whyLines(p, c, featureLabel, qualityLabel, locale = 'en-GB') {
  if (p.national_priority_rank == null) return [c.notRanked]
  const lines = [
    p.priority_band !== 'Remaining'
      ? fill(c.whyHigh, { band: c.bands[p.priority_band], total: formatCount(p.national_priority_total, locale) })
      : fill(c.whyOther, { rank: formatCount(p.national_priority_rank, locale), total: formatCount(p.national_priority_total, locale) }),
  ]
  if (Number.isFinite(p.national_median_score)) {
    const diff = p.risk_score - p.national_median_score
    const dir = Math.abs(diff) < 0.05 ? c.equal : diff > 0 ? c.above : c.below
    lines.push(fill(c.whyMedian, { score: formatDecimal(p.risk_score, 1), dir, median: formatDecimal(p.national_median_score, 1) }))
  }
  const factor = p.top_factors?.[0]
  if (factor) lines.push(fill(c.whyFactor, { factor: featureLabel(factor.feature, factor.display_name) }))
  if (p.national_priority_tied_count > 1) lines.push(fill(c.whyTies, { n: formatCount(p.national_priority_tied_count, locale) }))
  const status = p.data_quality?.status
  if (status && status !== 'Good') lines.push(fill(c.whyQuality, { quality: qualityLabel(status) }))
  lines.push(c.whyLimit)
  return lines
}

export default function PriorityInfo({ properties: p, compact = false }) {
  const { language, locale, t, featureLabel } = useLanguage()
  const c = PRIORITY_COPY[language]
  const ranked = p.national_priority_rank != null
  const hasMedian = ranked && Number.isFinite(p.national_median_score)
  const diff = hasMedian ? p.risk_score - p.national_median_score : null
  const dir = diff == null ? '' : Math.abs(diff) < 0.05 ? c.equal : diff > 0 ? c.above : c.below
  const lines = whyLines(p, c, featureLabel, (s) => t(`quality.${s}`), locale)
  return (
    <section className={`priority-info ${compact ? 'priority-info--compact' : ''}`} aria-label={c.priorityTitle}>
      <div className="priority-info__block priority-info__block--severity">
        <span className="eyebrow">{c.severityTitle}</span>
        <p>{c.severityNote}</p>
      </div>
      <div className="priority-info__block priority-info__block--rank">
        <span className="eyebrow">{c.priorityTitle}</span>
        {ranked ? (
          <>
            <strong className="priority-info__rank">{fill(c.rankLine, { rank: formatCount(p.national_priority_rank, locale), total: formatCount(p.national_priority_total, locale) })}</strong>
            <div className="priority-info__chips">
              <span>{c.bandLabel}:</span> <BandPill band={p.priority_band} />
              <small>{fill(c.topShare, { value: formatDecimal(p.national_priority_percentile, 2).replace(/\.?0+$/, '') })}</small>
            </div>
            {hasMedian && <p className="priority-info__median"><Icon name="chart" size={15} /> {fill(c.vsMedian, { score: formatDecimal(p.risk_score, 1), median: formatDecimal(p.national_median_score, 1), diff: formatDecimal(Math.abs(diff), 1), dir })}</p>}
          </>
        ) : <p>{c.notRanked}</p>}
        <p className="priority-info__note">{c.priorityNote}</p>
      </div>
      <div className="priority-info__why">
        <strong>{c.whyTitle}</strong>
        <ul>{lines.map((line) => <li key={line}>{line}</li>)}</ul>
      </div>
    </section>
  )
}

export function NationalContextNote({ summary }) {
  const { language, locale } = useLanguage()
  const c = PRIORITY_COPY[language]
  const total = summary?.available_cells
  const high = summary?.high_count
  return (
    <aside className="panel-callout national-context" aria-label={c.ctxTitle}>
      <Icon name="info" size={19} />
      <div>
        <strong>{c.ctxTitle}</strong>
        {Number.isFinite(total) && total > 0 && Number.isFinite(high) && <p>{fill(c.ctxCount, { high: formatCount(high, locale), total: formatCount(total, locale) })}</p>}
        <ul><li>{c.ctx1}</li><li>{c.ctx2}</li><li>{c.ctx3}</li><li>{c.ctx4}</li></ul>
      </div>
    </aside>
  )
}
