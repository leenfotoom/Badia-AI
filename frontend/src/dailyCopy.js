// Arabic / English copy for the daily forecast panel. Wording: associations, not causes; score is not a probability.
export const DAILY_COPY = {
  ar: {
    eyebrow: 'التوقع اليومي', title: 'خطر الإجهاد البيئي: اليوم و٧ أيام قادمة',
    intro: 'مؤشر نسبي من ٠ إلى ١٠٠ لشدة الإجهاد الجوي والمائي المتوقع في هذه الخلية. ليس احتمالًا، ولا قياسًا للغطاء النباتي، ولا تشخيصًا ميدانيًا.',
    today: 'اليوم', plusDay: '+{n} يوم', outOf: '/100', changeVsToday: 'التغير عن اليوم', noChange: 'بلا تغير',
    whyTitle: 'ما الذي يرتبط بهذه النتيجة؟', whyNote: 'علاقات داخل النموذج (TreeSHAP) وليست أسبابًا مؤكدة.',
    raises: 'يرفع المؤشر', lowers: 'يخفض المؤشر', changeWhy: 'سبب التغير عن اليوم', noReasons: 'لا عوامل بارزة لهذا اليوم.',
    issued: 'وقت إنشاء لقطة التوقع', issueDay: 'يوم مرجع التوقع', forecastReference: 'وقت مرجع التنبؤ الجوي',
    weatherSrc: 'التنبؤ الجوي', weatherAge: 'عمر التنبؤ: {h} ساعة', retrieved: 'وقت الاسترجاع',
    obsSrc: 'آخر رصد متاح', obsNote: 'الرصد المتأخر أو إعادة التحليل ليس بيانات لحظية.',
    satSrc: 'آخر رصد قمر صناعي متاح', satNote: 'الرصد المركّب والمتأخر لا يُعرض كبيانات لحظية.', satNone: 'غير متاح',
    lastSuccess: 'آخر تحديث ناجح', servedFrom: 'النسخة المعروضة', servedLatest: 'أحدث لقطة', servedFallback: 'آخر لقطة سليمة احتياطية',
    model: 'نسخة النموذج', confidence: 'الثقة وجودة البيانات',
    conf: { high: 'مرتفعة', medium: 'متوسطة', low: 'منخفضة', unknown: 'غير متاحة' },
    confParts: { validated_skill: 'مهارة النموذج المختبرة', input_completeness: 'اكتمال المدخلات', freshness: 'حداثة المصادر' },
    veg: 'حالة الغطاء النباتي (منفصلة عن هذا المؤشر)', vegState: { below_normal: 'أقل من المعتاد', near_normal: 'قريبة من المعتاد', above_normal: 'أعلى من المعتاد' },
    vegNote: 'تظهر هنا للسياق فقط وليست مدخلًا في التوقع اليومي. التوقع متوسط المدى +16/+32 يوم يبقى في الصفحات الأخرى.',
    reasons: {
      soil_moisture_below_normal: 'رطوبة التربة أقل من المعتاد', soil_moisture_state: 'حالة رطوبة التربة',
      recent_rain_low: 'أمطار الفترة الأخيرة قليلة', recent_rain_state: 'أمطار الفترة الأخيرة',
      forecast_rain_low: 'أمطار متوقعة قليلة جدًا', forecast_rain_state: 'الأمطار المتوقعة',
      heat_elevated: 'حرارة أعلى من المعتاد', heat_state: 'درجات الحرارة المتوقعة',
      air_dryness_elevated: 'جفاف الهواء مرتفع (VPD)', air_dryness_state: 'جفاف الهواء (VPD)',
    },
    groups: { soil_moisture: 'رطوبة التربة', recent_rain: 'الأمطار الأخيرة', forecast_rain: 'الأمطار المتوقعة', heat: 'الحرارة', dryness: 'جفاف الهواء', air_dryness: 'جفاف الهواء' },
    banners: {
      synthetic: ['بيانات تجريبية', 'هذه معاينة للواجهة بأرقام اصطناعية وليست توقعًا حقيقيًا.'],
      notInitialized: ['التوقع اليومي غير مُفعّل بعد', 'لم يُنشأ أي توقع يومي بعد. التوقع متوسط المدى +16/+32 يوم ما زال متاحًا.'],
      unavailable: ['خدمة التوقع اليومي غير متاحة', 'لا نعرض أرقامًا بديلة. التوقع متوسط المدى +16/+32 يوم ما زال متاحًا.'],
      noData: ['لا توجد بيانات يومية لهذه الخلية', 'لم تتوفر مدخلات كافية لهذه الخلية.'],
      stale: ['البيانات متأخرة', 'آخر توقع أقدم من المعتاد أو من نسخة احتياطية. تحقق من وقت الإصدار قبل الاعتماد عليه.'],
      expired: ['التوقع منتهي الصلاحية', 'هذا التوقع قديم جدًا ولا يجب استخدامه لقرار. بانتظار التحديث التلقائي.'],
      invalidData: ['بيانات التوقع غير مكتملة', 'لم تعرض الواجهة أرقامًا لأن تسلسل اليوم إلى +٧ مفقود أو مكرر أو خارج النطاق.'],
    },
    nat: { eyebrow: 'ملخص الأردن اليومي', title: 'خطر الإجهاد البيئي في الأردن: اليوم و٧ أيام', mean: 'متوسط المؤشر', cells: 'خلية', note: 'مؤشر نسبي ٠–١٠٠ وليس احتمالًا. منفصل عن التوقع متوسط المدى +16/+32 يوم.', level: { Low: 'منخفض', Moderate: 'متوسط', High: 'مرتفع' }, issued: 'صدر', age: 'عمر اللقطة: {h} ساعة' },
    loading: 'جارٍ تحميل التوقع اليومي…',
  },
  en: {
    eyebrow: 'Daily forecast', title: 'Environmental Stress Risk: today and the next 7 days',
    intro: 'A relative 0–100 index of forecast atmospheric and hydrological stress for this cell. It is not a probability, not a vegetation measurement and not a field diagnosis.',
    today: 'Today', plusDay: '+{n} d', outOf: '/100', changeVsToday: 'Change vs today', noChange: 'No change',
    whyTitle: 'What is associated with this result?', whyNote: 'Model associations (TreeSHAP), not confirmed causes.',
    raises: 'Raises the index', lowers: 'Lowers the index', changeWhy: 'Why it differs from today', noReasons: 'No prominent factors for this day.',
    issued: 'Forecast snapshot generated', issueDay: 'Forecast reference day', forecastReference: 'Weather forecast reference time',
    weatherSrc: 'Weather forecast', weatherAge: 'Forecast age: {h} h', retrieved: 'Retrieved',
    obsSrc: 'Latest available observation', obsNote: 'Delayed observations or reanalysis are not real-time data.',
    satSrc: 'Latest available satellite observation', satNote: 'Composite and delayed observations are never shown as live data.', satNone: 'Not available',
    lastSuccess: 'Last successful update', servedFrom: 'Copy being served', servedLatest: 'Latest snapshot', servedFallback: 'Last-good fallback snapshot',
    model: 'Model version', confidence: 'Confidence and data quality',
    conf: { high: 'High', medium: 'Medium', low: 'Low', unknown: 'Unavailable' },
    confParts: { validated_skill: 'Validated model skill', input_completeness: 'Input completeness', freshness: 'Source freshness' },
    veg: 'Vegetation condition (separate from this index)', vegState: { below_normal: 'Below normal', near_normal: 'Near normal', above_normal: 'Above normal' },
    vegNote: 'Shown for context only; it is not an input to the daily forecast. The +16/+32-day medium-term outlook remains on the other pages.',
    reasons: {
      soil_moisture_below_normal: 'Soil moisture below normal', soil_moisture_state: 'Soil moisture state',
      recent_rain_low: 'Little recent rainfall', recent_rain_state: 'Recent rainfall',
      forecast_rain_low: 'Very little rain forecast', forecast_rain_state: 'Forecast rainfall',
      heat_elevated: 'Temperature above normal', heat_state: 'Forecast temperature',
      air_dryness_elevated: 'High air dryness (VPD)', air_dryness_state: 'Air dryness (VPD)',
    },
    groups: { soil_moisture: 'Soil moisture', recent_rain: 'Recent rain', forecast_rain: 'Forecast rain', heat: 'Heat', dryness: 'Air dryness', air_dryness: 'Air dryness' },
    banners: {
      synthetic: ['Demonstration data', 'This is a UI preview with synthetic numbers, not a real forecast.'],
      notInitialized: ['Daily forecast not enabled yet', 'No daily forecast has been generated yet. The +16/+32-day outlook is still available.'],
      unavailable: ['Daily forecast service unavailable', 'We do not show substitute numbers. The +16/+32-day outlook is still available.'],
      noData: ['No daily data for this cell', 'Not enough inputs were available for this cell.'],
      stale: ['Data is delayed', 'The latest forecast is older than usual or comes from a fallback copy. Check the issue time before relying on it.'],
      expired: ['Forecast expired', 'This forecast is too old to base a decision on. Waiting for the automatic refresh.'],
      invalidData: ['Forecast data is incomplete', 'No numbers are shown because the Today-to-+7 sequence is missing, duplicated or outside the valid range.'],
    },
    nat: { eyebrow: 'Jordan daily summary', title: 'Environmental Stress Risk across Jordan: today and the next 7 days', mean: 'Mean index', cells: 'cells', note: 'Relative 0–100 index, not a probability. Separate from the +16/+32-day medium-term outlook.', level: { Low: 'Low', Moderate: 'Moderate', High: 'High' }, issued: 'Issued', age: 'Snapshot age: {h} h' },
    loading: 'Loading the daily forecast…',
  },
}

export function dt(language, path, vars) {
  const walk = (obj) => path.split('.').reduce((o, k) => (o == null ? o : o[k]), obj)
  let text = walk(DAILY_COPY[language]) ?? walk(DAILY_COPY.en) ?? path
  if (vars) for (const [k, v] of Object.entries(vars)) text = String(text).replaceAll(`{${k}}`, v)
  return text
}
