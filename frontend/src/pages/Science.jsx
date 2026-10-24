import React from 'react'
import { Link } from 'react-router-dom'
import Icon from '../components/Icons.jsx'
import { HorizonToggle, MetricComparison, SnapshotBadge } from '../components/UI.jsx'
import { useLanguage } from '../i18n.jsx'

const COPY = {
  ar: {
    kicker: 'كيف يعمل BADIA AI؟',
    title: <>ذكاء اصطناعي واضح،<br /><span>وحدود استخدام واضحة.</span></>,
    intro: 'شرح مبسّط لكيفية تحويل المشاهدات الفضائية المحفوظة إلى مؤشر متابعة نسبي، وكيف نعرف أن النموذج أضاف قيمة.',
    pipelineEyebrow: 'رحلة المعلومة',
    pipelineTitle: 'من القمر الصناعي إلى الخريطة في أربع خطوات.',
    pipeline: [
      ['يراقب', 'يقرأ الغطاء النباتي والمطر والحرارة ورطوبة التربة والموقع والتوقيت الموسمي.'],
      ['يقارن', 'يقارن حالة الغطاء النباتي بخطها الموسمي التاريخي لكل خلية وفترة.'],
      ['يتوقع', 'نموذجا XGBoost مجمّدان يتوقعان الانحراف النباتي بعد 16 أو 32 يومًا.'],
      ['يرتّب', 'يحوّل شدة الإشارة المتوقعة إلى رتبة مئينية موسمية من 0 إلى 100.'],
    ],
    riskEyebrow: 'معنى الدرجة',
    riskTitle: 'شدة نسبية وليست احتمالًا.',
    formulaLabel: 'مؤشر المتابعة',
    formula: '= الرتبة المئينية الموسمية لـ (− الانحراف المتوقع) × 100',
    riskText: 'كلما ارتفعت الدرجة، كانت إشارة الإجهاد التي توقعها النموذج أقوى مقارنة بالفترات التاريخية المشابهة. هذا لا يعني احتمال وقوع جفاف بنسبة الدرجة.',
    coreUnavailable: 'الإشارة الأساسية غير متاحة',
    timeEyebrow: 'اختبار زمني نزيه',
    timeTitle: 'المستقبل لم يدخل في تدريب الماضي.',
    time: [['تدريب', '2015–2022'], ['اختيار وضبط', '2023 فقط'], ['اختبار نهائي مجمّد', '2024–2025'], ['الأهداف', 'تبقى داخل السنة الميلادية']],
    evalEyebrow: 'هل النموذج أفضل فعلًا؟',
    evalTitle: 'XGBoost حقق خطأ أقل من خط أساس الاستمرار.',
    evalText: 'المعيار هو متوسط الخطأ المطلق؛ الرقم الأقل أفضل. النتائج مأخوذة من ملفات التقييم المحفوظة التي زوّد بها المشروع.',
    limitsEyebrow: 'حدود التفسير',
    limitsTitle: 'ما الذي نستفيد منه، وما الذي لا نستطيع ادعاءه؟',
    limitsText: 'الدرجة تساعد على ترتيب المتابعة، لكنها لا تستبدل فحص الموقع أو خبرة الفريق الزراعي والمائي.',
    cta: 'افتح خريطة المتابعة',
    can: 'يمكن',
    cannot: 'لا يمكن',
    items: [
      ['can', 'ترتيب أولوية المتابعة', 'مقارنة الخلايا بمرجع موسمي تاريخي ثابت.'],
      ['can', 'شرح سلوك النموذج', 'عرض المدخلات التي ساهمت أكثر في نتيجة كل خلية.'],
      ['cannot', 'تشخيص التصحر أو الجفاف ميدانيًا', 'لا يوجد تحقق ميداني شامل يجعل النتيجة تشخيصًا.'],
      ['cannot', 'إثبات السبب', 'مساهمات النموذج ليست آلية سببية بيئية.'],
      ['cannot', 'العمل كتوقع حي', 'لا توجد مدخلات 2026؛ أحدث لقطة مشتركة هنا تاريخية من 2025.'],
    ],
  },
  en: {
    kicker: 'How does BADIA AI work?',
    title: <>Transparent AI,<br /><span>with clear boundaries.</span></>,
    intro: 'A plain-language explanation of how saved satellite observations become a relative follow-up index, and how we know the model added value.',
    pipelineEyebrow: 'Information journey',
    pipelineTitle: 'From satellite observation to map in four steps.',
    pipeline: [
      ['Observe', 'Read vegetation, rainfall, temperature, soil moisture, location and seasonal timing.'],
      ['Compare', 'Compare vegetation condition with its historical seasonal reference for each cell and period.'],
      ['Predict', 'Two frozen XGBoost models estimate vegetation anomaly at +16 and +32 days.'],
      ['Rank', 'Convert predicted signal severity into a seasonal percentile from 0 to 100.'],
    ],
    riskEyebrow: 'What the score means',
    riskTitle: 'Relative severity, not probability.',
    formulaLabel: 'Follow-up index',
    formula: '= seasonal percentile of (− predicted anomaly) × 100',
    riskText: 'A higher score means the model predicted a stronger stress signal compared with similar historical periods. It does not mean drought will occur with that percentage probability.',
    coreUnavailable: 'core signal unavailable',
    timeEyebrow: 'Honest time split',
    timeTitle: 'Future data never entered past training.',
    time: [['Train', '2015–2022'], ['Tune and validate', '2023 only'], ['Frozen final test', '2024–2025'], ['Targets', 'stay inside each calendar year']],
    evalEyebrow: 'Does the model really improve?',
    evalTitle: 'XGBoost achieved lower error than the persistence baseline.',
    evalText: 'The measure is mean absolute error; lower is better. Results come from the saved evaluation artifacts supplied with the project.',
    limitsEyebrow: 'Interpretation boundaries',
    limitsTitle: 'What can the map support—and what can it not claim?',
    limitsText: 'The index helps prioritize follow-up, but it does not replace a site check or water and agriculture expertise.',
    cta: 'Open the priority map',
    can: 'Can',
    cannot: 'Cannot',
    items: [
      ['can', 'Prioritize follow-up', 'Compare cells against a consistent historical seasonal reference.'],
      ['can', 'Explain model behaviour', 'Show the inputs that contributed most to each cell result.'],
      ['cannot', 'Diagnose drought or desertification', 'No comprehensive field verification makes the result a diagnosis.'],
      ['cannot', 'Prove a cause', 'Model contributions are not environmental causal mechanisms.'],
      ['cannot', 'Act as a live forecast', 'No 2026 inputs are present; the latest common snapshot is historical 2025 data.'],
    ],
  },
}

export default function Science({ data, horizon, setHorizon }) {
  const { language, riskLabel } = useLanguage()
  const c = COPY[language]
  return (
    <div className="science-page">
      <section className="science-hero section-shell">
        <div><span className="kicker"><Icon name="science" size={17} /> {c.kicker}</span><h1>{c.title}</h1><p>{c.intro}</p></div>
        {data && <SnapshotBadge area={data.area} source={data.source} />}
      </section>

      <section className="section-shell pipeline-section">
        <div className="section-heading"><div><span className="eyebrow">{c.pipelineEyebrow}</span><h2>{c.pipelineTitle}</h2></div></div>
        <div className="pipeline-grid">{c.pipeline.map(([title, text], index) => <article key={title}><b>0{index + 1}</b><Icon name={index === 0 ? 'satellite' : index === 1 ? 'layers' : index === 2 ? 'chart' : 'map'} /><h3>{title}</h3><p>{text}</p></article>)}</div>
      </section>

      <section className="section-shell formula-grid">
        <article className="formula-card">
          <span className="eyebrow">{c.riskEyebrow}</span><h2>{c.riskTitle}</h2>
          <div className="formula"><span>{c.formulaLabel}</span><strong>{c.formula}</strong></div><p>{c.riskText}</p>
          <div className="thresholds">
            <span><i className="low" /><strong>{riskLabel('Low')}</strong><small>0–39.9</small></span>
            <span><i className="moderate" /><strong>{riskLabel('Moderate')}</strong><small>40–69.9</small></span>
            <span><i className="high" /><strong>{riskLabel('High')}</strong><small>70–100</small></span>
            <span><i className="na" /><strong>{riskLabel('N/A')}</strong><small>{c.coreUnavailable}</small></span>
          </div>
        </article>
        <article className="formula-card formula-card--dark">
          <span className="eyebrow">{c.timeEyebrow}</span><h2>{c.timeTitle}</h2>
          <ul className="check-list">{c.time.map(([title, text]) => <li key={title}><Icon name="quality" size={18} /><span><strong>{title}</strong> {text}</span></li>)}</ul>
        </article>
      </section>

      <section className="evaluation-section"><div className="section-shell"><div className="section-heading section-heading--evaluation"><div><span className="eyebrow">{c.evalEyebrow}</span><h2>{c.evalTitle}</h2><p>{c.evalText}</p></div><HorizonToggle horizon={horizon} onChange={setHorizon} /></div><MetricComparison metrics={data?.metrics} horizon={horizon} /></div></section>

      <section className="section-shell limits-section">
        <div className="limits-copy"><span className="eyebrow">{c.limitsEyebrow}</span><h2>{c.limitsTitle}</h2><p>{c.limitsText}</p><Link className="button button--primary" to="/explorer">{c.cta} <Icon name="map" size={17} /></Link></div>
        <div className="limits-list">{c.items.map(([type, title, text]) => <article key={title} className={type === 'cannot' ? 'limits-list__no' : ''}><span>{type === 'cannot' ? c.cannot : c.can}</span><h3>{title}</h3><p>{text}</p></article>)}</div>
      </section>
    </div>
  )
}
