import { useCallback, useEffect, useState } from 'react'
import { errorMessage, request } from '../api'
import { useAdmin } from './context'

export function useResource<T>(path: string) {
  const { call } = useAdmin()
  const [revision, setRevision] = useState(0)
  const key = `${path}:${revision}`
  const [response, setResponse] = useState<{ key: string; data?: T; error?: string } | null>(
    null,
  )
  const reload = useCallback(() => setRevision((v) => v + 1), [])
  useEffect(() => {
    const controller = new AbortController()
    void call(() => request<T>(path, undefined, controller.signal))
      .then((data) => {
        if (!controller.signal.aborted) setResponse({ key, data })
      })
      .catch((error) => {
        if (!controller.signal.aborted) setResponse({ key, error: errorMessage(error) })
      })
    return () => controller.abort()
  }, [call, path, key])
  const current = response?.key === key ? response : null
  return { data: current?.data, error: current?.error, loading: current === null, reload }
}
