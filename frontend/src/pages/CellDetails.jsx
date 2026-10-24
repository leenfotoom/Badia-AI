import React, { useEffect, useRef } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import ActionGuidance from '../components/ActionGuidance.jsx'
import DailyForecast from '../components/DailyForecast.jsx'
import RiskMap from '../components/RiskMap.jsx'
import Icon from '../components/Icons.jsx'
import PriorityInfo, { NationalContextNote } from '../components/PriorityInfo.jsx'
import { ErrorState, FactorList, HorizonToggle, LoadingState, MetricComparison, QualityPanel, RiskPill, SnapshotBadge } from '../components/UI.jsx'
import { useCellDetails } from '../hooks/useBadiaData.js'
import { formatAnomaly, formatDecimal, formatScore } from '../format.js'
import { cellLocationLabel } from '../location.js'
import { resolveDeepLinkedHorizon } from '../horizon.js'
import { useLanguage } from '../i18n.jsx'

const COPY = {
  ar: {
    back: 'خريطة المتابعة',
    kicker: 'تفاصيل خلية المتابعة · التوقع متوسط المدى للغطاء النباتي (+16/+32 يوم)',
    intro: 'سجل تاريخي محفوظ لخلية واحدة في الأردن، مع نتيجة النموذج والخطوة المقترحة للتحقق.',
    loading: 'جارٍ تحميل تفاصيل الخلية…',
    notFound: 'الخلية غير موجودة',
    notFoundText: 'هذا الرقم غير موجود في لقطة +{horizon} يوم المحلية.',
    return: 'العودة إلى الخريطة',
    index: 'مؤشر الشدة التاريخية',
    scoreNote: 'هذه رتبة مئينية موسمية تاريخية، وليست احتمال وقوع حدث ميداني.',
    anomaly: 'التغير النباتي المتوقع',
    horizon: 'الفترة',
    latitude: 'خط العرض',
    longitude: 'خط الطول',
    actionEyebrow: 'ماذا نفعل بهذه النتيجة؟',
    actionTitle: 'ابدأ بالتحقق، وليس بقرار ري تلقائي.',
    factorsEyebrow: 'تفسير النموذج',
    factorsTitle: 'أكثر المدخلات تأثيرًا',
    factorsNote: 'الترتيب حسب مساهمة TreeSHAP في نتيجة هذه الخلية. هذه علاقات داخل النموذج وليست أسبابًا بيئية مؤكدة.',
    qualityEyebrow: 'اكتمال المدخلات',
    qualityTitle: 'جودة البيانات والسياق',
    currentNdvi: 'حالة الغطاء النباتي الحالية',
    currentAnomaly: 'الانحراف الموسمي الحالي',
    rain16: 'مطر · 16 يومًا',
    rain90: 'مطر · 90 يومًا',
    temp30: 'حرارة · 30 يومًا',
    soil30: 'رطوبة التربة · 30 يومًا',
    evaluationEyebrow: 'التقييم التاريخي',
    evaluationTitle: 'XGBoost مقارنة ببقاء الحالة كما هي',
    cautionTitle: 'استخدم النتيجة بحذر.',
    caution: 'هذه إشارة نباتية مشتقة من الأقمار الصناعية. ليست تشخيص تصحر، ولا حقيقة ميدانية، ولا تفسيرًا سببيًا، ولا توقعًا حيًا لعام 2026.',
  },
  en: {
    back: 'Priority map',
    kicker: 'Cell follow-up details · medium-term vegetation outlook (+16/+32 d)',
    intro: 'A saved historical record for one Jordan cell, with the model result and a suggested verification step.',
    loading: 'Loading cell details…',
    notFound: 'Cell not found',
    notFoundText: 'This identifier is not present in the local +{horizon}-day snapshot.',
    return: 'Return to the map',
    index: 'Historical severity index',
    scoreNote: 'This is a historical seasonal percentile, not the probability of a field event.',
    anomaly: 'Predicted vegetation change',
    horizon: 'Look-ahead',
    latitude: 'Latitude',
    longitude: 'Longitude',
    actionEyebrow: 'What should we do with this result?',
    actionTitle: 'Start with verification, not an automatic irrigation decision.',
    factorsEyebrow: 'Model interpretation',
    factorsTitle: 'Most influential inputs',
    factorsNote: 'Ranked by absolute TreeSHAP contribution for this cell. These are model relationships, not confirmed environmental causes.',
    qualityEyebrow: 'Input coverage',
    qualityTitle: 'Data quality and context',
    currentNdvi: 'Current vegetation condition',
    currentAnomaly: 'Current seasonal anomaly',
    rain16: 'Rain · 16 days',
    rain90: 'Rain · 90 days',
    temp30: 'Temperature · 30 days',
    soil30: 'Soil moisture · 30 days',
    evaluationEyebrow: 'Historical evaluation',
    evaluationTitle: 'XGBoost compared with persistence',
    cautionTitle: 'Use the result with care.',
    caution: 'This is a satellite-derived vegetation signal. It is not a desertification diagnosis, field truth, causal explanation or live 2026 forecast.',
  },
}

export default function CellDetails({ data, loading, error, refresh, horizon, setHorizon }) {
  const { language, t } = useLanguage()
  const c = COPY[language]
  const { cellId } = useParams()
  const [params] = useSearchParams()
  const requestedHorizon = params.get('horizon')
  const appliedRequestedHorizon = useRef(null)

  useEffect(() => {
    const resolution = resolveDeepLinkedHorizon(requestedHorizon, horizon, appliedRequestedHorizon.current)
    appliedRequestedHorizon.current = resolution.applied
    if (resolution.next != null) setHorizon(resolution.next)
  }, [requestedHorizon, horizon, setHorizon])

  const detail = useCellDetails(cellId, horizon, data?.cells)
  const cell = detail.cell
  const properties = cell?.properties
  const location = properties ? cellLocationLabel(properties, language) ?? t('cell.locationUnavailable') : null
  const singleCollection = cell ? { type: 'FeatureCollection', features: [cell] } : null

  if (loading && !data) return <div className="section-shell page-state"><LoadingState full label={c.loading} /></div>
  if (error && !data) return <div className="section-shell page-state"><ErrorState message={error.message} onRetry={refresh} /></div>

  return (
    <div className="cell-page section-shell">
      <div className="page-breadcrumbs"><Link to="/explorer"><Icon name="chevron" size={15} /> {c.back}</Link><span>/</span><span>{cellId}</span></div>
      <header className="cell-page__header">
        <div>
          <span className="kicker"><Icon name="location" size={17} /> {c.kicker}</span>
          <h1>{location ?? cellId}</h1>
          {location && <p className="cell-page__cell-id">{t('cell.id')} <b dir="ltr">{cellId}</b></p>}
          <p>{c.intro}</p>
        </div>
        <div className="cell-page__controls"><HorizonToggle horizon={horizon} onChange={setHorizon} />{data && <SnapshotBadge area={data.area} source={data.source} />}</div>
      </header>

      {detail.loading ? <LoadingState label={c.loading} /> : !cell ? (
        <div className="state-card state-card--full"><span className="state-card__icon"><Icon name="location" size={24} /></span><strong>{c.notFound}</strong><p>{c.notFoundText.replace('{horizon}', horizon)}</p><Link className="button button--secondary" to="/explorer">{c.return}</Link></div>
      ) : (
        <>
          <section className="cell-hero-grid">
            <article className="cell-score-card">
              <div className="cell-score-card__top"><span className="eyebrow">{c.index}</span><RiskPill level={properties.risk_level} /></div>
              <div className="cell-score-card__value"><strong>{formatScore(properties.risk_score)}</strong><span>/100</span></div>
              <div className="score-display__track">{Number.isFinite(properties.risk_score) && <i style={{ width: `${Math.max(0, Math.min(100, properties.risk_score))}%` }} />}</div>
              <p>{c.scoreNote}</p>
              <PriorityInfo properties={properties} />
              <dl className="detail-facts">
                <div><dt>{c.anomaly}</dt><dd>{formatAnomaly(properties.predicted_anomaly)}</dd></div>
                <div><dt>{c.horizon}</dt><dd>{t('horizon.days', { value: properties.horizon_days })}</dd></div>
                <div><dt>{c.latitude}</dt><dd>{formatDecimal(properties.lat, 5)}</dd></div>
                <div><dt>{c.longitude}</dt><dd>{formatDecimal(properties.lon, 5)}</dd></div>
              </dl>
            </article>
            <div className="cell-map-card"><RiskMap collection={singleCollection} selectedId={properties.cell_id} compact /></div>
          </section>

          <DailyForecast cellId={properties.cell_id} />

          <section className="cell-action-section">
            <div className="cell-action-section__heading"><span className="eyebrow">{c.actionEyebrow}</span><h2>{c.actionTitle}</h2></div>
            <ActionGuidance level={properties.risk_level} />
          </section>

          <section className="detail-grid">
            <article className="detail-card detail-card--factors">
              <div className="detail-card__heading"><span className="detail-card__icon"><Icon name="chart" size={20} /></span><div><span className="eyebrow">{c.factorsEyebrow}</span><h2>{c.factorsTitle}</h2></div></div>
              <FactorList factors={properties.top_factors} />
              <p className="card-footnote">{c.factorsNote}</p>
            </article>
            <article className="detail-card">
              <div className="detail-card__heading"><span className="detail-card__icon"><Icon name="quality" size={20} /></span><div><span className="eyebrow">{c.qualityEyebrow}</span><h2>{c.qualityTitle}</h2></div></div>
              <QualityPanel quality={properties.data_quality} />
              <dl className="source-facts">
                <div><dt>{c.currentNdvi}</dt><dd>{formatDecimal(properties.ndvi, 4)}</dd></div>
                <div><dt>{c.currentAnomaly}</dt><dd>{formatAnomaly(properties.ndvi_anomaly_current)}</dd></div>
                <div><dt>{c.rain16}</dt><dd>{formatDecimal(properties.rain_16d_mm, 2)} mm</dd></div>
                <div><dt>{c.rain90}</dt><dd>{formatDecimal(properties.rain_90d_mm, 2)} mm</dd></div>
                <div><dt>{c.temp30}</dt><dd>{formatDecimal(properties.temperature_30d_c, 1)} °C</dd></div>
                <div><dt>{c.soil30}</dt><dd>{formatDecimal(properties.soil_moisture_30d, 4)}</dd></div>
              </dl>
            </article>
          </section>

          <section className="detail-card cell-evaluation"><div className="detail-card__heading"><span className="detail-card__icon"><Icon name="science" size={20} /></span><div><span className="eyebrow">{c.evaluationEyebrow}</span><h2>{c.evaluationTitle}</h2></div></div><MetricComparison metrics={data?.metrics} horizon={horizon} /></section>
          <section className="cell-context"><NationalContextNote summary={data?.area?.summary} /></section>
          <aside className="responsibility-note"><Icon name="info" size={21} /><p><strong>{c.cautionTitle}</strong> {c.caution}</p></aside>
        </>
      )}
    </div>
  )
}
