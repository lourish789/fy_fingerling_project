import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../lib/api'

export interface ApiState<T> {
  data: T | null
  error: ApiError | null
  loading: boolean
  /** True while refetching with data already on screen. */
  refreshing: boolean
  reload: () => void
  setData: (updater: (prev: T | null) => T | null) => void
}

/**
 * GET a backend path and keep it in state: loading skeleton first, stale data
 * kept on screen during reloads, retry on demand. `path = null` skips the call.
 */
export function useApi<T>(path: string | null): ApiState<T> {
  const [data, setDataState] = useState<T | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [loading, setLoading] = useState(!!path)
  const [refreshing, setRefreshing] = useState(false)
  const [nonce, setNonce] = useState(0)
  const hasData = useRef(false)

  useEffect(() => {
    if (!path) { setLoading(false); return }
    const ctrl = new AbortController()
    if (hasData.current) setRefreshing(true)
    else setLoading(true)
    setError(null)
    api<T>(path, { signal: ctrl.signal })
      .then((d) => { hasData.current = true; setDataState(d) })
      .catch((e) => {
        if (ctrl.signal.aborted) return
        setError(e instanceof ApiError ? e : new ApiError(String(e), 0, 'unknown'))
      })
      .finally(() => { if (!ctrl.signal.aborted) { setLoading(false); setRefreshing(false) } })
    return () => ctrl.abort()
  }, [path, nonce])

  const reload = useCallback(() => setNonce((n) => n + 1), [])
  const setData = useCallback((u: (prev: T | null) => T | null) => setDataState((p) => u(p)), [])
  return { data, error, loading, refreshing, reload, setData }
}
