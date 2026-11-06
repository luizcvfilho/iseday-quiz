import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import ArrowForwardRounded from '@mui/icons-material/ArrowForwardRounded'
import PrivacyTipOutlined from '@mui/icons-material/PrivacyTipOutlined'
import { api, errorMessage, normalizePhone } from '../api'
import type { CurrentQuiz, ParticipationContacts, ParticipationMatch, Registration } from '../api'
import { brand } from '../theme'
import { SectionHeading } from './Presentation'

type Props = {
  quiz: CurrentQuiz
  busy: boolean
  serverFields: string[]
  onSubmit: (data: Registration) => void
  onResume: (contacts: ParticipationContacts) => void
}

export function RegistrationForm({ quiz, busy, serverFields, onSubmit, onResume }: Props) {
  const [schoolName, setSchoolName] = useState('')
  const [phoneError, setPhoneError] = useState('')
  const [phone, setPhone] = useState('')
  const [email, setEmail] = useState('')
  const [match, setMatch] = useState<ParticipationMatch | null>(null)
  const [prompt, setPrompt] = useState<Registration | null>(null)
  const [checking, setChecking] = useState(false)
  const [lookupError, setLookupError] = useState('')
  const lookupEpoch = useRef(0)

  useEffect(() => () => {
    ++lookupEpoch.current
  }, [])

  function changeContact() {
    ++lookupEpoch.current
    setMatch(null)
    setLookupError('')
  }

  async function checkContacts() {
    if (busy || checking) return
    const contacts: ParticipationContacts = {}
    const normalized = normalizePhone(phone)
    if (normalized) contacts.phone = normalized
    if (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) contacts.email = email.trim()
    if (!contacts.email && !contacts.phone) return
    const id = ++lookupEpoch.current
    try {
      const found = await api.lookup(contacts)
      if (id === lookupEpoch.current) {
        setMatch(found)
        setLookupError('')
      }
    } catch {
      // Registration checks again before creating a participation.
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy || checking || !schoolName.trim()) return
    const fields = new FormData(event.currentTarget)
    const phone = normalizePhone(String(fields.get('phone')))
    if (!phone) {
      setPhoneError('Informe um telefone brasileiro com DDD e 10 ou 11 dígitos.')
      return
    }
    setPhoneError('')
    const data: Registration = {
      school_name: schoolName.trim(),
      full_name: String(fields.get('full_name')).trim(),
      phone,
      email: String(fields.get('email')).trim(),
      privacy_notice_version: quiz.privacy_notice_version,
    }
    const id = ++lookupEpoch.current
    setChecking(true)
    setLookupError('')
    try {
      const found = await api.lookup({ email: data.email, phone: data.phone })
      if (id !== lookupEpoch.current) return
      setMatch(found)
      if (found) setPrompt(data)
      else onSubmit(data)
    } catch (error) {
      if (id === lookupEpoch.current) setLookupError(errorMessage(error))
    } finally {
      setChecking(false)
    }
  }
  const invalid = (field: string) => serverFields.includes(field)
  const disabled = busy || checking
  const matchingContact = match?.matched_by.length === 2
    ? 'Este e-mail e telefone já foram utilizados'
    : match?.matched_by[0] === 'email'
      ? 'Este e-mail já foi utilizado'
      : 'Este telefone já foi utilizado'
  const matchMessage = match
    ? `${matchingContact} em uma participação ${match.status === 'completed' ? 'já concluída' : 'em andamento'}.`
    : ''

  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' },
        gap: { xs: 4, md: 7, lg: 10 },
        alignItems: 'start',
      }}
    >
      <Box component="section" aria-labelledby="intro-title" sx={{ pt: { xs: 0, md: 2 } }}>
        <SectionHeading
          id="intro-title"
          tag="ISE DAY · QUIZ DE AFINIDADES"
          title={
            <>
              Seu próximo passo começa com uma{' '}
              <Box component="span" sx={{ color: 'primary.main' }}>
                descoberta.
              </Box>
            </>
          }
        >
          O que desperta sua curiosidade? Explore seus interesses e conheça caminhos para o seu
          futuro.
        </SectionHeading>
        <Box
          sx={{ display: { xs: 'none', md: 'block' }, color: 'primary.main', maxWidth: 400, my: 3 }}
          aria-hidden="true"
        >
          <svg viewBox="0 0 400 185" fill="none" style={{ display: 'block', width: '100%' }}>
            <path
              d="M35 160H130Q175 160 175 115V75Q175 35 220 35H350M175 115Q175 85 220 85H300M175 105Q175 135 220 135H345"
              stroke="currentColor"
              strokeWidth="2"
            />
            <circle cx="35" cy="160" r="8" fill="currentColor" />
            <circle
              cx="350"
              cy="35"
              r="22"
              fill={brand.paleBlue}
              stroke="currentColor"
              strokeWidth="2"
            />
            <path d="M342 35h16m-8-8 8 8-8 8" stroke="currentColor" strokeWidth="2" />
            <rect
              x="300"
              y="72"
              width="26"
              height="26"
              rx="5"
              fill={brand.sand}
              stroke={brand.gold}
              strokeWidth="2"
            />
            <path
              d="m345 121 14 14-14 14-14-14 14-14Z"
              fill={brand.paleBlue}
              stroke="currentColor"
              strokeWidth="2"
            />
          </svg>
        </Box>
        <Stack
          component="ol"
          spacing={2}
          sx={{ listStyle: 'none', pl: 0, display: { xs: 'none', md: 'flex' } }}
        >
          {['Conte um pouco sobre você', 'Escolha 25 afirmativas', 'Descubra áreas e cursos'].map(
            (label, index) => (
              <Stack
                component="li"
                direction="row"
                spacing={1.5}
                key={label}
                sx={{ alignItems: 'center' }}
              >
                <Box
                  sx={{
                    display: 'grid',
                    placeItems: 'center',
                    width: 28,
                    height: 28,
                    border: 1,
                    borderColor: 'divider',
                    borderRadius: '50%',
                    color: 'primary.main',
                    fontSize: '.7rem',
                  }}
                >
                  0{index + 1}
                </Box>
                <Typography variant="body2">{label}</Typography>
              </Stack>
            ),
          )}
        </Stack>
      </Box>
      <Paper
        component="section"
        variant="outlined"
        aria-labelledby="form-title"
        sx={{ p: { xs: 2.5, sm: 4 }, boxShadow: '0 12px 48px -24px #0b3d6526' }}
      >
        <Typography id="form-title" component="h2" variant="h5" sx={{ mb: 1 }}>
          Vamos começar?
        </Typography>
        <Typography variant="body2" color="textSecondary" sx={{ mb: 3 }}>
          Preencha seus dados para iniciar o quiz. Todos os campos são obrigatórios.
        </Typography>
        <Box component="form" onSubmit={(event) => void submit(event)} autoComplete="off">
          <Stack spacing={2.5}>
            <TextField
              id="full-name"
              name="full_name"
              label="Nome completo"
              placeholder="Como podemos chamar você?"
              required
              disabled={disabled}
              autoComplete="off"
              slotProps={{ htmlInput: { minLength: 2, maxLength: 200 } }}
              error={invalid('full_name')}
              helperText={invalid('full_name') ? 'Informe seu nome completo.' : undefined}
            />
            <TextField
              id="school"
              name="school_name"
              label="Escola"
              placeholder="Digite o nome da sua escola"
              value={schoolName}
              onChange={(event) => setSchoolName(event.target.value)}
              required
              disabled={disabled}
              autoComplete="off"
              slotProps={{ htmlInput: { maxLength: 200 } }}
              error={invalid('school_name')}
              helperText={invalid('school_name') ? 'Informe o nome da sua escola.' : undefined}
            />
            <TextField
              id="phone"
              name="phone"
              label="Telefone com DDD"
              type="tel"
              placeholder="(11) 99999-9999"
              required
              disabled={disabled}
              value={phone}
              autoComplete="off"
              slotProps={{ htmlInput: { maxLength: 24 } }}
              error={!!phoneError || invalid('phone')}
              helperText={
                phoneError ||
                (invalid('phone') ? 'Confira o telefone e o DDD.' : 'Número brasileiro, com DDD.')
              }
              onChange={(event) => {
                setPhone(event.target.value)
                setPhoneError('')
                changeContact()
              }}
              onBlur={() => void checkContacts()}
            />
            <TextField
              id="email"
              name="email"
              label="E-mail"
              type="email"
              placeholder="voce@exemplo.com"
              required
              disabled={disabled}
              value={email}
              onChange={(event) => {
                setEmail(event.target.value)
                changeContact()
              }}
              onBlur={() => void checkContacts()}
              autoComplete="off"
              slotProps={{ htmlInput: { maxLength: 254 } }}
              error={invalid('email')}
              helperText={invalid('email') ? 'Informe um e-mail válido.' : undefined}
            />
            {match && (
              <Alert severity="info">
                {matchMessage} Ao continuar, você poderá retomar essa participação ou fazer um novo teste.
              </Alert>
            )}
            {lookupError && <Alert severity="error">{lookupError}</Alert>}
            <Alert
              severity="info"
              role="note"
              aria-label="Uso dos seus dados"
              icon={<PrivacyTipOutlined fontSize="small" />}
              sx={{ bgcolor: brand.paleBlue }}
            >
              <Typography variant="body2" sx={{ fontWeight: 700, mb: 0.5 }}>
                Sobre seus dados
              </Typography>
              <Typography variant="caption" component="p" sx={{ m: 0, whiteSpace: 'pre-line' }}>
                {quiz.privacy_notice_text}
              </Typography>
            </Alert>
            <Button
              variant="contained"
              type="submit"
              fullWidth
              disabled={disabled || !schoolName.trim()}
              loading={disabled}
              loadingPosition="end"
              endIcon={<ArrowForwardRounded />}
            >
              {checking ? 'Verificando participação…' : busy ? 'Iniciando…' : 'Começar meu quiz'}
            </Button>
          </Stack>
        </Box>
      </Paper>
      <Dialog
        open={prompt !== null}
        onClose={() => setPrompt(null)}
        aria-labelledby="existing-participation-title"
        aria-describedby="existing-participation-description"
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle id="existing-participation-title">
          Já encontramos uma participação sua
        </DialogTitle>
        <DialogContent>
          <DialogContentText id="existing-participation-description">
            {matchMessage} Deseja continuar de onde parou?
            {match?.status === 'completed' && ' Você poderá consultar seu resultado e encaminhamento.'}
            {match?.status === 'draft' && ' Marcações ainda não enviadas não são recuperadas após recarregar a página.'}
          </DialogContentText>
        </DialogContent>
        <DialogActions sx={{ flexWrap: 'wrap', gap: 1, px: 3, pb: 3 }}>
          <Button onClick={() => setPrompt(null)}>Voltar ao cadastro</Button>
          <Button variant="outlined" onClick={() => {
            if (!prompt) return
            onSubmit({ ...prompt, start_new: true })
            setPrompt(null)
          }}>
            Fazer novo teste
          </Button>
          <Button variant="contained" onClick={() => {
            if (!prompt) return
            onResume({ email: prompt.email, phone: prompt.phone })
            setPrompt(null)
          }}>
            Continuar participação
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
