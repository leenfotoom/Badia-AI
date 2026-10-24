import { useCallback, useEffect, useState } from 'react'
import { loadCell, loadDashboard } from '../api.js'

const dashboardCache = new Map()

export function useBadiaData(horizon) {
  const [state, setState] = useState(() => ({
    horizon,
    data: dashboardCache.get(horizon) ?? null,
    loading: !dashboardCache.has(horizon),
    error: null,
  }))
  const [revision, setRevision] = useState(0)

  useEffect(() => {
    let active = true
    const cached = dashboardCache.get(horizon)
    if (cached) {
      setState({ horizon, data: cached, loading: false, error: null })
      return () => {
        active = false
      }
    }

    // Never present the previous horizon under the newly selected +16/+32
    // label while the matching dataset is still loading.
    setState({ horizon, data: null, loading: true, error: null })
    loadDashboard(horizon)
      .then((data) => {
        if (!active) return
        dashboardCache.set(horizon, data)
        setState({ horizon, data, loading: false, error: null })
      })
      .catch((error) => {
        if (!active) return
        setState({ horizon, data: null, loading: false, error })
      })

    return () => {
      active = false
    }
  }, [horizon, revision])

  const refresh = useCallback(() => {
    dashboardCache.delete(horizon)
    setState({ horizon, data: null, loading: true, error: null })
    setRevision((value) => value + 1)
  }, [horizon])

  const visibleState = state.horizon === horizon
    ? state
    : {
        horizon,
        data: dashboardCache.get(horizon) ?? null,
        loading: !dashboardCache.has(horizon),
        error: null,
      }

  return { ...visibleState, refresh }
}

export function useCellDetails(cellId, horizon, localCells) {
  const [state, setState] = useState({ cell: null, loading: true })

  useEffect(() => {
    let active = true
    setState({ cell: null, loading: true })
    loadCell(cellId, horizon, localCells).then((cell) => {
      if (active) setState({ cell, loading: false })
    })
    return () => {
      active = false
    }
  }, [cellId, horizon, localCells])

  return state
}
