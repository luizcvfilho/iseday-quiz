import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import ExpandMoreRounded from '@mui/icons-material/ExpandMoreRounded'
import { errorMessage } from '../api'
import { adminApi, versionStatus } from './api'
import type { QuizVersion, VersionDetail, VersionForm } from './api'
import { useAdmin } from './context'
import { useResource } from './useResource'
import { QuestionCatalog } from './QuestionCatalog'

export function AdminVersionDetail() {
  const { id = '' } = useParams()
  const resource = useResource<VersionDetail>(`/admin/versions/${encodeURIComponent(id)}`)
  return (
    <>
      <Button component={Link} to="/admin/versions" sx={{ mb: 2 }}>
        Voltar às versões
      </Button>
      {resource.loading && <Typography role="status">Carregando versão…</Typography>}
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
      {resource.data && (
        <VersionEditor
          key={resource.data.id}
          original={resource.data}
          onReload={resource.reload}
        />
      )}
    </>
  )
}

function VersionEditor({
  original,
  onReload,
}: {
  original: VersionDetail
  onReload: () => void
}) {
  const { call } = useAdmin()
  const [saved, setSaved] = useState(original)
  const [form, setForm] = useState<VersionForm>(original)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [action, setAction] = useState<'publish' | 'archive' | null>(null)
  const [reviewed, setReviewed] = useState(false)
  const versions = useResource<QuizVersion[]>('/admin/versions')
  const published = versions.data?.find((v) => v.status === 'published')
  const editable = saved.status === 'draft'
  const dirty = JSON.stringify(form) !== JSON.stringify(saved)
  useEffect(() => {
    if (!dirty) return
    const warn = (event: BeforeUnloadEvent) => event.preventDefault()
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])
  const field = (
    label: string,
    value: string,
    change: (value: string) => void,
    instructions = false,
    required = true,
  ) => (
    <TextField
      label={label}
      value={value}
      onChange={(e) => change(e.target.value)}
      required={required}
      disabled={!editable || busy}
      fullWidth
      multiline={instructions}
      minRows={instructions ? 2 : undefined}
      slotProps={{ htmlInput: { maxLength: instructions ? 4000 : 200 } }}
    />
  )
  return (
    <>
      <Chip
        label={versionStatus[saved.status]}
        color={saved.status === 'published' ? 'success' : 'default'}
        sx={{ mb: 1 }}
      />
      <Typography component="h1" variant="h3" sx={{ overflowWrap: 'anywhere', mb: 2 }}>
        {saved.event_name} · versão {saved.version_number}
      </Typography>
      {!editable && (
        <Alert severity="info" sx={{ mb: 3 }}>
          Esta versão preserva o histórico dos participantes. Para alterar o conteúdo ou os
          destinos, crie uma cópia na lista de versões.
        </Alert>
      )}
      {error && (
        <Alert
          severity="error"
          sx={{ mb: 2 }}
          action={
            <Button color="inherit" onClick={onReload}>
              Recarregar versão
            </Button>
          }
        >
          {error}
        </Alert>
      )}
      {success && (
        <Alert severity="success" sx={{ mb: 2 }}>
          {success}
        </Alert>
      )}
      <Box
        component="form"
        onSubmit={async (e) => {
          e.preventDefault()
          if (busy) return
          setBusy(true)
          setError('')
          setSuccess('')
          try {
            const result = await call(() =>
              adminApi.saveVersion(saved.id, form, saved.revision),
            )
            setSaved(result)
            setForm(result)
            setSuccess('Rascunho salvo.')
          } catch (e) {
            setError(errorMessage(e))
          } finally {
            setBusy(false)
          }
        }}
      >
        <Paper variant="outlined" sx={{ p: { xs: 2, sm: 3 }, mb: 3 }}>
          <Typography component="h2" variant="h5" sx={{ mb: 2 }}>
            Evento e acolhimento em Psicologia
          </Typography>
          <Stack spacing={2.5}>
            {field('Nome do evento', form.event_name, (value) =>
              setForm({ ...form, event_name: value }),
            )}
            {field('Destino de Psicologia / SPA', form.psychology_destination, (value) =>
              setForm({ ...form, psychology_destination: value }),
            )}
            {field(
              'Instruções de Psicologia / SPA',
              form.psychology_instructions,
              (value) => setForm({ ...form, psychology_instructions: value }),
              true,
            )}
          </Stack>
        </Paper>
        <Typography component="h2" variant="h5" sx={{ mb: 2 }}>
          Encaminhamentos por área
        </Typography>
        <Stack spacing={2} sx={{ mb: 3 }}>
          {form.areas.map((area, index) => (
            <Paper key={area.id} variant="outlined" sx={{ p: { xs: 2, sm: 3 } }}>
              <Typography component="h3" variant="h6" sx={{ mb: 2 }}>
                {area.name}
              </Typography>
              <Stack spacing={2}>
                {field(`Destino · ${area.name}`, area.destination, (value) =>
                  setForm({
                    ...form,
                    areas: form.areas.map((a, i) =>
                      i === index ? { ...a, destination: value } : a,
                    ),
                  }),
                )}
                {field(
                  `Instruções · ${area.name}`,
                  area.destination_instructions,
                  (value) =>
                    setForm({
                      ...form,
                      areas: form.areas.map((a, i) =>
                        i === index ? { ...a, destination_instructions: value } : a,
                      ),
                    }),
                  true,
                )}
              </Stack>
            </Paper>
          ))}
        </Stack>
        <Typography component="h2" variant="h5" sx={{ mb: 1 }}>
          Encaminhamentos por curso
        </Typography>
        <Typography color="text.secondary" sx={{ mb: 2 }}>
          Opcional. Deixe os dois campos vazios para usar o destino da área.
        </Typography>
        {form.courses.map((course, index) => (
          <Accordion key={course.id} disableGutters>
            <AccordionSummary expandIcon={<ExpandMoreRounded />}>
              <Typography>
                {course.name} · {form.areas.find((a) => a.id === course.area_id)?.name}
              </Typography>
            </AccordionSummary>
            <AccordionDetails>
              <Stack spacing={2}>
                {field(
                  `Destino · ${course.name}`,
                  course.destination ?? '',
                  (value) =>
                    setForm({
                      ...form,
                      courses: form.courses.map((c, i) =>
                        i === index ? { ...c, destination: value || null } : c,
                      ),
                    }),
                  false,
                  !!course.destination_instructions,
                )}
                {field(
                  `Instruções · ${course.name}`,
                  course.destination_instructions ?? '',
                  (value) =>
                    setForm({
                      ...form,
                      courses: form.courses.map((c, i) =>
                        i === index ? { ...c, destination_instructions: value || null } : c,
                      ),
                    }),
                  true,
                  !!course.destination,
                )}
              </Stack>
            </AccordionDetails>
          </Accordion>
        ))}
        <Accordion sx={{ mt: 3 }}>
          <AccordionSummary expandIcon={<ExpandMoreRounded />}>
            <Typography component="h2">
              Perguntas e pesos · {form.statements.length} afirmativas
            </Typography>
          </AccordionSummary>
          <AccordionDetails>
            <QuestionCatalog
              statements={form.statements}
              courses={form.courses}
              editable={editable}
              busy={busy}
              onChange={(statements) => setForm({ ...form, statements })}
            />
          </AccordionDetails>
        </Accordion>
        {editable && (
          <Stack
            direction="row"
            spacing={2}
            sx={{ my: 3, alignItems: 'center', flexWrap: 'wrap' }}
          >
            <Button type="submit" variant="contained" disabled={busy || !dirty}>
              {busy ? 'Salvando…' : 'Salvar rascunho'}
            </Button>
            <Typography variant="body2" color="text.secondary">
              {dirty ? 'Há alterações para salvar.' : 'Todas as alterações estão salvas.'}
            </Typography>
          </Stack>
        )}
      </Box>
      <Accordion sx={{ mt: 3 }}>
        <AccordionSummary expandIcon={<ExpandMoreRounded />}>
          <Typography component="h2">Conferir metodologia e observações</Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Typography sx={{ mb: 2 }}>
            O aluno escolhe 25 afirmativas. Cada área distinta recebe um ponto por afirmativa;
            os cursos somam os pesos dos seus vínculos. Todos os empates são preservados.
          </Typography>
          <Box component="ul" sx={{ pl: 3 }}>
            {saved.review_notes.map((note) => (
              <li key={note}>
                <Typography variant="body2" sx={{ mb: 1 }}>
                  {note}
                </Typography>
              </li>
            ))}
          </Box>
        </AccordionDetails>
      </Accordion>
      {versions.error && (
        <Alert
          severity="error"
          sx={{ mt: 2 }}
          action={
            <Button color="inherit" onClick={versions.reload}>
              Atualizar versões
            </Button>
          }
        >
          {versions.error}
        </Alert>
      )}
      <Stack direction="row" spacing={2} sx={{ mt: 3 }}>
        {editable && (
          <Button
            variant="contained"
            disabled={busy || dirty || !versions.data}
            onClick={() => {
              setReviewed(false)
              setAction('publish')
            }}
          >
            Publicar versão
          </Button>
        )}
        {saved.status === 'published' && (
          <Button
            color="warning"
            variant="outlined"
            disabled={busy}
            onClick={() => setAction('archive')}
          >
            Arquivar versão
          </Button>
        )}
      </Stack>
      <Dialog
        open={action !== null}
        onClose={() => {
          if (!busy) setAction(null)
        }}
        fullWidth
        maxWidth="sm"
        aria-labelledby="publication-title"
      >
        <DialogTitle id="publication-title">
          {action === 'publish'
            ? `Publicar versão ${saved.version_number}?`
            : 'Arquivar a versão publicada?'}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2}>
            {action === 'publish' ? (
              <>
                <Typography>
                  {published
                    ? `A versão ${published.version_number} será arquivada. Novos participantes usarão esta versão.`
                    : 'Esta versão ficará disponível para novos participantes.'}{' '}
                  Participações já iniciadas continuarão com sua versão original.
                </Typography>
                <FormControlLabel
                  control={
                    <Checkbox
                      checked={reviewed}
                      onChange={(e) => setReviewed(e.target.checked)}
                      disabled={busy}
                    />
                  }
                  label="Confirmo que a instituição revisou os textos, a metodologia, os pesos e os destinos desta versão."
                />
              </>
            ) : (
              <Typography>
                Novos cadastros ficarão indisponíveis até publicar outra versão. Participações
                já iniciadas e resultados antigos serão preservados.
              </Typography>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button disabled={busy} onClick={() => setAction(null)}>
            Cancelar
          </Button>
          <Button
            variant="contained"
            color={action === 'archive' ? 'warning' : 'primary'}
            disabled={busy || (action === 'publish' && !reviewed)}
            onClick={async () => {
              if (busy) return
              setBusy(true)
              setError('')
              setSuccess('')
              try {
                const result = await call(() =>
                  action === 'publish'
                    ? adminApi.publishVersion(saved.id, published?.id ?? null, saved.revision)
                    : adminApi.archiveVersion(saved.id),
                )
                setSaved(result)
                setForm(result)
                setSuccess(
                  result.status === 'published' ? 'Versão publicada.' : 'Versão arquivada.',
                )
                versions.reload()
              } catch (e) {
                setError(errorMessage(e))
                versions.reload()
              } finally {
                setBusy(false)
                setAction(null)
              }
            }}
          >
            {busy
              ? 'Aguarde…'
              : action === 'publish'
                ? 'Confirmar publicação'
                : 'Confirmar arquivamento'}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  )
}
