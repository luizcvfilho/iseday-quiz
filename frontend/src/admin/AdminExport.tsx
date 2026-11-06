import { useEffect, useRef, useState } from 'react'
import { Alert, Box, Button, Stack } from '@mui/material'
import { errorMessage } from '../api'
import { adminApi } from './api'
import { useAdmin } from './context'

export function AdminExport({ query, disabled }: { query: string; disabled: boolean }) {
  const { call } = useAdmin()
  const [exporting, setExporting] = useState<'csv' | 'xlsx' | null>(null)
  const [error, setError] = useState('')
  const active = useRef<AbortController | null>(null)
  useEffect(() => () => active.current?.abort(), [])

  async function exportReport(format: 'csv' | 'xlsx') {
    if (disabled || exporting) return
    setExporting(format)
    setError('')
    const controller = new AbortController()
    active.current = controller
    const params = new URLSearchParams(query)
    params.delete('page')
    params.delete('page_size')
    try {
      const blob = await call(() => adminApi.exportReport(format, params, controller.signal))
      if (controller.signal.aborted) return
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `participacoes-iseday.${format}`
      document.body.append(link)
      link.click()
      link.remove()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (e) {
      if (!controller.signal.aborted) setError(errorMessage(e))
    } finally {
      if (!controller.signal.aborted) setExporting(null)
    }
  }

  return (
    <Box sx={{ mb: 3 }}>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
        {(['csv', 'xlsx'] as const).map((format) => (
          <Button
            key={format}
            variant="outlined"
            disabled={disabled || exporting !== null}
            onClick={() => exportReport(format)}
          >
            {exporting === format
              ? 'Exportando…'
              : `Exportar resultados filtrados (${format.toUpperCase()})`}
          </Button>
        ))}
      </Stack>
      {error && (
        <Alert severity="error" sx={{ mt: 2 }}>
          {error}
        </Alert>
      )}
    </Box>
  )
}
