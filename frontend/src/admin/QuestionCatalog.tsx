import { useState } from 'react'
import {
  Alert,
  Box,
  Button,
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
import type { Named, Question } from './api'

type Editing = {
  index: number | null
  text: string
  links: { course_id: string; weight: string }[]
}

export function QuestionCatalog({
  statements,
  courses,
  editable,
  busy,
  onChange,
}: {
  statements: Question[]
  courses: Named[]
  editable: boolean
  busy: boolean
  onChange: (statements: Question[]) => void
}) {
  const [editing, setEditing] = useState<Editing | null>(null)
  const [search, setSearch] = useState('')
  const validWeight = (value: string) =>
    /^\d+$/.test(value) && Number(value) >= 1 && Number(value) <= 32767
  const duplicate =
    !!editing &&
    statements.some(
      (s, index) =>
        index !== editing.index &&
        s.text.trim().replace(/\s+/g, ' ').toLocaleLowerCase('pt-BR') ===
          editing.text.trim().replace(/\s+/g, ' ').toLocaleLowerCase('pt-BR'),
    )
  const valid =
    editing &&
    editing.text.trim() &&
    !duplicate &&
    editing.links.length > 0 &&
    editing.links.every(
      (link) => courses.some((c) => c.id === link.course_id) && validWeight(link.weight),
    ) &&
    new Set(editing.links.map((link) => link.course_id)).size === editing.links.length
  const available = courses.filter(
    (c) => !editing?.links.some((link) => link.course_id === c.id),
  )
  const query = search.trim().toLocaleLowerCase('pt-BR')
  const visible = statements
    .map((statement, index) => ({ statement, index }))
    .filter(
      ({ statement }) =>
        !query ||
        `${statement.number} ${statement.text} ${statement.courses.map((c) => c.course).join(' ')}`
          .toLocaleLowerCase('pt-BR')
          .includes(query),
    )
  return (
    <>
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={2}
        sx={{ mb: 2, alignItems: { sm: 'center' } }}
      >
        <TextField
          label="Buscar afirmativa ou curso"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          size="small"
          fullWidth
        />
        {editable && (
          <Button
            variant="outlined"
            sx={{ flexShrink: 0 }}
            disabled={busy || statements.length >= 1000}
            onClick={() => setEditing({ index: null, text: '', links: [] })}
          >
            Adicionar afirmativa
          </Button>
        )}
      </Stack>
      {editable && (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Edite o texto e os pesos por curso. Use “Salvar rascunho” para gravar as alterações
          antes de publicar.
        </Typography>
      )}
      {!visible.length && <Alert severity="info">Nenhuma afirmativa encontrada.</Alert>}
      <Stack spacing={2}>
        {visible.map(({ statement, index }) => (
          <Paper key={statement.id ?? `new-${index}`} variant="outlined" sx={{ p: 2 }}>
            <Stack
              direction={{ xs: 'column', sm: 'row' }}
              sx={{ justifyContent: 'space-between', gap: 1 }}
            >
              <Box sx={{ minWidth: 0, overflowWrap: 'anywhere' }}>
                <Typography>
                  {statement.number}. {statement.text}
                </Typography>
                {!statement.id && (
                  <Typography variant="caption" color="primary">
                    Nova afirmativa · ainda não salva
                  </Typography>
                )}
                <Typography component="p" variant="caption" color="text.secondary">
                  {statement.courses.map((c) => `${c.course} (peso ${c.weight})`).join(' · ') ||
                    'Sem cursos vinculados'}
                </Typography>
              </Box>
              {editable && (
                <Button
                  disabled={busy}
                  sx={{ flexShrink: 0, alignSelf: 'start' }}
                  aria-label={`Editar afirmativa ${statement.number}`}
                  onClick={() =>
                    setEditing({
                      index,
                      text: statement.text,
                      links: statement.courses.map((c) => ({
                        course_id: c.course_id,
                        weight: String(c.weight),
                      })),
                    })
                  }
                >
                  Editar
                </Button>
              )}
            </Stack>
          </Paper>
        ))}
      </Stack>
      <Dialog
        open={editing !== null}
        onClose={() => setEditing(null)}
        fullWidth
        maxWidth="md"
        aria-labelledby="question-title"
      >
        {editing && (
          <Box
            component="form"
            onSubmit={(event) => {
              event.preventDefault()
              event.stopPropagation()
              if (!valid || busy) return
              const original = editing.index === null ? null : statements[editing.index]
              const question: Question = {
                id: original?.id ?? null,
                number: original?.number ?? Math.max(0, ...statements.map((s) => s.number)) + 1,
                text: editing.text.trim(),
                courses: editing.links.map((link) => ({
                  course_id: link.course_id,
                  course: courses.find((c) => c.id === link.course_id)!.name,
                  weight: Number(link.weight),
                })),
              }
              onChange(
                editing.index === null
                  ? [...statements, question]
                  : statements.map((s, i) => (i === editing.index ? question : s)),
              )
              setSearch('')
              setEditing(null)
            }}
          >
            <DialogTitle id="question-title">
              {editing.index === null
                ? 'Adicionar afirmativa'
                : `Editar afirmativa ${statements[editing.index].number}`}
            </DialogTitle>
            <DialogContent>
              <Stack spacing={2.5} sx={{ pt: 1 }}>
                <TextField
                  label="Texto da afirmativa"
                  required
                  autoFocus
                  fullWidth
                  multiline
                  minRows={3}
                  value={editing.text}
                  onChange={(e) => setEditing({ ...editing, text: e.target.value })}
                  slotProps={{ htmlInput: { maxLength: 4000 } }}
                  error={duplicate}
                  helperText={
                    duplicate
                      ? 'Já existe uma afirmativa com esse texto.'
                      : `${editing.text.length}/4000 caracteres`
                  }
                />
                <Typography component="h3" variant="h6">
                  Cursos e pesos
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Cada curso vinculado recebe o peso indicado quando o aluno seleciona esta
                  afirmativa. A área continua contando um ponto por afirmativa.
                </Typography>
                {!editing.links.length && (
                  <Alert severity="info">Adicione pelo menos um curso e seu peso.</Alert>
                )}
                {editing.links.map((link, index) => (
                  <Stack
                    key={index}
                    direction={{ xs: 'column', sm: 'row' }}
                    spacing={1.5}
                    sx={{ alignItems: { sm: 'start' } }}
                  >
                    <TextField
                      label={`Curso ${index + 1}`}
                      select
                      value={link.course_id}
                      fullWidth
                      onChange={(e) =>
                        setEditing({
                          ...editing,
                          links: editing.links.map((l, i) =>
                            i === index ? { ...l, course_id: e.target.value } : l,
                          ),
                        })
                      }
                    >
                      {courses
                        .filter(
                          (c) =>
                            c.id === link.course_id ||
                            !editing.links.some((l) => l.course_id === c.id),
                        )
                        .map((c) => (
                          <MenuItem key={c.id} value={c.id}>
                            {c.name}
                          </MenuItem>
                        ))}
                    </TextField>
                    <TextField
                      label={`Peso ${index + 1}`}
                      type="number"
                      required
                      value={link.weight}
                      onChange={(e) =>
                        setEditing({
                          ...editing,
                          links: editing.links.map((l, i) =>
                            i === index ? { ...l, weight: e.target.value } : l,
                          ),
                        })
                      }
                      error={!validWeight(link.weight)}
                      helperText="Inteiro de 1 a 32767"
                      slotProps={{ htmlInput: { min: 1, max: 32767, step: 1 } }}
                      sx={{ width: { xs: '100%', sm: 180 }, flexShrink: 0 }}
                    />
                    <Button
                      aria-label={`Remover vínculo ${index + 1}`}
                      color="warning"
                      onClick={() =>
                        setEditing({
                          ...editing,
                          links: editing.links.filter((_, i) => i !== index),
                        })
                      }
                    >
                      Remover
                    </Button>
                  </Stack>
                ))}
                <Button
                  variant="outlined"
                  sx={{ alignSelf: 'start' }}
                  disabled={!available.length}
                  onClick={() =>
                    setEditing({
                      ...editing,
                      links: [...editing.links, { course_id: available[0].id, weight: '1' }],
                    })
                  }
                >
                  Adicionar curso e peso
                </Button>
                <Typography variant="caption" color="text.secondary">
                  As alterações entram no rascunho ao aplicar. Depois, salve o rascunho para
                  gravá-las.
                </Typography>
              </Stack>
            </DialogContent>
            <DialogActions>
              <Button onClick={() => setEditing(null)}>Cancelar</Button>
              <Button type="submit" variant="contained" disabled={!valid || busy}>
                Aplicar ao rascunho
              </Button>
            </DialogActions>
          </Box>
        )}
      </Dialog>
    </>
  )
}
