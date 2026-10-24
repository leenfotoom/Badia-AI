import React, { useCallback, useEffect, useMemo, useState } from 'react'
import ActionGuidance from '../components/ActionGuidance.jsx'
import RiskMap from '../components/RiskMap.jsx'
import PriorityList from '../components/PriorityList.jsx'
import { NationalContextNote } from '../components/PriorityInfo.jsx'
import { topPriority } from '../priority.js'
import { PRIORITY_COPY } from '../priorityCopy.js'
import Icon from '../components/Icons.jsx'
import DailyNational from '../components/DailyNational.jsx'
import {
  CellSnapshot,
  EmptyState,
  ErrorState,
  HorizonToggle,
  LoadingState,
  MetricComparison,
  RiskLegend,
  SnapshotBadge,
  SourceNotice,
  SummaryCards,
} from '../components/UI.jsx'
import { formatCount } from '../format.js'
import { useLanguage } from '../i18n.jsx'

const FILTERS = ['All', 'Low', 'Moderate', 'High', 'N/A']
const COPY = {
  ar: {
    kicker: 'خريطة أولوية المتابعة',
    title: 'وين نبدأ المتابعة؟',
    intro: 'اختر الفترة، اقرأ اللون، ثم افتح الخلية لتعرف ما الذي يجب التحقق منه على الأرض.',
    search: 'ابحث برقم الخلية…',
    searchLabel: 'البحث عن خلية برقمها',
    filterLabel: 'تصفية الخلايا حسب مستوى الإشارة',
    cells: 'خلية',
    clear: 'إلغاء التصفية',
    legend: 'مؤشر الشدة التاريخية',
    notProbability: '0–100 مؤشر نسبي، وليس احتمالًا',
    national: 'ملخص الأردن',
    jordan: 'الأردن',
    nationalText: 'ملخص سريع للخلايا المتاحة في هذه اللقطة التاريخية.',
    distribution: 'توزيع مستويات المتابعة',
    total: 'الإجمالي',
    howTitle: 'كيف تستخدم الخريطة؟',
    howText: 'اضغط على خلية، راجع الدرجة وجودة البيانات، ثم اتبع خطوة التحقق المقترحة. لا تتخذ قرار ري من اللون وحده.',
    modelTitle: 'هل النموذج أفضل من بقاء الحالة كما هي؟',
    selectedAria: 'تفاصيل الخلية المختارة',
    nationalAria: 'ملخص الأردن',
    close: 'إغلاق تفاصيل الخلية',
    disclaimerTitle: 'ماذا تعرض الخريطة؟',
    disclaimer: 'إشارة نسبية للإجهاد النباتي مشتقة من الأقمار الصناعية مقارنة بالموسم التاريخي. ليست تشخيص تصحر، ولا حقيقة ميدانية، ولا تفسيرًا سببيًا، ولا توقعًا حيًا.',
  },
  en: {
    kicker: 'Follow-up priority map',
    title: 'Where should follow-up begin?',
    intro: 'Choose a look-ahead period, read the colour, then open a cell to see what should be verified on the ground.',
    search: 'Find a cell ID…',
    searchLabel: 'Find a cell by ID',
    filterLabel: 'Filter cells by signal level',
    cells: 'cells',
    clear: 'Clear filters',
    legend: 'Historical severity index',
    notProbability: '0–100 is a relative index, not probability',
    national: 'Jordan overview',
    jordan: 'Jordan',
    nationalText: 'A quick summary of the cells in this historical snapshot.',
    distribution: 'Follow-up level distribution',
    total: 'total',
    howTitle: 'How should I use the map?',
    howText: 'Select a cell, review its score and data quality, then follow the suggested verification step. Do not make an irrigation decision from colour alone.',
    modelTitle: 'Does the model improve on simply carrying the current state forward?',
    selectedAria: 'Selected cell details',
    nationalAria: 'Jordan overview',
    close: 'Close cell details',
    disclaimerTitle: 'What does the map show?',
    disclaimer: 'A satellite-derived relative vegetation-stress signal compared with historical seasonal patterns. It is not a desertification diagnosis, field truth, causal explanation or live forecast.',
  },
}

export default function Explorer({ data, loading, error, refresh, horizon, setHorizon }) {
  const { language, locale, riskLabel } = useLanguage()
  const c = COPY[language]
  const [selected, setSelected] = useState(null)
  const [filter, setFilter] = useState('All')
  const [query, setQuery] = useState('')
  const [focusRequest, setFocusRequest] = useState(null)
  const p = PRIORITY_COPY[language]

  useEffect(() => {
    setSelected(null)
    setFocusRequest(null)
    setFilter('All')
    setQuery('')
  }, [horizon])

  const collection = data?.cells
  const filteredCollection = useMemo(() => {
    const features = (collection?.features ?? []).filter((feature) => {
      const properties = feature.properties ?? {}
      const matchesLevel = filter === 'All' || properties.risk_level === filter
      const matchesQuery = !query.trim() || properties.cell_id.toLowerCase().includes(query.trim().toLowerCase())
      return matchesLevel && matchesQuery
    })
    return { type: 'FeatureCollection', features }
  }, [collection, filter, query])

  const filteredProps = useMemo(() => filteredCollection.features.map((feature) => feature.properties), [filteredCollection])
  const allProps = useMemo(() => (collection?.features ?? []).map((feature) => feature.properties), [collection])
  const rankedTotal = allProps.find((item) => item.national_priority_total)?.national_priority_total ?? 0

  // Keep the selected cell on the map even when a level filter / search would hide it.
  const mapCollection = useMemo(() => {
    const id = selected?.properties?.cell_id
    if (!id || filteredCollection.features.some((feature) => feature.properties.cell_id === id)) return filteredCollection
    return { type: 'FeatureCollection', features: [...filteredCollection.features, selected] }
  }, [filteredCollection, selected])

  const selectCell = useCallback((cellId, { focus = true } = {}) => {
    const feature = (collection?.features ?? []).find((item) => item.properties.cell_id === cellId)
    if (!feature) return
    setSelected(feature)
    if (focus) {
      setFocusRequest((current) => ({ id: cellId, n: (current?.n ?? 0) + 1 }))
      window.requestAnimationFrame(() => document.getElementById('explorer-map')?.scrollIntoView({ block: 'nearest', behavior: 'auto' }))
    }
  }, [collection])

  const jumpToTop = useCallback(() => {
    const top = topPriority(allProps)[0]
    if (top) selectCell(top.cell_id)
  }, [allProps, selectCell])

  return (
    <div className="explorer-page">
      <section className="explorer-top section-shell">
        <div><span className="kicker"><Icon name="map" size={17} /> {c.kicker}</span><h1>{c.title}</h1><p>{c.intro}</p></div>
        <div className="explorer-top__controls"><HorizonToggle horizon={horizon} onChange={setHorizon} />{data && <SnapshotBadge area={data.area} source={data.source} />}</div>
      </section>

      {data && <div className="section-shell"><SourceNotice source={data.source} /></div>}

      <DailyNational />

      {loading && !data ? <div className="section-shell"><LoadingState full /></div> : error ? <div className="section-shell"><ErrorState message={error.message} onRetry={refresh} /></div> : data ? (
        <>
        <PriorityList properties={filteredProps} rankedTotal={rankedTotal} selectedId={selected?.properties?.cell_id} onSelect={selectCell} onJump={jumpToTop} horizon={horizon} />
        <section className="explorer-workspace section-shell">
          <div className="map-panel">
            <div className="map-toolbar">
              <div className="map-search"><Icon name="location" size={17} /><label className="sr-only" htmlFor="cell-search">{c.searchLabel}</label><input id="cell-search" type="search" value={query} placeholder={c.search} onChange={(event) => setQuery(event.target.value)} /></div>
              <div className="filter-row" role="group" aria-label={c.filterLabel}>
                {FILTERS.map((level) => <button type="button" className={filter === level ? 'is-active' : ''} aria-pressed={filter === level} key={level} onClick={() => setFilter(level)}>{riskLabel(level)}</button>)}
              </div>
              <button className="button button--secondary map-jump" type="button" onClick={jumpToTop} disabled={!rankedTotal}><Icon name="location" size={16} /> {p.jump}</button><span className="map-result-count">{formatCount(filteredCollection.features.length, locale)} {c.cells}</span>
            </div>
            <div className="map-stage" id="explorer-map">
              {collection.features.length ? (
                <>
                  <RiskMap collection={mapCollection} selectedId={selected?.properties?.cell_id} onSelect={setSelected} focusRequest={focusRequest} />
                  {!filteredCollection.features.length && <div className="map-empty-overlay"><EmptyState /><button className="text-button" type="button" onClick={() => { setFilter('All'); setQuery('') }}>{c.clear}</button></div>}
                </>
              ) : <EmptyState />}
              <div className="map-legend-card"><span className="eyebrow">{c.legend}</span><RiskLegend counts={data.area.summary} vertical /><small>{c.notProbability}</small></div>
            </div>
          </div>

          <aside className={`insight-panel ${selected ? 'insight-panel--selected' : ''}`} aria-label={selected ? c.selectedAria : c.nationalAria}>
            {selected ? (
              <>
                <button className="panel-close" type="button" onClick={() => setSelected(null)} aria-label={c.close}><Icon name="close" size={18} /></button>
                <CellSnapshot cell={selected} />
                <button className="text-button panel-viewmap" type="button" onClick={() => document.getElementById('explorer-map')?.scrollIntoView({ block: 'nearest', behavior: 'auto' })}>{p.viewOnMap}</button>
                <div className="panel-divider" />
                <ActionGuidance level={selected.properties?.risk_level} compact />
              </>
            ) : (
              <>
                <div className="panel-heading"><span className="eyebrow">{c.national}</span><h2>{c.jordan} · +{horizon}</h2><p>{c.nationalText}</p></div>
                <SummaryCards summary={data.area.summary} />
                <div className="panel-section"><div className="panel-section__title"><span>{c.distribution}</span><small>{formatCount(data.area.summary.total_cells, locale)} {c.total}</small></div><RiskLegend counts={data.area.summary} vertical /></div>
                <NationalContextNote summary={data.area.summary} />
                <div className="panel-callout"><Icon name="info" size={19} /><div><strong>{c.howTitle}</strong><p>{c.howText}</p></div></div>
                <div className="panel-section"><div className="panel-section__title"><span>{c.modelTitle}</span></div><MetricComparison metrics={data.metrics} horizon={horizon} compact /></div>
              </>
            )}
          </aside>
        </section>
        </>
      ) : null}

      <section className="section-shell map-disclaimer"><Icon name="satellite" size={19} /><p><strong>{c.disclaimerTitle}</strong> {c.disclaimer}</p></section>
    </div>
  )
}
