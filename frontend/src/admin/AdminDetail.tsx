import { useEffect, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router'
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material'
import { ApiError, errorMessage } from '../api'
import { useAdmin } from './context'
import { adminApi, agreementLabel, dateTime, statusLabel } from './api'
import type { ParticipationDetail } from './api'

export function AdminDetail() {
  const { id = '' } = useParams()
  const location = useLocation()
  const { call } = useAdmin()
  const [response, setResponse] = useState<{
    key: string
    data?: ParticipationDetail
    error?: string
    missing?: boolean
  } | null>(null)
  const [refresh, setRefresh] = useState(0)
  const requestKey = `${id}:${refresh}`
  const current = response?.key === requestKey ? response : null
  const data = current?.data
  const error = current?.error ?? ''
  const missing = current?.missing ?? false
  const busy = current === null
  useEffect(() => {
    const controller = new AbortController()
    void call(() => adminApi.detail(id, controller.signal))
      .then((value) => {
        if (!controller.signal.aborted) setResponse({ key: requestKey, data: value })
      })
      .catch((e) => {
        if (!controller.signal.aborted) {
          setResponse({
            key: requestKey,
            error: errorMessage(e),
            missing: e instanceof ApiError && e.status === 404,
          })
        }
      })
    return () => controller.abort()
  }, [call, id, requestKey])
  const result = data?.result
  const feedback = result?.feedback
  const chosen = result?.courses.find((course) => course.id === feedback?.chosen_course_id)
  const back =
    typeof location.state?.search === 'string' ? `/admin?${location.state.search}` : '/admin'
  return (
    <>
      <Stack direction="row" sx={{ justifyContent: 'space-between', mb: 3 }}>
        <Button component={Link} to={back}>
          ← Voltar às participações
        </Button>
        <Button disabled={busy} onClick={() => setRefresh((v) => v + 1)}>
          Atualizar
        </Button>
      </Stack>
      {busy && (
        <Stack role="status" direction="row" spacing={2}>
          <CircularProgress size={24} />
          <Typography>Carregando resultado…</Typography>
        </Stack>
      )}
      {error && (
        <Alert
          severity={missing ? 'info' : 'error'}
          action={
            !missing && <Button onClick={() => setRefresh((v) => v + 1)}>Tentar novamente</Button>
          }
        >
          {error}
        </Alert>
      )}
      {data && (
        <>
          <Typography variant="overline" color="primary">
            RESULTADO INDIVIDUAL
          </Typography>
          <Typography
            component="h1"
            variant="h3"
            sx={{
              fontSize: { xs: '1.9rem', sm: '2.6rem' },
              mt: 1,
              overflowWrap: 'anywhere',
            }}
          >
            {data.full_name}
          </Typography>
          <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', rowGap: 1, my: 2 }}>
            <Chip
              label={statusLabel[data.status]}
              color={data.status === 'completed' ? 'success' : 'default'}
            />
            <Chip variant="outlined" label={`${data.event_name} · versão ${data.version_number}`} />
          </Stack>
          <Paper component="section" variant="outlined" sx={{ p: 3, mb: 3 }}>
            <Typography component="h2" variant="h6" sx={{ mb: 2 }}>
              Cadastro e participação
            </Typography>
            <Box
              component="dl"
              sx={{
                display: 'grid',
                gridTemplateColumns: {
                  xs: '1fr',
                  sm: 'repeat(2, minmax(0, 1fr))',
                },
                gap: 2,
                m: 0,
              }}
            >
              {(
                [
                  ['Escola', data.school.name],
                  ['E-mail', data.email],
                  ['Telefone', data.phone],
                  ['Início', dateTime(data.started_at)],
                  ['Envio das escolhas', dateTime(data.submitted_at)],
                  ['Conclusão', dateTime(data.completed_at)],
                  ['Aviso apresentado', data.privacy_notice_version],
                ] as const
              ).map(([label, value]) => (
                <Box key={label}>
                  <Typography component="dt" variant="caption" color="text.secondary">
                    {label}
                  </Typography>
                  <Typography component="dd" sx={{ m: 0, overflowWrap: 'anywhere' }}>
                    {value}
                  </Typography>
                </Box>
              ))}
            </Box>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 2 }}>
              Datas no horário de Brasília.
            </Typography>
          </Paper>
          {!result ? (
            <Alert severity="info">
              O estudante ainda não enviou suas escolhas. Afirmativas e resultados ficam disponíveis
              após o envio.
            </Alert>
          ) : (
            <>
              <Paper component="section" variant="outlined" sx={{ p: 3, mb: 3 }}>
                <Typography component="h2" variant="h5" sx={{ mb: 2 }}>
                  Afinidades encontradas
                </Typography>
                <Typography sx={{ fontWeight: 600 }}>
                  {data.winning_areas.map((area) => area.name).join(' · ')}
                </Typography>
                <Typography color="text.secondary" sx={{ mt: 1 }}>
                  Cursos sugeridos:{' '}
                  {data.recommended_courses.map((course) => course.name).join(', ')}
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
                  Todos os empates são preservados. As pontuações são pontos do quiz, sem percentual
                  de compatibilidade.
                </Typography>
              </Paper>
              <Box
                sx={{
                  display: 'grid',
                  gridTemplateColumns: {
                    xs: '1fr',
                    md: 'minmax(0, 1fr) minmax(0, 1.3fr)',
                  },
                  gap: 3,
                  mb: 3,
                }}
              >
                <ScoreTable
                  title="Pontuação por área"
                  rows={result.areas.map((area) => ({
                    ...area,
                    highlighted: area.is_winner,
                    badge: 'Vencedora',
                  }))}
                />
                <ScoreTable
                  title="Pontuação por curso"
                  rows={result.courses.map((course) => ({
                    ...course,
                    highlighted: course.is_recommended,
                    badge: 'Sugerido',
                    secondary: result.areas.find((area) => area.id === course.area_id)?.name,
                  }))}
                />
              </Box>
              <Paper component="section" variant="outlined" sx={{ p: 3, mb: 3 }}>
                <Typography component="h2" variant="h5" sx={{ mb: 2 }}>
                  Confirmação e encaminhamento
                </Typography>
                <Typography sx={{ fontWeight: 600 }}>
                  {agreementLabel(data.agrees_with_result)}
                </Typography>
                {feedback ? (
                  <>
                    {chosen && (
                      <Typography sx={{ mt: 1 }}>Curso escolhido: {chosen.name}</Typography>
                    )}
                    <Typography sx={{ mt: 2, fontWeight: 600 }}>{feedback.destination}</Typography>
                    <Typography sx={{ whiteSpace: 'pre-wrap', mt: 1 }}>
                      {feedback.destination_instructions}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      Respondido em {dateTime(feedback.answered_at)}
                    </Typography>
                  </>
                ) : (
                  <Typography color="text.secondary" sx={{ mt: 1 }}>
                    O estudante ainda não respondeu se concorda com o resultado.
                  </Typography>
                )}
              </Paper>
              <Paper component="section" variant="outlined" sx={{ p: 3 }}>
                <Typography component="h2" variant="h5" sx={{ mb: 2 }}>
                  Afirmativas selecionadas ({data.selections.length})
                </Typography>
                <Box component="ol" sx={{ pl: 3, m: 0 }}>
                  {data.selections.map((statement) => (
                    <Typography component="li" key={statement.id} sx={{ py: 1, pl: 0.5 }}>
                      {statement.text}
                    </Typography>
                  ))}
                </Box>
              </Paper>
            </>
          )}
        </>
      )}
    </>
  )
}
function ScoreTable({
  title,
  rows,
}: {
  title: string
  rows: {
    id: string
    name: string
    score: number
    highlighted: boolean
    badge: string
    secondary?: string
  }[]
}) {
  return (
    <Paper component="section" variant="outlined" sx={{ overflow: 'hidden' }}>
      <Typography component="h2" variant="h6" sx={{ p: 2 }}>
        {title}
      </Typography>
      <TableContainer>
        <Table size="small" aria-label={title}>
          <TableHead>
            <TableRow>
              <TableCell>Nome</TableCell>
              <TableCell align="right">Pontos</TableCell>
              <TableCell>Resultado</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {[...rows]
              .sort((a, b) => b.score - a.score || a.name.localeCompare(b.name, 'pt-BR'))
              .map((row) => (
                <TableRow
                  key={row.id}
                  sx={{ bgcolor: row.highlighted ? 'action.hover' : undefined }}
                >
                  <TableCell>
                    <Typography variant="body2">{row.name}</Typography>
                    {row.secondary && (
                      <Typography variant="caption" color="text.secondary">
                        {row.secondary}
                      </Typography>
                    )}
                  </TableCell>
                  <TableCell align="right">{row.score}</TableCell>
                  <TableCell>
                    {row.highlighted ? (
                      <Chip size="small" color="primary" variant="outlined" label={row.badge} />
                    ) : (
                      '—'
                    )}
                  </TableCell>
                </TableRow>
              ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Paper>
  )
}
