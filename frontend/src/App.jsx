import React, { useEffect, useState } from 'react'
import { Route, Routes, useLocation } from 'react-router-dom'
import { useBadiaData } from './hooks/useBadiaData.js'
import { AppFooter, AppHeader } from './components/UI.jsx'
import Landing from './pages/Landing.jsx'
import Explorer from './pages/Explorer.jsx'
import CellDetails from './pages/CellDetails.jsx'
import Science from './pages/Science.jsx'
import ActionGuide from './pages/ActionGuide.jsx'

function ScrollToTop() {
  const { pathname } = useLocation()
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'instant' })
  }, [pathname])
  return null
}

export default function App() {
  const [horizon, setHorizon] = useState(() => Number(window.localStorage.getItem('badia-horizon')) || 16)
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const dashboard = useBadiaData(horizon)

  const changeHorizon = (value) => {
    setHorizon(value)
    window.localStorage.setItem('badia-horizon', String(value))
  }

  return (
    <div className="app-shell">
      <ScrollToTop />
      <AppHeader mobileNavOpen={mobileNavOpen} setMobileNavOpen={setMobileNavOpen} />
      <main id="main-content">
        <Routes>
          <Route path="/" element={<Landing {...dashboard} horizon={horizon} setHorizon={changeHorizon} />} />
          <Route path="/explorer" element={<Explorer {...dashboard} horizon={horizon} setHorizon={changeHorizon} />} />
          <Route path="/action" element={<ActionGuide />} />
          <Route path="/cells/:cellId" element={<CellDetails {...dashboard} horizon={horizon} setHorizon={changeHorizon} />} />
          <Route path="/science" element={<Science {...dashboard} horizon={horizon} setHorizon={changeHorizon} />} />
          <Route path="*" element={<Landing {...dashboard} horizon={horizon} setHorizon={changeHorizon} />} />
        </Routes>
      </main>
      <AppFooter />
    </div>
  )
}
