import { useEffect, useRef, useState } from 'react'
import { Alert, Box, Button } from '@mui/material'
import { errorMessage } from '../api'
import { adminApi } from './api'
import { useAdmin } from './context'

export function AdminExport({ query, disabled }: { query: string; disabled: boolean }) {
  const { call } = useAdmin()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const active = useRef<AbortController | null>(null)
  useEffect(() => () => active.current?.abort(), [])
  return (
    <Box sx={{ mb: 3 }}>
      <Button
        variant="outlined"
        disabled={disabled || busy}
        onClick={async () => {
          if (busy) return
          setBusy(true)
          setError('')
          const controller = new AbortController()
          active.current = controller
          const params = new URLSearchParams(query)
          params.delete('page')
          params.delete('page_size')
          try {
            const blob = await call(() => adminApi.exportCsv(params, controller.signal))
            if (controller.signal.aborted) return
            const url = URL.createObjectURL(blob)
            const link = document.createElement('a')
            link.href = url
            link.download = 'participacoes-iseday.csv'
            document.body.append(link)
            link.click()
            link.remove()
            window.setTimeout(() => URL.revokeObjectURL(url), 1000)
          } catch (e) {
            if (!controller.signal.aborted) setError(errorMessage(e))
          } finally {
            if (!controller.signal.aborted) setBusy(false)
          }
        }}
      >
        {busy ? 'Exportando…' : 'Exportar resultados filtrados (CSV)'}
      </Button>
      {error && (
        <Alert severity="error" sx={{ mt: 2 }}>
          {error}
        </Alert>
      )}
    </Box>
  )
}
