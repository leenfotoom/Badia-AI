import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

const COPY = {
  ar: {
    skip: 'تجاوز إلى المحتوى',
    nav: { home: 'الرئيسية', explorer: 'خريطة المتابعة', action: 'ماذا نفعل؟', science: 'كيف يعمل؟' },
    status: 'عرض تاريخي',
    language: 'English',
    languageLabel: 'Switch to English',
    menuOpen: 'فتح القائمة',
    menuClose: 'إغلاق القائمة',
    footer: {
      purpose: 'أداة مساعدة لاتخاذ القرار ومتابعة الغطاء النباتي في الأردن.',
      note: 'بيانات أقمار صناعية · عرض تاريخي · لا يستبدل التحقق الميداني',
    },
    horizon: { label: 'الفترة القادمة', days: '+{value} يوم' },
    snapshot: {
      label: 'لقطة تاريخية متاحة · 2025',
      dateFallback: 'تاريخ اللقطة محفوظ مع البيانات',
      api: 'متصل بالبيانات المحلية',
      bundle: 'نسخة محلية محفوظة',
    },
    offline: {
      title: 'وضع العرض دون اتصال.',
      body: 'نعرض اللقطة التاريخية المحفوظة لأن خدمة البيانات المحلية غير متاحة حاليًا.',
      partialTitle: 'بعض مصادر الواجهة غير متاحة.',
      partialBody: 'تُعرض القيم المتاحة فقط، مع إبقاء القيم المفقودة واضحة بدل خلطها بلقطة أخرى.',
    },
    risk: { All: 'الكل', Low: 'منخفض', Moderate: 'متوسط', High: 'مرتفع', 'N/A': 'غير متاح' },
    summary: { mapped: 'خلايا متاحة', mean: 'متوسط المؤشر', high: 'خلايا ذات شدة مرتفعة' },
    states: {
      loading: 'جارٍ تحميل أحدث لقطة متاحة…',
      loadingSub: 'نجهّز طبقة المتابعة المحلية',
      error: 'تعذّر تحميل البيانات',
      errorHelp: 'تأكد أن النسخة المحلية تعمل وأن ملف البيانات المحفوظ متاح.',
      retry: 'حاول مرة أخرى',
      empty: 'لا توجد خلايا مطابقة',
      emptyHelp: 'البيانات موجودة، لكن لا توجد نتيجة تطابق البحث أو التصفية الحالية.',
    },
    map: {
      aria: 'خريطة تفاعلية لإشارات الإجهاد النباتي في الأردن',
      legend: 'مفتاح مستويات الشدة التاريخية',
      offlineNote: 'طبقة الخلايا تعمل محليًا · خريطة الخلفية تحتاج إنترنت',
      gridCell: 'خلية',
    },
    cell: {
      selected: 'الخلية المختارة',
      location: 'الموقع',
      id: 'معرّف الخلية',
      locationUnavailable: 'الموقع غير متاح',
      relativeIndex: 'مؤشر الشدة التاريخية — وليس احتمالًا',
      predictedAnomaly: 'التغير النباتي المتوقع',
      horizon: 'الفترة',
      leadingSignal: 'أبرز مدخل أثّر في النموذج',
      open: 'افتح تفاصيل الخلية',
    },
    quality: {
      title: 'جودة البيانات',
      Good: 'جيدة',
      Fair: 'متوسطة',
      Partial: 'جزئية',
      Limited: 'محدودة',
      Poor: 'ضعيفة',
      'Not reported': 'غير مذكورة',
      completeness: 'اكتمال المدخلات {value}.',
      noCompleteness: 'نسبة الاكتمال غير متاحة.',
      missing: ' حقول ناقصة: {fields}.',
      noMissing: ' لا توجد حقول ناقصة مسجلة.',
    },
    factor: {
      unavailable: 'تفاصيل العوامل غير متاحة لهذه اللقطة.',
      generic: 'إشارة من مدخلات النموذج',
      raisesRisk: 'يدفع توقع النموذج نحو إشارة إجهاد أعلى',
      lowersRisk: 'يدفع توقع النموذج نحو إشارة إجهاد أقل',
    },
    metrics: {
      validation: 'التحقق · 2023',
      test: 'الاختبار النهائي · 2024–2025',
      model: 'XGBoost',
      baseline: 'الاستمرار كما هو',
      lowerBetter: 'متوسط الخطأ · الأقل أفضل',
    },
    action: {
      openGuide: 'افتح دليل التصرّف',
      historical: 'هذه لقطة تاريخية للتوضيح. عند الاستخدام التشغيلي، طبّق الخطوات على بيانات حديثة وبعد تحقق ميداني.',
    },
  },
  en: {
    skip: 'Skip to content',
    nav: { home: 'Home', explorer: 'Priority map', action: 'What to do', science: 'How it works' },
    status: 'Historical demo',
    language: 'العربية',
    languageLabel: 'التبديل إلى العربية',
    menuOpen: 'Open navigation',
    menuClose: 'Close navigation',
    footer: {
      purpose: 'Decision-support for responsible vegetation monitoring in Jordan.',
      note: 'Satellite-derived · Historical demo · Field verification required',
    },
    horizon: { label: 'Look-ahead', days: '+{value} days' },
    snapshot: {
      label: 'Available historical snapshot · 2025',
      dateFallback: 'Snapshot date is stored with the dataset',
      api: 'Connected to local data',
      bundle: 'Saved local copy',
    },
    offline: {
      title: 'Offline demo mode.',
      body: 'Showing the saved historical snapshot because the local data service is currently unavailable.',
      partialTitle: 'Some interface data sources are unavailable.',
      partialBody: 'Only available values are shown; missing values remain explicit instead of being mixed with another snapshot.',
    },
    risk: { All: 'All', Low: 'Low', Moderate: 'Moderate', High: 'High', 'N/A': 'N/A' },
    summary: { mapped: 'Available cells', mean: 'Mean index', high: 'High-severity cells' },
    states: {
      loading: 'Loading the latest available snapshot…',
      loadingSub: 'Preparing the local monitoring layer',
      error: 'Data could not be loaded',
      errorHelp: 'Check that the local demo is running and the saved data file is available.',
      retry: 'Try again',
      empty: 'No matching cells',
      emptyHelp: 'The data loaded, but no result matches the current search or filter.',
    },
    map: {
      aria: 'Interactive map of vegetation-stress signals across Jordan',
      legend: 'Historical severity-level legend',
      offlineNote: 'Cell layer works locally · basemap needs internet',
      gridCell: 'Grid cell',
    },
    cell: {
      selected: 'Selected cell',
      location: 'Location',
      id: 'Cell ID',
      locationUnavailable: 'Location unavailable',
      relativeIndex: 'Historical severity index — not a probability',
      predictedAnomaly: 'Predicted vegetation change',
      horizon: 'Look-ahead',
      leadingSignal: 'Leading model input',
      open: 'Open cell details',
    },
    quality: {
      title: 'Data quality',
      Good: 'Good',
      Fair: 'Fair',
      Partial: 'Partial',
      Limited: 'Limited',
      Poor: 'Poor',
      'Not reported': 'Not reported',
      completeness: '{value} input completeness.',
      noCompleteness: 'Completeness percentage was not supplied.',
      missing: ' Missing fields: {fields}.',
      noMissing: ' No missing fields were reported.',
    },
    factor: {
      unavailable: 'Factor details were not available for this snapshot.',
      generic: 'Model input signal',
      raisesRisk: 'Pushes the model toward a stronger stress signal',
      lowersRisk: 'Pushes the model toward a weaker stress signal',
    },
    metrics: {
      validation: 'Validation · 2023',
      test: 'Final test · 2024–2025',
      model: 'XGBoost',
      baseline: 'Persistence',
      lowerBetter: 'Mean error · lower is better',
    },
    action: {
      openGuide: 'Open the action guide',
      historical: 'This is a historical demonstration snapshot. In operations, apply the steps to current data and verify conditions in the field.',
    },
  },
}

const FEATURE_NAMES = {
  ar: {
    ndvi: 'حالة الغطاء النباتي الحالية',
    ndvi_anomaly_current: 'الانحراف الموسمي الحالي للغطاء النباتي',
    rain_16d_mm: 'الأمطار خلال 16 يومًا',
    rain_30d_mm: 'الأمطار خلال 30 يومًا',
    rain_90d_mm: 'الأمطار خلال 90 يومًا',
    temperature_30d_c: 'متوسط الحرارة خلال 30 يومًا',
    soil_moisture_30d: 'رطوبة التربة خلال 30 يومًا',
    period_sin: 'التوقيت داخل الموسم',
    period_cos: 'التوقيت داخل الموسم',
    latitude: 'الموقع شمالًا',
    longitude: 'الموقع شرقًا',
    area_km2: 'مساحة الخلية',
  },
  en: {
    ndvi: 'Current vegetation condition',
    ndvi_anomaly_current: 'Current seasonal vegetation anomaly',
    rain_16d_mm: 'Rainfall over 16 days',
    rain_30d_mm: 'Rainfall over 30 days',
    rain_90d_mm: 'Rainfall over 90 days',
    temperature_30d_c: 'Temperature over 30 days',
    soil_moisture_30d: 'Soil moisture over 30 days',
    period_sin: 'Seasonal timing',
    period_cos: 'Seasonal timing',
    latitude: 'Latitude',
    longitude: 'Longitude',
    area_km2: 'Cell area',
  },
}

function readPath(object, path) {
  return path.split('.').reduce((value, key) => value?.[key], object)
}

function interpolate(value, variables = {}) {
  return String(value).replace(/\{(\w+)\}/g, (_, key) => variables[key] ?? `{${key}}`)
}

const LanguageContext = createContext(null)

export function LanguageProvider({ children }) {
  const [language, setLanguageState] = useState(() => (
    window.localStorage.getItem('badia-language') === 'en' ? 'en' : 'ar'
  ))

  const setLanguage = useCallback((next) => {
    const safe = next === 'en' ? 'en' : 'ar'
    setLanguageState(safe)
    window.localStorage.setItem('badia-language', safe)
  }, [])

  useEffect(() => {
    document.documentElement.lang = language
    document.documentElement.dir = language === 'ar' ? 'rtl' : 'ltr'
    document.title = language === 'ar'
      ? 'بادية AI · متابعة الإجهاد النباتي في الأردن'
      : 'BADIA AI · Jordan Vegetation Monitoring'
  }, [language])

  const value = useMemo(() => {
    const t = (key, variables) => interpolate(readPath(COPY[language], key) ?? readPath(COPY.en, key) ?? key, variables)
    const riskLabel = (level = 'N/A') => COPY[language].risk[level] ?? level
    const featureLabel = (feature, fallback) => {
      const key = String(feature ?? '').trim().toLowerCase()
      return FEATURE_NAMES[language][key] ?? fallback ?? String(feature ?? (language === 'ar' ? 'عامل' : 'Factor'))
    }
    const directionLabel = (direction) => {
      const normalized = String(direction ?? '').toLowerCase()
      if (normalized.includes('raises relative risk') || normalized.includes('lowers predicted anomaly')) return t('factor.raisesRisk')
      if (normalized.includes('lowers relative risk') || normalized.includes('raises predicted anomaly')) return t('factor.lowersRisk')
      return direction || t('factor.generic')
    }
    return {
      language,
      isArabic: language === 'ar',
      locale: language === 'ar' ? 'ar-JO' : 'en-GB',
      setLanguage,
      toggleLanguage: () => setLanguage(language === 'ar' ? 'en' : 'ar'),
      t,
      riskLabel,
      featureLabel,
      directionLabel,
    }
  }, [language, setLanguage])

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>
}

export function useLanguage() {
  const value = useContext(LanguageContext)
  if (!value) throw new Error('useLanguage must be used inside LanguageProvider')
  return value
}
