import { useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  Paper,
  Stack,
  Switch,
  TextField,
  Typography,
} from '@mui/material'
import { errorMessage } from '../api'
import { adminApi } from './api'
import type { ManagedSchool } from './api'
import { useAdmin } from './context'
import { useResource } from './useResource'

const blank = { name: '', city: '', state_code: '', is_active: true }

export function AdminSchools() {
  const { call } = useAdmin()
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const resource = useResource<ManagedSchool[]>(`/admin/schools?q=${encodeURIComponent(query)}`)
  const [form, setForm] = useState<(typeof blank & { id?: string }) | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const open = (school?: ManagedSchool) => {
    setError('')
    setSuccess('')
    setForm(school ?? { ...blank })
  }
  return (
    <>
      <Stack
        direction="row"
        sx={{ justifyContent: 'space-between', gap: 2, flexWrap: 'wrap', mb: 3 }}
      >
        <Box>
          <Typography component="h1" variant="h3">
            Escolas
          </Typography>
          <Typography color="text.secondary" sx={{ mt: 1 }}>
            Cadastre escolas e controle quais aparecem para novos participantes.
          </Typography>
        </Box>
        <Button variant="contained" onClick={() => open()}>
          Cadastrar escola
        </Button>
      </Stack>
      {success && (
        <Alert severity="success" sx={{ mb: 2 }}>
          {success}
        </Alert>
      )}
      <Stack
        component="form"
        direction="row"
        spacing={1}
        sx={{ mb: 3 }}
        onSubmit={(e) => {
          e.preventDefault()
          setQuery(search.trim())
          resource.reload()
        }}
      >
        <TextField
          label="Buscar escola"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          size="small"
          fullWidth
          slotProps={{ htmlInput: { maxLength: 200 } }}
        />
        <Button type="submit">Buscar</Button>
        <Button onClick={resource.reload}>Atualizar</Button>
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
      {resource.loading && <Typography role="status">Carregando escolas…</Typography>}
      {resource.data?.length === 0 && <Alert severity="info">Nenhuma escola encontrada.</Alert>}
      <Stack spacing={2}>
        {resource.data?.map((school) => (
          <Paper variant="outlined" key={school.id} sx={{ p: 2.5 }}>
            <Stack
              direction="row"
              sx={{ gap: 2, justifyContent: 'space-between', alignItems: 'center' }}
            >
              <Box sx={{ minWidth: 0, overflowWrap: 'anywhere' }}>
                <Typography component="h2" variant="h6">
                  {school.name}
                </Typography>
                <Typography color="text.secondary">
                  {[school.city, school.state_code].filter(Boolean).join(' · ') ||
                    'Localidade não informada'}
                </Typography>
                <Chip
                  size="small"
                  label={school.is_active ? 'Ativa' : 'Inativa'}
                  color={school.is_active ? 'success' : 'default'}
                  sx={{ mt: 1 }}
                />
              </Box>
              <Button aria-label={`Editar ${school.name}`} onClick={() => open(school)}>
                Editar
              </Button>
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
        aria-labelledby="school-title"
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
                await call(() =>
                  adminApi.saveSchool(
                    {
                      name: form.name,
                      city: form.city,
                      state_code: form.state_code,
                      is_active: form.is_active,
                    },
                    form.id,
                  ),
                )
                setForm(null)
                setSuccess('Escola salva.')
                resource.reload()
              } catch (e) {
                setError(errorMessage(e))
              } finally {
                setBusy(false)
              }
            }}
          >
            <DialogTitle id="school-title">
              {form.id ? 'Editar escola' : 'Cadastrar escola'}
            </DialogTitle>
            <DialogContent>
              <Stack spacing={2.5} sx={{ pt: 1 }}>
                {error && <Alert severity="error">{error}</Alert>}
                <TextField
                  label="Nome da escola"
                  required
                  autoFocus
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  disabled={busy}
                  slotProps={{ htmlInput: { maxLength: 200 } }}
                />
                <TextField
                  label="Cidade"
                  value={form.city}
                  onChange={(e) => setForm({ ...form, city: e.target.value })}
                  disabled={busy}
                  slotProps={{ htmlInput: { maxLength: 200 } }}
                />
                <TextField
                  label="UF"
                  value={form.state_code}
                  onChange={(e) =>
                    setForm({ ...form, state_code: e.target.value.toUpperCase() })
                  }
                  disabled={busy}
                  slotProps={{ htmlInput: { maxLength: 2, pattern: '[A-Z]{2}' } }}
                  helperText="Opcional. Duas letras, por exemplo: RJ."
                />
                <FormControlLabel
                  control={
                    <Switch
                      checked={form.is_active}
                      onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
                      disabled={busy}
                    />
                  }
                  label="Disponível para novos participantes"
                />
                <Typography variant="body2" color="text.secondary">
                  Desativar a escola preserva as participações já registradas.
                </Typography>
              </Stack>
            </DialogContent>
            <DialogActions>
              <Button disabled={busy} onClick={() => setForm(null)}>
                Cancelar
              </Button>
              <Button type="submit" variant="contained" disabled={busy || !form.name.trim()}>
                {busy ? 'Salvando…' : 'Salvar escola'}
              </Button>
            </DialogActions>
          </Box>
        )}
      </Dialog>
    </>
  )
}
