import React from 'react'
import { Link } from 'react-router-dom'
import { guidanceFor } from '../guidance.js'
import { useLanguage } from '../i18n.jsx'
import Icon from './Icons.jsx'
import { RiskPill } from './UI.jsx'

export default function ActionGuidance({ level = 'N/A', compact = false, showLink = true }) {
  const { language, t } = useLanguage()
  const guidance = guidanceFor(level, language)
  return (
    <article className={`action-guidance action-guidance--${String(level).toLowerCase().replace('/', '')} ${compact ? 'action-guidance--compact' : ''}`}>
      <div className="action-guidance__head">
        <span className="action-guidance__icon"><Icon name={level === 'High' ? 'alert' : level === 'N/A' ? 'info' : 'water'} size={21} /></span>
        <div><span className="eyebrow">{language === 'ar' ? 'الخطوة التالية' : 'Next step'}</span><h3>{guidance.title}</h3></div>
        <RiskPill level={level} small />
      </div>
      <p>{guidance.summary}</p>
      <ol>
        {guidance.steps.map((step) => <li key={step}><Icon name="check" size={16} /><span>{step}</span></li>)}
      </ol>
      <div className="action-guidance__caution"><Icon name="info" size={17} /><span>{guidance.caution}</span></div>
      {showLink && <Link className="text-link" to="/action">{t('action.openGuide')} <Icon name="arrow" size={16} /></Link>}
    </article>
  )
}
