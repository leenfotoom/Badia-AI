import React, { useEffect, useMemo, useState } from 'react'
import Icon from './Icons.jsx'
import { formatCount, formatDecimal } from '../format.js'
import { useLanguage } from '../i18n.jsx'
import { PRIORITY_COPY, fill } from '../priorityCopy.js'
import { selectPriorityRows } from '../priority.js'

const SCOPES = ['top10', 'band1', 'band5', 'band10', 'all']
const PAGE = 50

export default function PriorityList({ properties, rankedTotal, selectedId, onSelect, onJump, horizon }) {
  const { language, locale, t } = useLanguage()
  const c = PRIORITY_COPY[language]
  const [scope, setScope] = useState('top10')
  const [sort, setSort] = useState('rank')
  const [limit, setLimit] = useState(PAGE)

  useEffect(() => {
    setScope('top10')
    setSort('rank')
    setLimit(PAGE)
  }, [horizon])
  useEffect(() => setLimit(PAGE), [scope, sort])

  const rows = useMemo(() => selectPriorityRows(properties, scope, sort), [properties, scope, sort])
  const visible = scope === 'all' || rows.length > PAGE ? rows.slice(0, limit) : rows
  const qualityLabel = (p) => t(`quality.${p.data_quality?.status || 'Not reported'}`)
  const handleListKeys = (event) => {
    if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return
    const buttons = [...event.currentTarget.querySelectorAll('button.priority-row')]
    const current = buttons.indexOf(document.activeElement)
    if (current < 0 || !buttons.length) return
    event.preventDefault()
    const next = event.key === 'Home'
      ? 0
      : event.key === 'End'
        ? buttons.length - 1
        : event.key === 'ArrowDown'
          ? Math.min(current + 1, buttons.length - 1)
          : Math.max(current - 1, 0)
    buttons[next]?.focus()
  }

  return (
    <section className="priority-section section-shell" aria-labelledby="priority-title">
      <div className="priority-head">
        <div>
          <h2 id="priority-title">{c.listTitle}</h2>
          <p>{c.listIntro}</p>
        </div>
        <button className="button button--primary priority-jump" type="button" onClick={onJump} disabled={!rankedTotal}>
          <Icon name="location" size={17} /> {c.jump}
        </button>
      </div>
      <div className="priority-controls">
        <div className="filter-row" role="group" aria-label={c.scopeLabel}>
          {SCOPES.map((key) => (
            <button type="button" key={key} className={scope === key ? 'is-active' : ''} aria-pressed={scope === key} onClick={() => setScope(key)}>{c.scope[key]}</button>
          ))}
        </div>
        <div className="filter-row" role="group" aria-label={c.sortLabel}>
          <span className="priority-sort-label">{c.sortLabel}</span>
          {['rank', 'score'].map((key) => (
            <button type="button" key={key} className={sort === key ? 'is-active' : ''} aria-pressed={sort === key} onClick={() => setSort(key)}>{key === 'rank' ? c.sortRank : c.sortScore}</button>
          ))}
        </div>
      </div>
      {!rankedTotal ? <p className="muted-copy" role="status">{c.noRanked}</p> : !rows.length ? <p className="muted-copy" role="status">{c.noMatch}</p> : (
        <>
          <div className="priority-table" role="region" aria-labelledby="priority-title">
            <div className="priority-row priority-row--head" aria-hidden="true">
              <span>{c.colRank}</span><span>{c.colCell}</span><span>{c.colScore}</span><span>{c.colQuality}</span><span>{c.colHorizon}</span>
            </div>
            <ol className="priority-rows" aria-label={c.listAria} onKeyDown={handleListKeys}>
              {visible.map((p) => {
                const selected = selectedId === p.cell_id
                return (
                  <li key={p.cell_id}>
                    <button
                      type="button"
                      className={`priority-row ${selected ? 'is-selected' : ''}`}
                      aria-pressed={selected}
                      aria-label={fill(c.rowAria, {
                        rank: formatCount(p.national_priority_rank, locale),
                        cell: p.cell_id,
                        score: formatDecimal(p.risk_score, 1),
                      })}
                      onClick={() => onSelect(p.cell_id)}
                    >
                      <b className="priority-row__rank" dir="ltr">#{formatCount(p.national_priority_rank, locale)}</b>
                      <span className="priority-row__cell" dir="ltr">{p.cell_id}</span>
                      <span className="priority-row__score" dir="ltr">{formatDecimal(p.risk_score, 1)}<small>/100</small></span>
                      <span className="priority-row__quality">{qualityLabel(p)}</span>
                      <span className="priority-row__horizon">{t('horizon.days', { value: p.horizon_days })}</span>
                    </button>
                  </li>
                )
              })}
            </ol>
          </div>
          <div className="priority-foot">
            <small>{fill(c.showing, {
              shown: formatCount(visible.length, locale),
              matching: formatCount(rows.length, locale),
              total: formatCount(rankedTotal, locale),
            })} · {c.filtersApply}</small>
            {visible.length < rows.length && <button className="text-button" type="button" onClick={() => setLimit((v) => v + PAGE)}>{c.more}</button>}
          </div>
        </>
      )}
    </section>
  )
}
