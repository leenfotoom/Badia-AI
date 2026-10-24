export const GUIDANCE_SOURCES = [
  {
    labelAr: 'سياسة قطاع المياه لإدارة الجفاف — وزارة المياه والري',
    labelEn: 'Water Sector Policy for Drought Management — Ministry of Water and Irrigation',
    url: 'https://mwi.gov.jo/ebv4.0/root_storage/ar/eb_list_page/water_sector_policy_for_drought_management-0.pdf',
  },
  {
    labelAr: 'الاستراتيجية الوطنية للمياه 2023–2040',
    labelEn: 'Jordan National Water Strategy 2023–2040',
    url: 'https://www.mwi.gov.jo/EBV4.0/Root_Storage/AR/EB_List_Page/national_water_strategy_2023-2040.pdf',
  },
  {
    labelAr: 'استخدام أذكى للمياه في الأردن — منظمة الأغذية والزراعة',
    labelEn: 'Smarter water use in Jordan — FAO',
    url: 'https://www.fao.org/jordan/news/detail/smart-investments-and-smarter-water-use-in-jordan/en',
  },
]

const GUIDANCE = {
  ar: {
    Low: {
      title: 'متابعة اعتيادية',
      summary: 'الإشارة منخفضة نسبيًا. حافظ على المتابعة وكفاءة استخدام المياه، ولا تعتبر الدرجة ضمانًا لعدم وجود مشكلة محلية.',
      steps: [
        'استمر في المتابعة الدورية وقارن الاتجاه مع التحديث التالي.',
        'حافظ على ممارسات توفير المياه وافحص أي فاقد ظاهر.',
        'سجّل أي ملاحظة ميدانية غير متوافقة مع الخريطة.',
      ],
      caution: 'لا توقف المتابعة لأن المؤشر منخفض؛ الظروف المحلية قد تختلف داخل الخلية.',
    },
    Moderate: {
      title: 'تحقق أقرب',
      summary: 'هناك إشارة تستحق الانتباه. راجع المطر ورطوبة التربة والري قبل اتخاذ قرار.',
      steps: [
        'راجع أحدث معلومات المطر ورطوبة التربة وجدول الري.',
        'خطّط لفحص ميداني للمواقع الحساسة أو الأعلى قيمة.',
        'افحص التسرب وانتظام توزيع المياه وجهّز إجراءً تصحيحيًا بسيطًا.',
      ],
      caution: 'لا تغيّر كمية الري اعتمادًا على المؤشر وحده؛ تحقق من التربة والمحصول ومصدر المياه.',
    },
    High: {
      title: 'أولوية تحقق مرتفعة',
      summary: 'الإشارة قوية مقارنة بالموسم التاريخي. ابدأ بالتحقق الميداني ووجّه المتابعة للموقع أولًا.',
      steps: [
        'قارن الإشارة مع آخر مطر، رطوبة التربة، وموعد الري الفعلي.',
        'افحص علامات الإجهاد والتسرب وعدم انتظام الري على الأرض.',
        'رتّب الدعم للمناطق الحساسة ونسّق مع الفريق الزراعي أو المائي ثم وثّق النتيجة.',
      ],
      caution: 'الدرجة المرتفعة ليست تشخيص جفاف ولا أمرًا تلقائيًا بزيادة الري.',
    },
    'N/A': {
      title: 'لا توجد إشارة كافية',
      summary: 'المدخل النباتي الأساسي غير متاح، لذلك لا يمكن ترتيب أولوية موثوقة لهذه الخلية.',
      steps: [
        'تحقق من سبب نقص البيانات وجودة المشهد الفضائي.',
        'استخدم مصدر مشاهدة بديل أو زيارة ميدانية عند أهمية الموقع.',
        'أعد التقييم عند وصول لقطة صالحة بدل افتراض أن الخطر منخفض.',
      ],
      caution: 'غير متاح لا تعني منخفض.',
    },
  },
  en: {
    Low: {
      title: 'Routine monitoring',
      summary: 'The relative signal is low. Keep monitoring and using water efficiently; the score does not rule out a local issue.',
      steps: [
        'Continue routine monitoring and compare the trend with the next update.',
        'Maintain water-saving practices and inspect any visible losses.',
        'Record field observations that do not match the map.',
      ],
      caution: 'Do not stop monitoring because the index is low; conditions can vary within a cell.',
    },
    Moderate: {
      title: 'Check more closely',
      summary: 'The signal deserves attention. Review rainfall, soil moisture and irrigation before deciding on an intervention.',
      steps: [
        'Review the latest rainfall, soil-moisture and irrigation information.',
        'Plan a field check for sensitive or high-value locations.',
        'Inspect leakage and distribution uniformity, then prepare a proportionate correction.',
      ],
      caution: 'Do not change irrigation volume from the index alone; verify soil, crop and supply conditions.',
    },
    High: {
      title: 'High verification priority',
      summary: 'The signal is strong relative to the historical season. Verify conditions and prioritize this location for review.',
      steps: [
        'Compare the signal with recent rain, soil moisture and actual irrigation timing.',
        'Check plants, leakage and irrigation uniformity on the ground.',
        'Prioritize sensitive areas, coordinate with water or agriculture teams, and record the outcome.',
      ],
      caution: 'A high score is not a drought diagnosis or an automatic instruction to increase irrigation.',
    },
    'N/A': {
      title: 'Not enough signal',
      summary: 'A core vegetation input is unavailable, so this cell cannot receive a reliable priority level.',
      steps: [
        'Check why the data is missing and review image quality.',
        'Use another observation source or a field visit when the location matters.',
        'Reassess when a valid snapshot arrives instead of assuming low risk.',
      ],
      caution: 'Unavailable does not mean low.',
    },
  },
}

export function guidanceFor(level, language = 'ar') {
  const safeLanguage = language === 'en' ? 'en' : 'ar'
  const safeLevel = GUIDANCE[safeLanguage][level] ? level : 'N/A'
  return GUIDANCE[safeLanguage][safeLevel]
}
