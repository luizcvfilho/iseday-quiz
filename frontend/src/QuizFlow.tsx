import { useEffect, useRef, useState } from 'react'
import { ApiError, api, errorMessage } from './api'
import type {
  CurrentQuiz,
  Feedback,
  Participant,
  Quiz,
  Referral,
  Registration,
  Result,
} from './api'
import { RegistrationForm } from './components/RegistrationForm'
import { QuizSelection } from './components/QuizSelection'
import { QuizResult } from './components/QuizResult'
import {
  Alert,
  AlertTitle,
  Box,
  Button,
  Dialog as MuiDialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Paper,
  Typography,
} from '@mui/material'
import ArrowForwardRounded from '@mui/icons-material/ArrowForwardRounded'
import NorthEastRounded from '@mui/icons-material/NorthEastRounded'
import { FlowLayout } from './components/FlowLayout'
import { Eyebrow, SectionHeading, StatusScreen } from './components/Presentation'
import { brand } from './theme'

type Screen =
  | 'loading'
  | 'registration'
  | 'resume'
  | 'quiz'
  | 'review'
  | 'result'
  | 'referral'
  | 'expired'
  | 'ending'
  | 'unavailable'

function Dialog({
  kind,
  seconds,
  onContinue,
  onEnd,
}: {
  kind: 'idle' | 'exit'
  seconds: number
  onContinue: () => void
  onEnd: () => void
}) {
  return (
    <MuiDialog
      open
      aria-labelledby="dialog-title"
      aria-describedby="dialog-description"
      transitionDuration={0}
      onClose={(_, reason) => {
        if (reason === 'escapeKeyDown') onContinue()
      }}
    >
      <DialogTitle id="dialog-title">
        <Eyebrow>DISPOSITIVO COMPARTILHADO</Eyebrow>
        {kind === 'idle' ? 'Você ainda está por aqui?' : 'Encerrar esta participação?'}
      </DialogTitle>
      <DialogContent>
        <DialogContentText id="dialog-description">
          {kind === 'idle'
            ? `Sem atividade, esta tela será limpa em ${seconds} segundos para o próximo participante.`
            : 'As marcações ainda não enviadas serão descartadas. Respostas já enviadas continuam registradas.'}
        </DialogContentText>
      </DialogContent>
      <DialogActions>
        <Button variant="contained" autoFocus onClick={onContinue}>
          Continuar participação
        </Button>
        <Button variant="outlined" onClick={onEnd}>
          Encerrar e limpar
        </Button>
      </DialogActions>
    </MuiDialog>
  )
}

export function QuizFlow() {
  const [screen, setScreen] = useState<Screen>('loading')
  const [current, setCurrent] = useState<CurrentQuiz | null>(null)
  const [quiz, setQuiz] = useState<Quiz | null>(null)
  const [participant, setParticipant] = useState<Participant | null>(null)
  const [selected, setSelected] = useState<string[]>([])
  const [result, setResult] = useState<Result | null>(null)
  const [referral, setReferral] = useState<Referral | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [fields, setFields] = useState<string[]>([])
  const [uncertain, setUncertain] = useState(false)
  const [dialog, setDialog] = useState<'idle' | 'exit' | null>(null)
  const [seconds, setSeconds] = useState(60)
  const epoch = useRef(0)
  const busyRef = useRef(false)
  const activity = useRef(Date.now())
  const pendingFeedback = useRef<Feedback | null>(null)
  const channel = useRef<BroadcastChannel | null>(null)

  function clearPrivate() {
    setCurrent(null)
    setQuiz(null)
    setParticipant(null)
    setSelected([])
    setResult(null)
    setReferral(null)
    setFields([])
    setUncertain(false)
    setDialog(null)
    pendingFeedback.current = null
  }
  function begin() {
    if (busyRef.current) return null
    busyRef.current = true
    setBusy(true)
    setError('')
    setFields([])
    return epoch.current
  }
  function finish(id: number) {
    if (id === epoch.current) {
      busyRef.current = false
      setBusy(false)
    }
  }
  function invalidatePending() {
    ++epoch.current
  }
  function expire() {
    ++epoch.current
    busyRef.current = false
    setBusy(false)
    clearPrivate()
    setError('')
    setScreen('expired')
  }
  function showResult(data: Result) {
    setResult(data)
    setUncertain(false)
    pendingFeedback.current = null
    if (data.feedback) {
      setReferral(data.feedback)
      setScreen('referral')
    } else setScreen('result')
  }

  async function bootstrap() {
    const id = ++epoch.current
    clearPrivate()
    setScreen('loading')
    setError('')
    busyRef.current = true
    setBusy(true)
    try {
      let existing: Participant | null = null
      try {
        existing = await api.me()
      } catch (error) {
        if (!(error instanceof ApiError && error.status === 401)) throw error
      }
      if (id !== epoch.current) return
      if (existing) {
        setParticipant(existing)
        setScreen('resume')
      } else {
        const data = await api.current()
        if (id === epoch.current) {
          setCurrent(data)
          setScreen('registration')
        }
      }
    } catch (error) {
      if (id === epoch.current) {
        setError(errorMessage(error))
        setScreen('unavailable')
      }
    } finally {
      finish(id)
    }
  }

  useEffect(() => {
    let mounted = true
    queueMicrotask(() => {
      if (mounted) void bootstrap()
    })
    const onPageShow = (event: PageTransitionEvent) => {
      if (event.persisted) void bootstrap()
    }
    window.addEventListener('pageshow', onPageShow)
    const activeChannel =
      'BroadcastChannel' in window ? new BroadcastChannel('iseday-participant') : null
    if (activeChannel) {
      channel.current = activeChannel
      activeChannel.onmessage = (event) => {
        if (event.data === 'ended') expire()
      }
    }
    return () => {
      mounted = false
      invalidatePending()
      window.removeEventListener('pageshow', onPageShow)
      activeChannel?.close()
    }
  }, [])

  useEffect(() => {
    activity.current = Date.now()
    document.querySelector<HTMLElement>('h1')?.focus()
    window.scrollTo({ top: 0, behavior: 'instant' })
  }, [screen])

  useEffect(() => {
    if (error) document.querySelector<HTMLElement>('.error-banner')?.focus()
  }, [error])

  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault()
    }
    if ((screen === 'quiz' || screen === 'review') && selected.length)
      window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [screen, selected.length])

  useEffect(() => {
    if (!['registration', 'resume', 'quiz', 'review', 'result', 'referral'].includes(screen)) return
    const touch = () => {
      if (dialog !== 'idle') activity.current = Date.now()
    }
    for (const name of ['pointerdown', 'keydown', 'scroll'])
      window.addEventListener(name, touch, { passive: true })
    const timer = window.setInterval(() => {
      if (participant && Date.now() >= Date.parse(participant.access_expires_at)) {
        expire()
        return
      }
      if (busyRef.current) return
      const idle = Date.now() - activity.current
      if (idle >= 300_000) {
        void endAndReset()
        return
      }
      if (idle >= 240_000) {
        setSeconds(Math.ceil((300_000 - idle) / 1000))
        setDialog('idle')
      }
    }, 1000)
    return () => {
      clearInterval(timer)
      for (const name of ['pointerdown', 'keydown', 'scroll'])
        window.removeEventListener(name, touch)
    }
  }, [screen, participant, dialog])

  async function endAndReset() {
    if (busyRef.current) return
    const id = ++epoch.current
    busyRef.current = true
    setBusy(true)
    clearPrivate()
    setError('')
    setScreen('ending')
    let ended = false
    try {
      await api.end()
      if (id !== epoch.current) return
      channel.current?.postMessage('ended')
      ended = true
      const data = await api.current()
      if (id === epoch.current) {
        setCurrent(data)
        setScreen('registration')
      }
    } catch (error) {
      if (id === epoch.current) {
        setError(errorMessage(error))
        if (ended) setScreen('unavailable')
      }
    } finally {
      finish(id)
    }
  }

  async function resume() {
    if (!participant) return
    const id = begin()
    if (id === null) return
    try {
      if (participant.status === 'draft') {
        const data = await api.quiz()
        if (id === epoch.current) {
          setQuiz(data)
          setSelected([])
          setScreen('quiz')
        }
      } else {
        const data = await api.result()
        if (id === epoch.current) showResult(data)
      }
    } catch (error) {
      if (id === epoch.current) {
        if (error instanceof ApiError && error.status === 401) expire()
        else setError(errorMessage(error))
      }
    } finally {
      finish(id)
    }
  }

  async function register(data: Registration) {
    const id = begin()
    if (id === null) return
    try {
      const session = await api.register(data)
      const content = session.status === 'draft' ? await api.quiz() : null
      const saved = content ? null : await api.result()
      if (id !== epoch.current) return
      setParticipant(session)
      // The registration component is unmounted; contact values remain in no store.
      setCurrent(null)
      if (saved) showResult(saved)
      else {
        setQuiz(content)
        setScreen('quiz')
      }
    } catch (error) {
      if (id === epoch.current) {
        setError(errorMessage(error))
        setFields(error instanceof ApiError ? error.fields : [])
      }
    } finally {
      finish(id)
    }
  }

  async function reconcile(error: unknown, id: number) {
    if (id !== epoch.current) return
    if (error instanceof ApiError && error.status === 401) {
      expire()
      return
    }
    // A POST may have committed even when the browser did not receive its body.
    // Keep its inputs frozen until this authenticated read resolves the outcome.
    setUncertain(true)
    try {
      const saved = await api.result()
      if (id !== epoch.current) return
      if (saved.feedback || screen === 'review') {
        setError('')
        showResult(saved)
      } else {
        setUncertain(false)
        pendingFeedback.current = null
        setError(errorMessage(error))
      }
    } catch (readError) {
      if (id !== epoch.current) return
      if (readError instanceof ApiError && readError.status === 401) {
        expire()
        return
      }
      if (readError instanceof ApiError && readError.status === 409) setUncertain(false)
      setError(errorMessage(error))
    }
  }

  async function submit() {
    if (!quiz || selected.length !== quiz.required_selection_count) return
    const id = begin()
    if (id === null) return
    try {
      const data = await api.submit(selected)
      if (id === epoch.current) showResult(data)
    } catch (error) {
      await reconcile(error, id)
    } finally {
      finish(id)
    }
  }

  async function confirm(data: Feedback) {
    const id = begin()
    if (id === null) return
    const attempt = pendingFeedback.current ?? data
    pendingFeedback.current = attempt
    try {
      const saved = await api.feedback(attempt)
      if (id === epoch.current) {
        setReferral(saved)
        setScreen('referral')
        setUncertain(false)
      }
    } catch (error) {
      await reconcile(error, id)
    } finally {
      finish(id)
    }
  }

  const active = ['quiz', 'review', 'result', 'referral'].includes(screen)
  const step = ['registration', 'resume'].includes(screen)
    ? 1
    : ['quiz', 'review'].includes(screen)
      ? 2
      : 3
  return (
    <>
      <FlowLayout
        active={active}
        busy={busy}
        step={
          ['registration', 'resume', 'quiz', 'review', 'result', 'referral'].includes(screen)
            ? step
            : null
        }
        onExit={() => setDialog('exit')}
      >
        {error && (
          <Alert severity="error" className="error-banner" tabIndex={-1} sx={{ mb: 3 }}>
            <AlertTitle>Vamos tentar de novo?</AlertTitle>
            <Typography variant="body2">{error}</Typography>
            {uncertain && (
              <Typography variant="body2" sx={{ mt: 1 }}>
                Estamos sem confirmação do recebimento. Suas escolhas estão preservadas; tente
                enviar novamente para recuperar a resposta.
              </Typography>
            )}
            {screen === 'registration' && (
              <Button variant="text" disabled={busy} onClick={() => void bootstrap()}>
                Verificar sessão e atualizar o quiz
              </Button>
            )}
          </Alert>
        )}
        {screen === 'registration' && current && (
          <RegistrationForm
            quiz={current}
            busy={busy}
            serverFields={fields}
            onSubmit={(data) => void register(data)}
          />
        )}
        {screen === 'resume' && (
          <StatusScreen
            tag="BEM-VINDO DE VOLTA"
            title="Há uma participação aberta por aqui."
            actions={
              <>
                <Button
                  variant="contained"
                  disabled={busy}
                  loading={busy}
                  onClick={() => void resume()}
                >
                  {busy ? 'Recuperando…' : 'Continuar minha participação'}
                </Button>
                <Button variant="outlined" disabled={busy} onClick={() => void endAndReset()}>
                  Começar outra participação
                </Button>
              </>
            }
          >
            Se ela é sua, você pode continuar. Para outro aluno, encerre esta sessão e comece um
            novo cadastro.
            {participant?.status === 'draft' && (
              <Box component="span" sx={{ display: 'block', typography: 'caption', mt: 2 }}>
                Marcações ainda não enviadas não são recuperadas após recarregar a página.
              </Box>
            )}
          </StatusScreen>
        )}
        {(screen === 'quiz' || screen === 'review') && quiz && (
          <QuizSelection
            quiz={quiz}
            selected={selected}
            review={screen === 'review'}
            busy={busy}
            uncertain={uncertain}
            onToggle={(id) =>
              setSelected((previous) =>
                previous.includes(id)
                  ? previous.filter((item) => item !== id)
                  : previous.length < quiz.required_selection_count
                    ? [...previous, id]
                    : previous,
              )
            }
            onReview={() => {
              setError('')
              setScreen('review')
            }}
            onEdit={() => {
              setError('')
              setScreen('quiz')
            }}
            onSubmit={() => void submit()}
          />
        )}
        {screen === 'result' && result && (
          <QuizResult
            result={result}
            busy={busy}
            uncertain={uncertain}
            onConfirm={(data) => void confirm(data)}
          />
        )}
        {screen === 'referral' && referral && (
          <Box
            component="section"
            aria-labelledby="referral-title"
            sx={{ maxWidth: 800, mx: 'auto', textAlign: 'center' }}
          >
            <Box
              sx={{
                display: 'grid',
                placeItems: 'center',
                width: 76,
                height: 76,
                mx: 'auto',
                mb: 3,
                borderRadius: '50%',
                background: brand.gradient,
                color: 'white',
              }}
            >
              <NorthEastRounded fontSize="large" />
            </Box>
            <SectionHeading
              id="referral-title"
              centered
              tag="SEU PRÓXIMO PASSO NO ISE DAY"
              title={
                referral.agrees_with_result
                  ? 'Vamos conhecer de perto?'
                  : 'Vamos conversar sobre caminhos?'
              }
            >
              {referral.agrees_with_result
                ? 'Sua descoberta continua pelo campus. Siga o encaminhamento abaixo.'
                : 'Tudo bem não se identificar. A equipe de Psicologia pode ajudar você a explorar outras possibilidades.'}
            </SectionHeading>
            <Paper
              variant="outlined"
              sx={{
                my: 4,
                p: { xs: 3, sm: 4 },
                textAlign: 'left',
                borderTop: '4px solid',
                borderTopColor: 'secondary.main',
              }}
            >
              <Typography variant="overline" color="primary">
                SEU DESTINO
              </Typography>
              <Typography
                component="h2"
                variant="h4"
                sx={{ mt: 2, mb: 2, overflowWrap: 'anywhere' }}
              >
                {referral.destination}
              </Typography>
              <Typography sx={{ whiteSpace: 'pre-line' }}>
                {referral.destination_instructions}
              </Typography>
            </Paper>
            <Typography variant="caption" component="p" color="textSecondary" sx={{ mb: 3 }}>
              Sua participação foi registrada. Ao terminar, encerre para liberar este dispositivo.
            </Typography>
            <Button
              variant="contained"
              disabled={busy}
              onClick={() => void endAndReset()}
              endIcon={<ArrowForwardRounded />}
            >
              Encerrar e liberar dispositivo
            </Button>
          </Box>
        )}
        {screen === 'loading' && (
          <StatusScreen tag="ISE DAY" title="Preparando sua descoberta…" loading>
            Só um instante.
          </StatusScreen>
        )}
        {screen === 'ending' && (
          <StatusScreen
            tag="DISPOSITIVO COMPARTILHADO"
            title="Encerrando a sessão"
            loading={busy}
            actions={
              !busy && (
                <Button variant="contained" onClick={() => void endAndReset()}>
                  Tentar encerrar novamente
                </Button>
              )
            }
          >
            {busy
              ? 'Aguarde enquanto liberamos o dispositivo.'
              : 'Precisamos confirmar o encerramento antes de um novo cadastro.'}
          </StatusScreen>
        )}
        {screen === 'expired' && (
          <StatusScreen
            tag="SESSÃO ENCERRADA"
            title="Vamos começar de novo?"
            actions={
              <Button variant="contained" disabled={busy} onClick={() => void endAndReset()}>
                Voltar ao início
              </Button>
            }
          >
            A sessão terminou. Os dados desta tela foram limpos. Respostas já enviadas continuam
            registradas.
          </StatusScreen>
        )}
        {screen === 'unavailable' && (
          <StatusScreen
            tag="UM INSTANTE"
            title="Não foi possível abrir o quiz."
            actions={
              <Button variant="contained" disabled={busy} onClick={() => void bootstrap()}>
                Tentar novamente
              </Button>
            }
          >
            Tente novamente. Se continuar, procure a equipe do ISE Day.
          </StatusScreen>
        )}
      </FlowLayout>
      {dialog && (
        <Dialog
          kind={dialog}
          seconds={seconds}
          onContinue={() => {
            activity.current = Date.now()
            setDialog(null)
          }}
          onEnd={() => void endAndReset()}
        />
      )}
    </>
  )
}
