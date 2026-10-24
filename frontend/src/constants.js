export const JORDAN_BOUNDS = [
  [29.05, 34.82],
  [33.4, 39.35],
]

export const RISK_COLORS = {
  Low: '#4fd1aa',
  Moderate: '#f2b84b',
  High: '#ef725f',
  'N/A': '#7f899d',
}

export const RISK_LABELS = ['Low', 'Moderate', 'High', 'N/A']

export const PUBLISHED_METRICS = {
  model_name: 'XGBoost',
  evaluation_protocol: 'Train 2015–2022 · validate 2023 · final test 2024–2025',
  horizons: {
    16: {
      validation: { model_mae: 0.005072, baseline_mae: 0.005446, improvement_pct: 6.9 },
      test: { model_mae: 0.004711, baseline_mae: 0.00484, improvement_pct: 2.7 },
    },
    32: {
      validation: { model_mae: 0.006047, baseline_mae: 0.006907, improvement_pct: 12.4 },
      test: { model_mae: 0.005536, baseline_mae: 0.006193, improvement_pct: 10.6 },
    },
  },
}

export const DEFAULT_METADATA = {
  project_name: 'BADIA AI',
  snapshot_label: 'Latest available historical demo',
  data_period: '2015–2025',
  source: 'Satellite-derived vegetation and environmental observations',
  risk_definition:
    'A transparent 0–100 index that ranks predicted vegetation anomaly severity against the relevant historical seasonal distribution.',
  disclaimer:
    'This is a satellite-derived vegetation anomaly risk indicator. It is not a field diagnosis of desertification, a causal claim, or a live forecast.',
}

export const API_BASE = (import.meta.env?.VITE_API_BASE_URL || '/api').replace(/\/$/, '')
