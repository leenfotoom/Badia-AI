import React from 'react'
import { Link } from 'react-router-dom'
import { PUBLISHED_METRICS, RISK_COLORS } from '../constants.js'
import { formatCount, formatPercent, formatScore, metricFor } from '../format.js'
import { useLanguage } from '../i18n.jsx'
import Icon from '../components/Icons.jsx'
import DailyNational from '../components/DailyNational.jsx'
import { ErrorState, HorizonToggle, LoadingState, RiskLegend, SourceNotice } from '../components/UI.jsx'
import { JORDAN_PATH, JORDAN_VIEWBOX, projectJordanPoint, representativeJordanFeatures } from '../jordanSilhouette.js'

const COPY = {
  ar: {
    kicker: 'ذكاء اصطناعي لمتابعة أرض الأردن',
    title: <>افهم إشارة الأرض،<br /><span>وابدأ من المكان الأهم.</span></>,
    intro: 'BADIA AI يحوّل بيانات الأقمار الصناعية إلى خريطة بسيطة تساعدك تعرف أين تحتاج متابعة أكثر خلال 16 أو 32 يومًا.',
    mapCta: 'افتح خريطة المتابعة',
    actionCta: 'اعرف ماذا تفعل',
    trust1: 'أحدث بيانات تاريخية متاحة من 2025',
    trust2: 'مؤشر واضح من 0 إلى 100',
    coverage: 'تغطية الأردن',
    snapshot: 'لقطة تاريخية',
    mean: 'متوسط مؤشر المتابعة',
    outOf: 'من 100',
    proof: ['خلية متاحة', 'فترتان للمتابعة', 'تحسن عن خط الأساس', 'سنوات المشاهدة'],
    aiEyebrow: 'شو دور الـAI؟',
    aiTitle: 'يختصر آلاف القراءات إلى قرار مفهوم.',
    aiIntro: 'بدل ما تبدأ من كل الأردن مرة واحدة، النموذج يساعدك ترتب الأولويات ثم يبيّن لماذا رفع خلية عن غيرها.',
    steps: [
      ['يقرأ', 'حالة الغطاء النباتي والمطر والحرارة ورطوبة التربة والتوقيت الموسمي.'],
      ['يتوقع', 'التغير النباتي النسبي بعد 16 أو 32 يومًا باستخدام نموذج XGBoost محفوظ ومختبر.'],
      ['يرتّب ويشرح', 'الخلايا من الأقل إلى الأعلى متابعة، ويعرض أبرز المدخلات التي أثّرت في النتيجة.'],
    ],
    actionEyebrow: 'من خريطة إلى خطة',
    actionTitle: 'اللون لا يكفي؛ كل مستوى معه خطوة تالية.',
    actionText: 'افتح أي خلية لترى ماذا تتحقق منه، وكيف تفحص فاقد المياه، ومتى ترفع أولوية الزيارة—من دون تحويل الدرجة إلى أمر ري تلقائي.',
    actionButton: 'شاهد دليل التصرّف',
    guardEyebrow: 'استخدمها بمسؤولية',
    guardTitle: 'إنذار مبكر، وليس حكمًا ميدانيًا.',
    guardText: 'النتيجة إشارة نباتية مشتقة من الأقمار الصناعية. لا تشخّص التصحر، ولا تثبت سبب الإجهاد، ولا تمثل توقعًا حيًا لعام 2026.',
    limits: 'كيف يعمل وحدود الاستخدام',
  },
  en: {
    kicker: 'AI for monitoring Jordan’s land',
    title: <>Understand the land signal,<br /><span>and start where attention matters.</span></>,
    intro: 'BADIA AI turns satellite observations into a simple map that shows where vegetation may need closer follow-up at +16 or +32 days.',
    mapCta: 'Open the priority map',
    actionCta: 'See what to do',
    trust1: 'Latest available historical data from 2025',
    trust2: 'A clear 0–100 index',
    coverage: 'Jordan coverage',
    snapshot: 'Historical snapshot',
    mean: 'Mean follow-up index',
    outOf: 'out of 100',
    proof: ['available cells', 'look-ahead periods', 'improvement over baseline', 'observation years'],
    aiEyebrow: 'What does the AI do?',
    aiTitle: 'It turns thousands of readings into a clear starting point.',
    aiIntro: 'Instead of reviewing all of Jordan at once, the model prioritizes locations and shows the inputs that influenced each result.',
    steps: [
      ['Read', 'Vegetation condition, rainfall, temperature, soil moisture and seasonal timing.'],
      ['Predict', 'Relative vegetation change at +16 or +32 days with a saved, evaluated XGBoost model.'],
      ['Prioritize and explain', 'Cells from lower to higher follow-up priority, plus the leading model inputs.'],
    ],
    actionEyebrow: 'From map to plan',
    actionTitle: 'A colour is not enough; every level has a next step.',
    actionText: 'Open a cell to see what to verify, how to check avoidable water loss and when to prioritize a visit—without turning the score into an automatic irrigation order.',
    actionButton: 'View the action guide',
    guardEyebrow: 'Use responsibly',
    guardTitle: 'An early signal, not a field verdict.',
    guardText: 'The result is a satellite-derived vegetation signal. It does not diagnose desertification, prove a cause, or represent a live 2026 forecast.',
    limits: 'How it works and its limits',
  },
}

function HeroMap({ data, copy }) {
  const features = data?.cells?.features ?? []
  const dots = representativeJordanFeatures(features)
  const summary = data?.area?.summary ?? {}
  return (
    <div className="hero-map" aria-label={copy.coverage}>
      <div className="hero-map__topline"><span><i /> {copy.coverage}</span><em>{copy.snapshot}</em></div>
      <div className="hero-map__canvas">
        <svg className="jordan-silhouette" viewBox={`0 0 ${JORDAN_VIEWBOX.width} ${JORDAN_VIEWBOX.height}`} role="img" aria-label={copy.coverage}>
          <defs>
            <linearGradient id="jordan-fill" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#744237" /><stop offset="1" stopColor="#2b241c" /></linearGradient>
            <clipPath id="jordan-clip"><path d={JORDAN_PATH} /></clipPath>
          </defs>
          <path className="jordan-silhouette__outline" d={JORDAN_PATH} fill="url(#jordan-fill)" stroke="#d3aa6d" strokeWidth="2" vectorEffect="non-scaling-stroke" />
          <g clipPath="url(#jordan-clip)">
          {dots.map((feature, index) => {
            const properties = feature.properties ?? {}
            const [x, y] = projectJordanPoint(properties.lon, properties.lat)
            return <circle key={`${properties.cell_id}-${index}`} cx={x} cy={y} r="5.5" fill={RISK_COLORS[properties.risk_level] ?? RISK_COLORS['N/A']} opacity=".92" />
          })}
          </g>
        </svg>
        <div className="hero-score-card"><small>{copy.mean}</small><strong>{formatScore(summary.mean_risk_score)}</strong><span>{copy.outOf}</span></div>
      </div>
      <RiskLegend />
    </div>
  )
}

export default function Landing({ data, loading, error, refresh, horizon, setHorizon }) {
  const { language, locale } = useLanguage()
  const c = COPY[language]
  const metrics = data?.metrics ?? PUBLISHED_METRICS
  const metric = metricFor(metrics, horizon)
  const summary = data?.area?.summary ?? {}

  return (
    <div className="landing-page">
      <section className="hero section-shell">
        <div className="hero__copy">
          <span className="kicker"><Icon name="satellite" size={17} /> {c.kicker}</span>
          <h1>{c.title}</h1>
          <p>{c.intro}</p>
          <div className="hero__actions">
            <Link className="button button--primary" to="/explorer">{c.mapCta} <Icon name="arrow" size={17} /></Link>
            <Link className="button button--ghost" to="/action">{c.actionCta}</Link>
          </div>
          <div className="hero__trust"><span><Icon name="calendar" size={17} /> {c.trust1}</span><span><Icon name="quality" size={17} /> {c.trust2}</span></div>
        </div>
        <div className="hero__visual">
          <div className="hero-orbit hero-orbit--one" /><div className="hero-orbit hero-orbit--two" />
          {loading && !data ? <LoadingState /> : error ? <ErrorState message={error.message} onRetry={refresh} compact /> : <HeroMap data={data} copy={c} />}
        </div>
      </section>

      {data && <div className="section-shell"><SourceNotice source={data.source} /></div>}

      <DailyNational />

      <section className="proof-strip" aria-label="snapshot summary">
        <div className="section-shell proof-strip__inner">
          <article><strong>{formatCount(summary.available_cells, locale)}</strong><span>{c.proof[0]}</span></article>
          <article><strong>2</strong><span>{c.proof[1]}</span></article>
          <article><strong>{formatPercent(metric?.validation?.improvement_pct)}</strong><span>{c.proof[2]}</span></article>
          <article><strong>2015–25</strong><span>{c.proof[3]}</span></article>
        </div>
      </section>

      <section className="section-shell signal-section">
        <div className="section-heading"><div><span className="eyebrow">{c.aiEyebrow}</span><h2>{c.aiTitle}</h2><p>{c.aiIntro}</p></div><HorizonToggle horizon={horizon} onChange={setHorizon} /></div>
        <div className="method-cards">
          {c.steps.map(([title, text], index) => (
            <article key={title}><span className="method-card__number">0{index + 1}</span><Icon name={index === 0 ? 'satellite' : index === 1 ? 'chart' : 'map'} /><h3>{title}</h3><p>{text}</p></article>
          ))}
        </div>
      </section>

      <section className="home-action-band">
        <div className="section-shell home-action-band__inner">
          <span className="home-action-band__icon"><Icon name="water" size={28} /></span>
          <div><span className="eyebrow">{c.actionEyebrow}</span><h2>{c.actionTitle}</h2><p>{c.actionText}</p></div>
          <Link className="button button--primary" to="/action">{c.actionButton} <Icon name="arrow" size={17} /></Link>
        </div>
      </section>

      <section className="section-shell guardrail-section">
        <div className="guardrail-card">
          <span className="guardrail-card__icon"><Icon name="info" size={25} /></span>
          <div><span className="eyebrow">{c.guardEyebrow}</span><h2>{c.guardTitle}</h2><p>{c.guardText}</p></div>
          <Link className="text-link" to="/science">{c.limits} <Icon name="arrow" size={16} /></Link>
        </div>
      </section>
    </div>
  )
}
