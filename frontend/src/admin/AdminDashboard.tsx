import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router'
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  MenuItem,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  TextField,
  Typography,
} from '@mui/material'
import ExpandMoreRounded from '@mui/icons-material/ExpandMoreRounded'
import { errorMessage } from '../api'
import { useAdmin } from './context'
import { adminApi, agreementLabel, dateTime, statusLabel } from './api'
import type { AdminOptions, Count, ParticipationPage, Summary } from './api'
import { AdminExport } from './AdminExport'

type FilterState = Record<
  | 'q'
  | 'school_id'
  | 'quiz_version_id'
  | 'status'
  | 'area_id'
  | 'course_id'
  | 'agreement'
  | 'date_from'
  | 'date_to',
  string
>
const empty: FilterState = {
  q: '',
  school_id: '',
  quiz_version_id: '',
  status: '',
  area_id: '',
  course_id: '',
  agreement: '',
  date_from: '',
  date_to: '',
}
const fromParams = (params: URLSearchParams): FilterState =>
  Object.fromEntries(
    Object.keys(empty).map((key) => [key, params.get(key) ?? '']),
  ) as FilterState

export function AdminDashboard() {
  const { call } = useAdmin()
  const [params, setParams] = useSearchParams()
  const query = params.toString()
  const [form, setForm] = useState(() => ({ query, filters: fromParams(params) }))
  if (form.query !== query) setForm({ query, filters: fromParams(params) })
  const filters = form.filters
  const setFilters = (update: FilterState | ((current: FilterState) => FilterState)) =>
    setForm({ query, filters: typeof update === 'function' ? update(form.filters) : update })
  const [options, setOptions] = useState<AdminOptions | null>(null)
  const [response, setResponse] = useState<{
    key: string
    data?: { list: ParticipationPage; summary: Summary }
    error?: string
  } | null>(null)
  const [optionsError, setOptionsError] = useState('')
  const [refresh, setRefresh] = useState(0)
  const requestKey = `${query}:${refresh}`
  const current = response?.key === requestKey ? response : null
  const data = current?.data
  const error = current?.error ?? ''
  const busy = current === null
  useEffect(() => {
    const controller = new AbortController()
    void call(() => adminApi.options(controller.signal))
      .then((value) => {
        if (!controller.signal.aborted) {
          setOptions(value)
          setOptionsError('')
        }
      })
      .catch((e) => {
        if (!controller.signal.aborted) setOptionsError(errorMessage(e))
      })
    return () => controller.abort()
  }, [call, refresh])
  useEffect(() => {
    const controller = new AbortController()
    const listParams = new URLSearchParams(query)
    const summaryParams = new URLSearchParams(query)
    summaryParams.delete('page')
    summaryParams.delete('page_size')
    void call(() =>
      Promise.all([
        adminApi.list(listParams, controller.signal),
        adminApi.summary(summaryParams, controller.signal),
      ]),
    )
      .then(([list, summary]) => {
        if (!controller.signal.aborted)
          setResponse({ key: requestKey, data: { list, summary } })
      })
      .catch((e) => {
        if (!controller.signal.aborted) setResponse({ key: requestKey, error: errorMessage(e) })
      })
    return () => controller.abort()
  }, [call, query, requestKey])
  const change = (key: keyof FilterState, value: string) =>
    setFilters((current) => ({
      ...current,
      [key]: value,
      ...(key === 'quiz_version_id' ? { area_id: '', course_id: '' } : {}),
    }))
  const apply = (event: FormEvent) => {
    event.preventDefault()
    const next = new URLSearchParams()
    for (const [key, value] of Object.entries(filters))
      if (value.trim()) next.set(key, value.trim())
    if (params.has('page_size')) next.set('page_size', params.get('page_size')!)
    setParams(next)
  }
  const pageTo = (page: number, size?: number) => {
    const next = new URLSearchParams(params)
    next.set('page', String(page))
    if (size) next.set('page_size', String(size))
    setParams(next)
  }
  const select = (
    key: keyof FilterState,
    label: string,
    items: { id: string; name: string }[],
  ) => (
    <TextField
      select
      label={label}
      value={filters[key]}
      onChange={(e) => change(key, e.target.value)}
      fullWidth
      size="small"
    >
      <MenuItem value="">Todos</MenuItem>
      {items.map((item) => (
        <MenuItem key={item.id} value={item.id}>
          {item.name}
        </MenuItem>
      ))}
    </TextField>
  )
  const versionLabel = (id: string) =>
    options?.versions.find((v) => v.id === id)?.version_number ?? '—'
  return (
    <>
      <Stack
        direction="row"
        sx={{
          justifyContent: 'space-between',
          alignItems: 'start',
          gap: 2,
          mb: 3,
        }}
      >
        <Box>
          <Typography variant="overline" color="primary">
            ACOMPANHAMENTO
          </Typography>
          <Typography
            component="h1"
            variant="h3"
            sx={{ fontSize: { xs: '1.8rem', sm: '2.5rem' }, mt: 1 }}
          >
            Participações dos estudantes
          </Typography>
          <Typography color="text.secondary" sx={{ mt: 1 }}>
            Resultados, escolhas e encaminhamentos do quiz.
          </Typography>
        </Box>
        <Button onClick={() => setRefresh((v) => v + 1)} disabled={busy}>
          Atualizar
        </Button>
      </Stack>
      <Paper component="form" onSubmit={apply} variant="outlined" sx={{ p: 2.5, mb: 3 }}>
        <Typography component="h2" variant="h6" sx={{ mb: 2 }}>
          Filtrar participações
        </Typography>
        {optionsError && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {optionsError} Use “Atualizar” para recarregar os filtros.
          </Alert>
        )}
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: {
              xs: '1fr',
              sm: 'repeat(2, minmax(0, 1fr))',
              md: 'repeat(3, minmax(0, 1fr))',
            },
            gap: 2,
          }}
        >
          <TextField
            label="Nome do estudante"
            value={filters.q}
            onChange={(e) => change('q', e.target.value)}
            size="small"
            fullWidth
            slotProps={{ htmlInput: { maxLength: 200 } }}
          />
          {select('school_id', 'Escola', options?.schools ?? [])}
          {select(
            'quiz_version_id',
            'Versão do quiz',
            options?.versions.map((v) => ({
              id: v.id,
              name: `${v.name} · versão ${v.version_number}`,
            })) ?? [],
          )}
          {select(
            'status',
            'Situação',
            Object.entries(statusLabel).map(([id, name]) => ({ id, name })),
          )}
          {select(
            'area_id',
            'Área vencedora',
            options?.areas
              .filter(
                (v) =>
                  !filters.quiz_version_id || v.quiz_version_id === filters.quiz_version_id,
              )
              .map((v) => ({
                ...v,
                name: `${v.name} · v${versionLabel(v.quiz_version_id)}`,
              })) ?? [],
          )}
          {select(
            'course_id',
            'Curso sugerido',
            options?.courses
              .filter(
                (v) =>
                  !filters.quiz_version_id || v.quiz_version_id === filters.quiz_version_id,
              )
              .map((v) => ({
                ...v,
                name: `${v.name} · v${versionLabel(v.quiz_version_id)}`,
              })) ?? [],
          )}
          {select('agreement', 'Confirmação do resultado', [
            { id: 'yes', name: 'Concordou' },
            { id: 'no', name: 'Discordou' },
            { id: 'pending', name: 'Sem resposta' },
          ])}
          <TextField
            label="Data inicial"
            type="date"
            size="small"
            value={filters.date_from}
            onChange={(e) => change('date_from', e.target.value)}
            slotProps={{ inputLabel: { shrink: true } }}
          />
          <TextField
            label="Data final"
            type="date"
            size="small"
            value={filters.date_to}
            onChange={(e) => change('date_to', e.target.value)}
            error={
              !!filters.date_from && !!filters.date_to && filters.date_from > filters.date_to
            }
            helperText={
              filters.date_from && filters.date_to && filters.date_from > filters.date_to
                ? 'A data final deve ser igual ou posterior à inicial.'
                : undefined
            }
            slotProps={{
              inputLabel: { shrink: true },
              htmlInput: { min: filters.date_from || undefined },
            }}
          />
        </Box>
        <Stack
          direction="row"
          spacing={1}
          sx={{ mt: 2, alignItems: 'center', flexWrap: 'wrap', rowGap: 1 }}
        >
          <Button
            type="submit"
            variant="contained"
            disabled={
              busy ||
              (!!filters.date_from && !!filters.date_to && filters.date_from > filters.date_to)
            }
          >
            Aplicar filtros
          </Button>
          <Button
            onClick={() => {
              setFilters(empty)
              setParams({})
            }}
            disabled={busy}
          >
            Limpar
          </Button>
          <Typography variant="caption" color="text.secondary">
            Período pela data de início · horário de Brasília.
          </Typography>
        </Stack>
      </Paper>
      <AdminExport key={query} query={query} disabled={busy || !data} />
      {error && (
        <Alert
          severity="error"
          action={
            <Button color="inherit" onClick={() => setRefresh((v) => v + 1)}>
              Tentar novamente
            </Button>
          }
        >
          {error}
        </Alert>
      )}
      {busy && (
        <Stack
          role="status"
          direction="row"
          spacing={2}
          sx={{ py: 4, justifyContent: 'center' }}
        >
          <CircularProgress size={24} />
          <Typography>Carregando participações…</Typography>
        </Stack>
      )}
      {data && (
        <>
          <Box
            aria-label="Resumo das participações filtradas"
            sx={{
              display: 'grid',
              gridTemplateColumns: {
                xs: 'repeat(2, minmax(0, 1fr))',
                md: 'repeat(4, minmax(0, 1fr))',
              },
              gap: 2,
              mb: 2,
            }}
          >
            {(
              [
                ['Iniciadas', data.summary.total],
                ['Em andamento', data.summary.draft],
                ['Aguardam confirmação', data.summary.submitted],
                ['Concluídas', data.summary.completed],
              ] as const
            ).map(([label, value]) => (
              <Paper key={label} variant="outlined" sx={{ p: 2.5 }}>
                <Typography color="text.secondary" variant="body2">
                  {label}
                </Typography>
                <Typography variant="h4" sx={{ mt: 1 }}>
                  {value}
                </Typography>
              </Paper>
            ))}
          </Box>
          <Paper variant="outlined" sx={{ p: 2.5, mb: 3 }}>
            <Typography component="h2" variant="h6">
              Confirmação dos estudantes
            </Typography>
            <Typography sx={{ mt: 1 }}>
              {data.summary.agreed} concordaram · {data.summary.disagreed} discordaram
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {data.summary.agreement_rate === null
                ? 'Ainda não há confirmações para calcular a concordância.'
                : `${data.summary.agreement_rate.toLocaleString('pt-BR')}% de concordância entre os ${data.summary.agreed + data.summary.disagreed} estudantes que responderam à confirmação.`}
            </Typography>
          </Paper>
          <Typography component="h2" variant="h5" sx={{ mb: 2 }}>
            Estudantes encontrados ({data.list.total})
          </Typography>
          {data.list.items.length === 0 ? (
            <Paper variant="outlined" sx={{ p: 4, mb: 3 }}>
              <Typography>
                {data.list.total
                  ? 'Não há registros nesta página.'
                  : 'Nenhuma participação encontrada para estes filtros.'}
              </Typography>
              {data.list.total > 0 && (
                <Button onClick={() => pageTo(1)}>Voltar à primeira página</Button>
              )}
            </Paper>
          ) : (
            <TableContainer component={Paper} variant="outlined" sx={{ mb: 1 }}>
              <Table sx={{ minWidth: 850 }} aria-label="Participações dos estudantes">
                <TableHead>
                  <TableRow>
                    {[
                      'Estudante / escola',
                      'Início',
                      'Situação',
                      'Áreas vencedoras / cursos sugeridos',
                      'Confirmação',
                      'Consulta',
                    ].map((label) => (
                      <TableCell key={label}>{label}</TableCell>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {data.list.items.map((row) => (
                    <TableRow key={row.id} hover>
                      <TableCell>
                        <Typography sx={{ fontWeight: 600 }}>{row.full_name}</Typography>
                        <Typography variant="body2" color="text.secondary">
                          {row.school.name}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          Versão {row.version_number}
                        </Typography>
                      </TableCell>
                      <TableCell sx={{ whiteSpace: 'nowrap' }}>
                        {dateTime(row.started_at)}
                      </TableCell>
                      <TableCell>
                        <Chip
                          size="small"
                          label={statusLabel[row.status]}
                          color={row.status === 'completed' ? 'success' : 'default'}
                        />
                      </TableCell>
                      <TableCell sx={{ maxWidth: 320 }}>
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>
                          {row.winning_areas.map((a) => a.name).join(', ') ||
                            'Ainda sem resultado'}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          {row.recommended_courses.map((c) => c.name).join(', ')}
                        </Typography>
                      </TableCell>
                      <TableCell>{agreementLabel(row.agrees_with_result)}</TableCell>
                      <TableCell>
                        <Button
                          component={Link}
                          to={`/admin/participations/${row.id}`}
                          state={{ search: query }}
                          aria-label={`Ver resultado de ${row.full_name}`}
                        >
                          Ver resultado
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
          {data.list.total > 0 && (
            <TablePagination
              component="div"
              count={data.list.total}
              page={Math.min(
                data.list.page - 1,
                Math.max(0, Math.ceil(data.list.total / data.list.page_size) - 1),
              )}
              rowsPerPage={data.list.page_size}
              rowsPerPageOptions={[10, 20, 50, 100]}
              onPageChange={(_, page) => pageTo(page + 1)}
              onRowsPerPageChange={(e) => pageTo(1, Number(e.target.value))}
              labelRowsPerPage="Por página:"
              labelDisplayedRows={({ from, to, count }) => `${from}–${to} de ${count}`}
              getItemAriaLabel={(type) =>
                type === 'next' ? 'Próxima página' : 'Página anterior'
              }
              sx={{
                mb: 3,
                '& .MuiTablePagination-toolbar': {
                  px: { xs: 0, sm: 2 },
                  flexWrap: 'wrap',
                },
                '& .MuiTablePagination-spacer': {
                  display: { xs: 'none', sm: 'block' },
                },
              }}
            />
          )}
          <Typography component="h2" variant="h5" sx={{ mt: 3, mb: 1 }}>
            Distribuição dos resultados
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            O resumo acompanha os filtros aplicados. Empates contam o estudante em cada área e
            curso sugerido; as somas dessas categorias podem superar o total de estudantes.
          </Typography>
          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: {
                xs: '1fr',
                md: 'repeat(3, minmax(0, 1fr))',
              },
              gap: 2,
            }}
          >
            <Distribution title="Por escola" items={data.summary.schools} />
            <Distribution title="Por área vencedora" items={data.summary.areas} />
            <Distribution title="Por curso sugerido" items={data.summary.courses} />
          </Box>
        </>
      )}
    </>
  )
}

function Distribution({ title, items }: { title: string; items: Count[] }) {
  return (
    <Accordion variant="outlined" disableGutters sx={{ alignSelf: 'start' }}>
      <AccordionSummary expandIcon={<ExpandMoreRounded />}>
        <Typography component="h3" sx={{ fontWeight: 600 }}>
          {title}
        </Typography>
      </AccordionSummary>
      <AccordionDetails>
        {items.length ? (
          <Stack component="ul" spacing={1.5} sx={{ p: 0, m: 0, listStyle: 'none' }}>
            {items.map((item) => (
              <Stack
                component="li"
                key={item.id}
                direction="row"
                spacing={2}
                sx={{ justifyContent: 'space-between' }}
              >
                <Box>
                  <Typography variant="body2">{item.name}</Typography>
                  {item.version_number != null && (
                    <Typography variant="caption" color="text.secondary">
                      Versão {item.version_number}
                    </Typography>
                  )}
                </Box>
                <Typography sx={{ fontWeight: 600 }}>{item.count}</Typography>
              </Stack>
            ))}
          </Stack>
        ) : (
          <Typography variant="body2" color="text.secondary">
            Sem resultados neste período.
          </Typography>
        )}
      </AccordionDetails>
    </Accordion>
  )
}
