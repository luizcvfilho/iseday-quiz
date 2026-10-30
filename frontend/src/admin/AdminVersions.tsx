import { useState } from 'react'
import { Link, useNavigate } from 'react-router'
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { errorMessage } from '../api'
import { adminApi, dateTime, versionStatus } from './api'
import type { QuizVersion } from './api'
import { useAdmin } from './context'
import { useResource } from './useResource'

export function AdminVersions() {
  const resource = useResource<QuizVersion[]>('/admin/versions')
  const { call } = useAdmin()
  const navigate = useNavigate()
  const [form, setForm] = useState<{ name: string; source: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  return (
    <>
      <Stack
        direction="row"
        sx={{ justifyContent: 'space-between', gap: 2, flexWrap: 'wrap', mb: 3 }}
      >
        <Box>
          <Typography component="h1" variant="h3">
            Versões do quiz
          </Typography>
          <Typography color="text.secondary" sx={{ mt: 1 }}>
            Prepare os destinos, confira o catálogo e publique a versão do evento.
          </Typography>
        </Box>
        <Button
          variant="contained"
          onClick={() => {
            setError('')
            setForm({ name: 'ISE Day', source: '' })
          }}
        >
          Criar versão
        </Button>
      </Stack>
      {resource.error && (
        <Alert
          severity="error"
          action={
            <Button color="inherit" onClick={resource.reload}>
              Tentar novamente
            </Button>
          }
        >
          {resource.error}
        </Alert>
      )}
      {resource.loading && <Typography role="status">Carregando versões…</Typography>}
      {resource.data && !resource.data.some((v) => v.status === 'published') && (
        <Alert severity="info" sx={{ mb: 3 }}>
          Nenhuma versão publicada. Novos participantes só poderão começar após a publicação.
        </Alert>
      )}
      <Stack spacing={2}>
        {resource.data?.map((version) => (
          <Paper key={version.id} variant="outlined" sx={{ p: 3 }}>
            <Stack
              direction="row"
              sx={{ justifyContent: 'space-between', gap: 2, flexWrap: 'wrap' }}
            >
              <Box sx={{ minWidth: 0, overflowWrap: 'anywhere' }}>
                <Chip
                  label={versionStatus[version.status]}
                  color={version.status === 'published' ? 'success' : 'default'}
                  size="small"
                />
                <Typography component="h2" variant="h5" sx={{ mt: 1 }}>
                  {version.event_name} · versão {version.version_number}
                </Typography>
                <Typography color="text.secondary">
                  {version.statement_count} afirmativas · criada em{' '}
                  {dateTime(version.created_at)}
                </Typography>
              </Box>
              <Stack
                direction="row"
                spacing={1}
                sx={{ alignItems: 'center', flexWrap: 'wrap' }}
              >
                <Button
                  component={Link}
                  to={`/admin/versions/${version.id}`}
                  variant="outlined"
                >
                  Abrir versão {version.version_number}
                </Button>
                <Button
                  onClick={() => {
                    setError('')
                    setForm({ name: version.event_name, source: version.id })
                  }}
                  aria-label={`Copiar versão ${version.version_number}`}
                >
                  Criar cópia
                </Button>
              </Stack>
            </Stack>
          </Paper>
        ))}
      </Stack>
      <Dialog
        open={form !== null}
        onClose={() => {
          if (!busy) setForm(null)
        }}
        fullWidth
        maxWidth="sm"
        aria-labelledby="version-create-title"
      >
        {form && (
          <Box
            component="form"
            onSubmit={async (e) => {
              e.preventDefault()
              if (busy) return
              setBusy(true)
              setError('')
              try {
                const created = await call(() =>
                  adminApi.createVersion(form.name, form.source || null),
                )
                navigate(`/admin/versions/${created.id}`)
              } catch (e) {
                setError(errorMessage(e))
              } finally {
                setBusy(false)
              }
            }}
          >
            <DialogTitle id="version-create-title">Criar rascunho do quiz</DialogTitle>
            <DialogContent>
              <Stack spacing={2.5} sx={{ pt: 1 }}>
                {error && <Alert severity="error">{error}</Alert>}
                <TextField
                  label="Nome do evento"
                  autoFocus
                  required
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  disabled={busy}
                  slotProps={{ htmlInput: { maxLength: 200 } }}
                />
                <TextField
                  label="Conteúdo inicial"
                  select
                  value={form.source}
                  onChange={(e) => setForm({ ...form, source: e.target.value })}
                  disabled={busy || resource.loading}
                >
                  <MenuItem value="">Catálogo original (74 afirmativas)</MenuItem>
                  {resource.data?.map((v) => (
                    <MenuItem key={v.id} value={v.id}>
                      Copiar versão {v.version_number} · {v.event_name}
                    </MenuItem>
                  ))}
                </TextField>
                <Typography variant="body2" color="text.secondary">
                  A nova versão começa como rascunho. Revise os destinos e o conteúdo antes de
                  publicar.
                </Typography>
              </Stack>
            </DialogContent>
            <DialogActions>
              <Button disabled={busy} onClick={() => setForm(null)}>
                Cancelar
              </Button>
              <Button type="submit" variant="contained" disabled={busy || !form.name.trim()}>
                {busy ? 'Criando…' : 'Criar rascunho'}
              </Button>
            </DialogActions>
          </Box>
        )}
      </Dialog>
    </>
  )
}
