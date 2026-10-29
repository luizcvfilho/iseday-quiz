import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import {
  Alert,
  Autocomplete,
  Box,
  Button,
  CircularProgress,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import ArrowForwardRounded from '@mui/icons-material/ArrowForwardRounded'
import PrivacyTipOutlined from '@mui/icons-material/PrivacyTipOutlined'
import { api, errorMessage, normalizePhone } from '../api'
import type { CurrentQuiz, Registration, School } from '../api'
import { brand } from '../theme'
import { SectionHeading } from './Presentation'

type Props = {
  quiz: CurrentQuiz
  busy: boolean
  serverFields: string[]
  onSubmit: (data: Registration) => void
}

export function RegistrationForm({ quiz, busy, serverFields, onSubmit }: Props) {
  const [schools, setSchools] = useState<School[]>([])
  const [school, setSchool] = useState<School | null>(null)
  const [search, setSearch] = useState('')
  const [schoolInput, setSchoolInput] = useState('')
  const [schoolError, setSchoolError] = useState('')
  const [schoolLoading, setSchoolLoading] = useState(true)
  const [retry, setRetry] = useState(0)
  const [phoneError, setPhoneError] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    const timer = setTimeout(() => {
      setSchoolLoading(true)
      setSchoolError('')
      api
        .schools(search, controller.signal)
        .then((items) => {
          if (!controller.signal.aborted) setSchools(items)
        })
        .catch((error) => {
          if (!controller.signal.aborted) setSchoolError(errorMessage(error))
        })
        .finally(() => {
          if (!controller.signal.aborted) setSchoolLoading(false)
        })
    }, 250)
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [search, retry])

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy || !school) return
    const fields = new FormData(event.currentTarget)
    const phone = normalizePhone(String(fields.get('phone')))
    if (!phone) {
      setPhoneError('Informe um telefone brasileiro com DDD e 10 ou 11 dígitos.')
      return
    }
    setPhoneError('')
    onSubmit({
      quiz_version_id: quiz.id,
      school_id: school.id,
      full_name: String(fields.get('full_name')).trim(),
      phone,
      email: String(fields.get('email')).trim(),
      privacy_notice_version: quiz.privacy_notice_version,
    })
  }
  const invalid = (field: string) => serverFields.includes(field)
  const options =
    school && !schools.some((item) => item.id === school.id) ? [school, ...schools] : schools

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
        <Box component="form" onSubmit={submit} autoComplete="off">
          <Stack spacing={2.5}>
            <TextField
              id="full-name"
              name="full_name"
              label="Nome completo"
              placeholder="Como podemos chamar você?"
              required
              disabled={busy}
              autoComplete="off"
              slotProps={{ htmlInput: { minLength: 2, maxLength: 200 } }}
              error={invalid('full_name')}
              helperText={invalid('full_name') ? 'Informe seu nome completo.' : undefined}
            />
            <Autocomplete
              id="school"
              options={options}
              value={school}
              inputValue={schoolInput}
              disabled={busy}
              loading={schoolLoading}
              filterOptions={(items) => items}
              isOptionEqualToValue={(a, b) => a.id === b.id}
              getOptionLabel={(item) => item.name + (item.city ? ' · ' + item.city : '')}
              onChange={(_, value) => {
                setSchool(value)
                setSchoolInput(value ? value.name + (value.city ? ' · ' + value.city : '') : '')
              }}
              onInputChange={(_, value, reason) => {
                if (reason === 'input' || reason === 'clear') {
                  setSchoolInput(value)
                  setSchool(null)
                  setSearch(value.slice(0, 100))
                  setSchoolLoading(true)
                }
              }}
              loadingText="Buscando escolas…"
              noOptionsText="Nenhuma escola encontrada."
              renderInput={(params) => (
                <TextField
                  {...params}
                  label="Escola"
                  placeholder="Busque pelo nome da sua escola"
                  required
                  autoComplete="off"
                  error={invalid('school_id') || !!schoolError}
                  helperText={
                    schoolError ||
                    (invalid('school_id')
                      ? 'Selecione uma escola ativa da lista.'
                      : 'Não encontrou sua escola? Procure a equipe do evento.')
                  }
                  slotProps={{
                    ...params.slotProps,
                    htmlInput: {
                      ...params.slotProps.htmlInput,
                      maxLength: 100,
                      autoComplete: 'off',
                    },
                    input: {
                      ...params.slotProps.input,
                      endAdornment: (
                        <>
                          {schoolLoading && (
                            <CircularProgress
                              color="inherit"
                              size={18}
                              aria-label="Buscando escolas"
                            />
                          )}
                          {params.slotProps.input.endAdornment}
                        </>
                      ),
                    },
                  }}
                />
              )}
            />
            {schoolError && (
              <Button variant="text" onClick={() => setRetry((n) => n + 1)} disabled={busy}>
                Buscar novamente
              </Button>
            )}
            <TextField
              id="phone"
              name="phone"
              label="Telefone com DDD"
              type="tel"
              placeholder="(11) 99999-9999"
              required
              disabled={busy}
              autoComplete="off"
              slotProps={{ htmlInput: { maxLength: 24 } }}
              error={!!phoneError || invalid('phone')}
              helperText={
                phoneError ||
                (invalid('phone') ? 'Confira o telefone e o DDD.' : 'Número brasileiro, com DDD.')
              }
              onChange={() => setPhoneError('')}
            />
            <TextField
              id="email"
              name="email"
              label="E-mail"
              type="email"
              placeholder="voce@exemplo.com"
              required
              disabled={busy}
              autoComplete="off"
              slotProps={{ htmlInput: { maxLength: 254 } }}
              error={invalid('email')}
              helperText={invalid('email') ? 'Informe um e-mail válido.' : undefined}
            />
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
              disabled={busy || !school}
              loading={busy}
              loadingPosition="end"
              endIcon={<ArrowForwardRounded />}
            >
              {busy ? 'Iniciando…' : 'Começar meu quiz'}
            </Button>
          </Stack>
        </Box>
      </Paper>
    </Box>
  )
}
