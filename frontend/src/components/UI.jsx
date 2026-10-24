import React from 'react'
import { Link, NavLink, useLocation } from 'react-router-dom'
import { RISK_COLORS, RISK_LABELS } from '../constants.js'
import {
  displayFeatureName,
  formatAnomaly,
  formatCount,
  formatDate,
  formatDecimal,
  formatPercent,
  formatScore,
  metricFor,
} from '../format.js'
import { useLanguage } from '../i18n.jsx'
import { cellLocationLabel } from '../location.js'
import Icon, { BrandMark } from './Icons.jsx'
import PriorityInfo from './PriorityInfo.jsx'

export function AppHeader({ mobileNavOpen, setMobileNavOpen }) {
  const location = useLocation()
  const { t, toggleLanguage } = useLanguage()
  const navItems = [
    { to: '/', label: t('nav.home'), icon: 'home' },
    { to: '/explorer', label: t('nav.explorer'), icon: 'map' },
    { to: '/action', label: t('nav.action'), icon: 'water' },
    { to: '/science', label: t('nav.science'), icon: 'science' },
  ]

  return (
    <>
      <a className="skip-link" href="#main-content">{t('skip')}</a>
      <header className="app-header">
        <Link className="brand" to="/" aria-label="BADIA AI">
          <BrandMark compact />
        </Link>
        <nav className={`main-nav ${mobileNavOpen ? 'main-nav--open' : ''}`} aria-label={t('menuOpen')}>
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) => (isActive ? 'nav-link nav-link--active' : 'nav-link')}
              onClick={() => setMobileNavOpen(false)}
            >
              <Icon name={item.icon} size={17} />
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="header-actions">
          <div className="header-meta"><span className="status-dot" />{t('status')}</div>
          <button className="language-toggle" type="button" onClick={toggleLanguage} aria-label={t('languageLabel')}>
            <Icon name="language" size={17} /> {t('language')}
          </button>
          <button
            className="menu-button"
            type="button"
            aria-expanded={mobileNavOpen}
            aria-label={mobileNavOpen ? t('menuClose') : t('menuOpen')}
            onClick={() => setMobileNavOpen((value) => !value)}
          >
            <Icon name={mobileNavOpen ? 'close' : 'menu'} />
          </button>
        </div>
        {mobileNavOpen && location.pathname && (
          <button className="nav-scrim" type="button" aria-label={t('menuClose')} onClick={() => setMobileNavOpen(false)} />
        )}
      </header>
    </>
  )
}

export function AppFooter() {
  const { t } = useLanguage()
  return (
    <footer className="app-footer">
      <div className="footer-brand" aria-label="BADIA AI"><BrandMark compact /></div>
      <p>{t('footer.purpose')}</p>
      <span>{t('footer.note')}</span>
    </footer>
  )
}

export function HorizonToggle({ horizon, onChange, compact = false }) {
  const { t } = useLanguage()
  return (
    <div className={`horizon-toggle ${compact ? 'horizon-toggle--compact' : ''}`} role="group" aria-label={t('horizon.label')}>
      <span className="horizon-toggle__label">{t('horizon.label')}</span>
      {[16, 32].map((value) => (
        <button type="button" key={value} className={horizon === value ? 'is-active' : ''} aria-pressed={horizon === value} onClick={() => onChange(value)}>
          {t('horizon.days', { value })}
        </button>
      ))}
    </div>
  )
}

export function SnapshotBadge({ area, source }) {
  const { t, locale } = useLanguage()
  const date = formatDate(area?.snapshot_date, locale)
  return (
    <div className="snapshot-badge">
      <Icon name="calendar" size={17} />
      <span>
        <strong>{t('snapshot.label')}</strong>
        <small>{date || t('snapshot.dateFallback')} · {source === 'bundle' ? t('snapshot.bundle') : t('snapshot.api')}</small>
      </span>
    </div>
  )
}

export function SourceNotice({ source }) {
  const { t } = useLanguage()
  if (source !== 'bundle' && source !== 'api-partial') return null
  const partial = source === 'api-partial'
  return (
    <div className="source-notice" role="status">
      <Icon name="offline" size={18} />
      <span><strong>{t(partial ? 'offline.partialTitle' : 'offline.title')}</strong> {t(partial ? 'offline.partialBody' : 'offline.body')}</span>
    </div>
  )
}

export function RiskPill({ level = 'N/A', small = false }) {
  const { riskLabel } = useLanguage()
  const safeLevel = RISK_COLORS[level] ? level : 'N/A'
  return (
    <span className={`risk-pill ${small ? 'risk-pill--small' : ''}`} style={{ '--risk-color': RISK_COLORS[safeLevel] }}>
      <i /> {riskLabel(safeLevel)}
    </span>
  )
}

export function RiskLegend({ counts, vertical = false }) {
  const { riskLabel, locale, t } = useLanguage()
  return (
    <div className={`risk-legend ${vertical ? 'risk-legend--vertical' : ''}`} aria-label={t('map.legend')}>
      {RISK_LABELS.map((level) => {
        const key = level === 'N/A' ? 'na_count' : `${level.toLowerCase()}_count`
        return (
          <span key={level}>
            <i style={{ background: RISK_COLORS[level] }} />
            {riskLabel(level)}
            {counts && <b>{formatCount(counts[key], locale)}</b>}
          </span>
        )
      })}
    </div>
  )
}

export function SummaryCards({ summary = {} }) {
  const { t, locale } = useLanguage()
  const cards = [
    { label: t('summary.mapped'), value: formatCount(summary.available_cells, locale), icon: 'layers' },
    { label: t('summary.mean'), value: formatScore(summary.mean_risk_score), icon: 'chart', accent: true },
    { label: t('summary.high'), value: formatCount(summary.high_count, locale), icon: 'location', danger: true },
  ]
  return (
    <div className="summary-cards">
      {cards.map((card) => (
        <article className={`summary-card ${card.accent ? 'summary-card--accent' : ''} ${card.danger ? 'summary-card--danger' : ''}`} key={card.label}>
          <span className="summary-card__icon"><Icon name={card.icon} size={18} /></span>
          <span><small>{card.label}</small><strong>{card.value}</strong></span>
        </article>
      ))}
    </div>
  )
}

export function LoadingState({ label, full = false }) {
  const { t } = useLanguage()
  return (
    <div className={`state-card state-card--loading ${full ? 'state-card--full' : ''}`} role="status">
      <span className="loader-orbit"><i /></span>
      <strong>{label || t('states.loading')}</strong>
      <small>{t('states.loadingSub')}</small>
    </div>
  )
}

export function ErrorState({ message, onRetry, compact = false }) {
  const { t } = useLanguage()
  return (
    <div className={`state-card state-card--error ${compact ? 'state-card--compact' : ''}`} role="alert">
      <span className="state-card__icon"><Icon name="offline" size={24} /></span>
      <strong>{t('states.error')}</strong>
      <p>{message || t('states.errorHelp')}</p>
      {onRetry && <button className="button button--secondary" type="button" onClick={onRetry}>{t('states.retry')}</button>}
    </div>
  )
}

export function EmptyState() {
  const { t } = useLanguage()
  return (
    <div className="state-card" role="status">
      <span className="state-card__icon"><Icon name="map" size={24} /></span>
      <strong>{t('states.empty')}</strong>
      <p>{t('states.emptyHelp')}</p>
    </div>
  )
}

export function CellSnapshot({ cell, link = true }) {
  const { t, featureLabel, language } = useLanguage()
  if (!cell) return null
  const properties = cell.properties
  const factor = properties.top_factors?.[0]
  const location = cellLocationLabel(properties, language) ?? t('cell.locationUnavailable')
  return (
    <article className="cell-snapshot">
      <div className="cell-snapshot__head"><span className="eyebrow">{t('cell.selected')}</span><RiskPill level={properties.risk_level} /></div>
      <div className="cell-location">
        <span className="cell-location__label"><Icon name="location" size={15} /> {t('cell.location')}</span>
        <h2>{location}</h2>
        <p className="cell-location__id">{t('cell.id')} <b dir="ltr">{properties.cell_id}</b></p>
      </div>
      <p className="coordinate-line"><Icon name="location" size={15} />{properties.lat?.toFixed(4) ?? '—'}, {properties.lon?.toFixed(4) ?? '—'}</p>
      <div className="score-display" style={{ '--risk-color': RISK_COLORS[properties.risk_level] ?? RISK_COLORS['N/A'] }}>
        <span><strong>{formatScore(properties.risk_score)}</strong><small>/ 100</small></span>
        <div className="score-display__track">{Number.isFinite(properties.risk_score) && <i style={{ width: `${Math.max(0, Math.min(100, properties.risk_score))}%` }} />}</div>
        <p>{t('cell.relativeIndex')}</p>
      </div>
      <PriorityInfo properties={properties} compact />
      <dl className="compact-facts">
        <div><dt>{t('cell.predictedAnomaly')}</dt><dd>{formatAnomaly(properties.predicted_anomaly)}</dd></div>
        <div><dt>{t('cell.horizon')}</dt><dd>{t('horizon.days', { value: properties.horizon_days })}</dd></div>
      </dl>
      {factor && <div className="factor-preview"><small>{t('cell.leadingSignal')}</small><strong>{featureLabel(factor.feature, factor.display_name)}</strong></div>}
      {link && (
        <Link className="text-link" to={`/cells/${encodeURIComponent(properties.cell_id)}?horizon=${properties.horizon_days}`}>
          {t('cell.open')} <Icon name="arrow" size={16} />
        </Link>
      )}
    </article>
  )
}

export function FactorList({ factors = [] }) {
  const { t, featureLabel, directionLabel } = useLanguage()
  if (!factors.length) return <p className="muted-copy">{t('factor.unavailable')}</p>
  return (
    <ol className="factor-list">
      {factors.map((factor, index) => (
        <li key={`${factor.feature}-${index}`}>
          <span className="factor-rank">0{index + 1}</span>
          <span>
            <strong>{featureLabel(factor.feature, factor.display_name || displayFeatureName(factor.feature))}</strong>
            <small>{directionLabel(factor.direction)}</small>
          </span>
          <b>{typeof factor.value === 'number' ? formatDecimal(factor.value, Math.abs(factor.value) < 0.1 ? 4 : 2) : factor.value ?? '—'}</b>
        </li>
      ))}
    </ol>
  )
}

export function QualityPanel({ quality = {} }) {
  const { t, featureLabel } = useLanguage()
  const completeness = Number(quality.completeness_pct)
  const hasCompleteness = Number.isFinite(completeness)
  const rawStatus = quality.status || (hasCompleteness && completeness >= 80 ? 'Good' : 'Not reported')
  const status = t(`quality.${rawStatus}`)
  const missing = Array.isArray(quality.missing_fields) ? quality.missing_fields : []
  return (
    <div className="quality-panel">
      <span className="quality-panel__icon"><Icon name="quality" size={21} /></span>
      <div>
        <span className="eyebrow">{t('quality.title')}</span>
        <strong>{status}</strong>
        <p>
          {hasCompleteness ? t('quality.completeness', { value: formatPercent(completeness, 0) }) : t('quality.noCompleteness')}
          {missing.length ? t('quality.missing', { fields: missing.map((field) => featureLabel(field)).join('، ') }) : t('quality.noMissing')}
        </p>
      </div>
    </div>
  )
}

export function MetricComparison({ metrics, horizon, compact = false }) {
  const { t } = useLanguage()
  const metric = metricFor(metrics, horizon)
  if (!metric) return null
  return (
    <div className={`metric-comparison ${compact ? 'metric-comparison--compact' : ''}`}>
      {['validation', 'test'].map((split) => {
        const values = metric[split]
        return (
          <article key={split}>
            <div className="metric-comparison__title"><span>{t(`metrics.${split}`)}</span><strong>↓ {formatPercent(values?.improvement_pct)}</strong></div>
            <div className="metric-bars">
              <span><small>{t('metrics.model')}</small><i className="metric-bars__model" style={{ width: `${Math.min(100, (values?.model_mae / values?.baseline_mae) * 100 || 0)}%` }} /><b>{formatDecimal(values?.model_mae, 6)}</b></span>
              <span><small>{t('metrics.baseline')}</small><i className="metric-bars__baseline" style={{ width: '100%' }} /><b>{formatDecimal(values?.baseline_mae, 6)}</b></span>
            </div>
          </article>
        )
      })}
    </div>
  )
}
