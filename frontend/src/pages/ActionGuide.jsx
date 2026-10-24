import React from 'react'
import { Link } from 'react-router-dom'
import ActionGuidance from '../components/ActionGuidance.jsx'
import Icon from '../components/Icons.jsx'
import { GUIDANCE_SOURCES } from '../guidance.js'
import { useLanguage } from '../i18n.jsx'

const COPY = {
  ar: {
    kicker: 'من الإشارة إلى التصرّف',
    title: 'الذكاء الاصطناعي يحدد الأولوية، والقرار يبدأ بالتحقق.',
    intro: 'BADIA AI لا يصنع المطر ولا يقرر كمية الري. دوره أن يقرأ النمط التاريخي بسرعة، يلفت الانتباه للمناطق غير المعتادة، ثم يساعد الفريق يبدأ من المكان الأهم.',
    cta: 'افتح خريطة المتابعة',
    roleEyebrow: 'دور الذكاء الاصطناعي',
    roleTitle: 'ثلاث مهام واضحة بدل صندوق أسود.',
    roles: [
      ['يقرأ', 'يجمع حالة الغطاء النباتي مع المطر والحرارة ورطوبة التربة والتوقيت الموسمي.'],
      ['يتوقع ويقارن', 'يقدّر التغير النباتي بعد 16 أو 32 يومًا ويقارنه بموسمه التاريخي.'],
      ['يرتّب ويشرح', 'يرتب الخلايا حسب أولوية المتابعة ويعرض المدخلات الأكثر تأثيرًا في نتيجة النموذج.'],
    ],
    notTitle: 'ما الذي لا يفعله؟',
    notItems: ['لا يشخّص الجفاف أو التصحر ميدانيًا.', 'لا يحدد السبب البيئي وحده.', 'لا يعطي أمرًا تلقائيًا بزيادة أو خفض الري.', 'لا يمثل توقعًا حيًا لعام 2026 في هذه النسخة.'],
    levelsEyebrow: 'اقرأ اللون ثم تحرّك',
    levelsTitle: 'إجراء متناسب مع مستوى الإشارة.',
    levelsIntro: 'هذه الخطوات دليل قرار، وليست وصفة ري. ابدأ دائمًا بالمعلومة الأحدث والتحقق من الموقع.',
    pathwayEyebrow: 'حل عملي للجفاف',
    pathwayTitle: 'النظام لا يحل الجفاف وحده؛ يساعد على تنفيذ استجابة أذكى.',
    pathways: [
      ['إنذار مبكر', 'رصد التغير غير المعتاد قبل أن يتحول إلى مشكلة أكبر.'],
      ['تحقق ميداني موجّه', 'إرسال الزيارة للمناطق ذات الأولوية بدل توزيع الجهد عشوائيًا.'],
      ['تقليل الفاقد', 'فحص التسرب وتوقيت الري وانتظام التوزيع وتحسين كفاءة استخدام المياه.'],
      ['ترتيب الموارد', 'توجيه المتابعة والدعم للمواقع والمحاصيل والمراعي الأكثر حساسية.'],
      ['تعلم مستمر', 'تسجيل ما حدث على الأرض ومقارنته مع الإشارة لتحسين القرار القادم.'],
    ],
    flowEyebrow: 'طريقة الاستخدام',
    flowTitle: 'قرار مفهوم في أربع خطوات.',
    flow: [
      ['1', 'اختر الخلية', 'ابدأ من اللون والدرجة، ثم افتح تفاصيل الموقع.'],
      ['2', 'راجع المدخلات', 'انظر للمطر ورطوبة التربة وجودة البيانات وأبرز عوامل النموذج.'],
      ['3', 'تحقق محليًا', 'قارن مع الواقع: النبات، التربة، الري، وأي معلومة حديثة.'],
      ['4', 'نفّذ وسجّل', 'اختر الإجراء المتناسب وسجّل النتيجة ليصبح القرار التالي أفضل.'],
    ],
    demoTitle: 'مهم قبل الاستخدام',
    demo: 'الخريطة الحالية لقطة تاريخية من 2025 للعرض والتحقق التقني. لا تستخدم ألوانها لاتخاذ إجراء ميداني اليوم. في التشغيل الحقيقي يجب إدخال بيانات حديثة ثم اتباع مسار التحقق أعلاه.',
    sourcesEyebrow: 'السياق الأردني',
    sourcesTitle: 'إرشادات مبنية على توجهات رسمية لكفاءة المياه وإدارة الجفاف.',
    sourcesText: 'الخطوات تعكس مبادئ الإنذار المبكر، كفاءة استخدام المياه، التحقق، وترتيب التدخلات. الروابط التالية للمراجعة المؤسسية وليست اعتمادًا رسميًا للمنتج.',
  },
  en: {
    kicker: 'From signal to action',
    title: 'AI sets the priority; a sound decision starts with verification.',
    intro: 'BADIA AI does not make rain or prescribe irrigation. It reads historical patterns quickly, flags unusual locations and helps teams start where attention matters most.',
    cta: 'Open the priority map',
    roleEyebrow: 'The role of AI',
    roleTitle: 'Three clear jobs, not a black box.',
    roles: [
      ['Read', 'Combine vegetation condition with rainfall, temperature, soil moisture and seasonal timing.'],
      ['Predict and compare', 'Estimate vegetation change at +16 or +32 days and compare it with the historical season.'],
      ['Prioritize and explain', 'Rank cells for follow-up and show the inputs that most influenced the model result.'],
    ],
    notTitle: 'What does it not do?',
    notItems: ['It does not diagnose drought or desertification in the field.', 'It does not identify environmental causes on its own.', 'It does not automatically prescribe more or less irrigation.', 'This edition is not a live 2026 forecast.'],
    levelsEyebrow: 'Read the colour, then act',
    levelsTitle: 'A proportionate response for each signal level.',
    levelsIntro: 'These are decision prompts, not an irrigation prescription. Always begin with current information and local verification.',
    pathwayEyebrow: 'A practical drought response',
    pathwayTitle: 'The system does not solve drought alone; it helps people respond more intelligently.',
    pathways: [
      ['Earlier warning', 'Notice unusual vegetation change before it grows into a larger problem.'],
      ['Targeted field checks', 'Send limited field capacity to priority locations instead of spreading it randomly.'],
      ['Reduce avoidable loss', 'Inspect leaks, timing and distribution uniformity to improve water-use efficiency.'],
      ['Prioritize resources', 'Direct monitoring and support toward the most sensitive locations, crops or rangelands.'],
      ['Keep learning', 'Record field outcomes and compare them with the signal to improve the next decision.'],
    ],
    flowEyebrow: 'How to use it',
    flowTitle: 'A clear decision in four steps.',
    flow: [
      ['1', 'Choose a cell', 'Start with colour and score, then open the location details.'],
      ['2', 'Review the inputs', 'Check rainfall, soil moisture, data quality and leading model factors.'],
      ['3', 'Verify locally', 'Compare the signal with plants, soil, irrigation and any current information.'],
      ['4', 'Act and record', 'Choose a proportionate response and record the outcome for the next decision.'],
    ],
    demoTitle: 'Important before use',
    demo: 'The current map is a historical 2025 snapshot for demonstration and technical verification. Do not use its colours for a field action today. Operations require current inputs followed by the verification path above.',
    sourcesEyebrow: 'Jordan context',
    sourcesTitle: 'Guidance grounded in official drought-management and water-efficiency directions.',
    sourcesText: 'The steps reflect early warning, water-use efficiency, verification and prioritization. These links are institutional references, not an official endorsement of the product.',
  },
}

export default function ActionGuide() {
  const { language } = useLanguage()
  const c = COPY[language]
  return (
    <div className="action-page">
      <section className="action-hero section-shell">
        <div>
          <span className="kicker"><Icon name="water" size={18} /> {c.kicker}</span>
          <h1>{c.title}</h1>
          <p>{c.intro}</p>
          <Link className="button button--primary" to="/explorer">{c.cta} <Icon name="map" size={17} /></Link>
        </div>
        <div className="ai-role-card">
          <span className="eyebrow">{c.notTitle}</span>
          <ul>{c.notItems.map((item) => <li key={item}><Icon name="alert" size={17} /><span>{item}</span></li>)}</ul>
        </div>
      </section>

      <section className="section-shell ai-role-section">
        <div className="section-heading"><div><span className="eyebrow">{c.roleEyebrow}</span><h2>{c.roleTitle}</h2></div></div>
        <div className="role-grid">
          {c.roles.map(([title, text], index) => (
            <article key={title}><b>0{index + 1}</b><Icon name={index === 0 ? 'satellite' : index === 1 ? 'chart' : 'map'} /><h3>{title}</h3><p>{text}</p></article>
          ))}
        </div>
      </section>

      <section className="action-levels-section">
        <div className="section-shell">
          <div className="section-heading"><div><span className="eyebrow">{c.levelsEyebrow}</span><h2>{c.levelsTitle}</h2><p>{c.levelsIntro}</p></div></div>
          <div className="guidance-grid">{['Low', 'Moderate', 'High', 'N/A'].map((level) => <ActionGuidance key={level} level={level} showLink={false} />)}</div>
        </div>
      </section>

      <section className="section-shell drought-pathway-section">
        <div className="section-heading"><div><span className="eyebrow">{c.pathwayEyebrow}</span><h2>{c.pathwayTitle}</h2></div></div>
        <div className="pathway-grid">
          {c.pathways.map(([title, text], index) => <article key={title}><span><Icon name={index < 2 ? 'satellite' : index === 2 ? 'water' : index === 3 ? 'location' : 'quality'} /></span><h3>{title}</h3><p>{text}</p></article>)}
        </div>
      </section>

      <section className="decision-flow-section">
        <div className="section-shell">
          <div className="section-heading"><div><span className="eyebrow">{c.flowEyebrow}</span><h2>{c.flowTitle}</h2></div></div>
          <div className="decision-flow">{c.flow.map(([number, title, text]) => <article key={number}><b>{number}</b><div><h3>{title}</h3><p>{text}</p></div></article>)}</div>
          <aside className="historical-action-note"><Icon name="calendar" size={22} /><div><strong>{c.demoTitle}</strong><p>{c.demo}</p></div></aside>
        </div>
      </section>

      <section className="section-shell reference-section">
        <div><span className="eyebrow">{c.sourcesEyebrow}</span><h2>{c.sourcesTitle}</h2><p>{c.sourcesText}</p></div>
        <div className="reference-links">
          {GUIDANCE_SOURCES.map((source) => <a key={source.url} href={source.url} target="_blank" rel="noreferrer">{language === 'ar' ? source.labelAr : source.labelEn} <Icon name="arrow" size={15} /></a>)}
        </div>
      </section>
    </div>
  )
}
