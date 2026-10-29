import type { ReactNode } from 'react'
import {
  AppBar,
  Box,
  Button,
  Container,
  Link,
  Stack,
  Step,
  StepLabel,
  Stepper,
  Toolbar,
  Typography,
} from '@mui/material'
import LogoutRounded from '@mui/icons-material/LogoutRounded'
import { brand } from '../theme'

export function FlowLayout({
  children,
  active,
  busy,
  step,
  onExit,
}: {
  children: ReactNode
  active: boolean
  busy: boolean
  step: number | null
  onExit: () => void
}) {
  return (
    <>
      <Link className="skip-link" href="#main-content">
        Ir para o conteúdo
      </Link>
      <AppBar
        position="static"
        color="inherit"
        elevation={0}
        sx={{
          borderTop: '3px solid',
          borderTopColor: 'primary.main',
          borderBottom: 1,
          borderBottomColor: 'divider',
          bgcolor: 'background.paper',
        }}
      >
        <Container maxWidth="lg">
          <Toolbar disableGutters sx={{ py: 2, gap: { xs: 1.5, sm: 4 }, minHeight: 88 }}>
            <Link
              href="/"
              underline="none"
              color="textPrimary"
              aria-label="ISE Day, início"
              sx={{ display: 'flex', alignItems: 'center', gap: 1.5, flexShrink: 0 }}
            >
              <Box
                component="img"
                src="/brand/brasao-isecensa.png"
                alt="Brasão do ISECENSA"
                width={45}
                height={52}
                sx={{ objectFit: 'contain' }}
              />
              <Box>
                <Typography
                  component="span"
                  sx={{
                    display: 'block',
                    fontFamily: '"Open Sans", sans-serif',
                    fontWeight: 800,
                    fontSize: { xs: '1.05rem', sm: '1.2rem' },
                    lineHeight: 1.25,
                  }}
                >
                  ISECENSA
                </Typography>
                <Typography
                  component="span"
                  variant="caption"
                  sx={{ display: 'block', color: 'primary.main', letterSpacing: '.14em', mt: 0.5 }}
                >
                  ISE DAY
                </Typography>
              </Box>
            </Link>
            <Typography
              variant="overline"
              color="textSecondary"
              sx={{
                borderLeft: 1,
                borderColor: 'divider',
                pl: 3,
                display: { xs: 'none', sm: 'block' },
              }}
            >
              QUIZ DE AFINIDADES
            </Typography>
            <Box sx={{ ml: 'auto' }}>
              {active ? (
                <Button
                  variant="text"
                  disabled={busy}
                  onClick={onExit}
                  endIcon={<LogoutRounded />}
                  sx={{ fontSize: { xs: '.7rem', sm: '.8rem' }, px: { xs: 0.5, sm: 1.5 } }}
                >
                  Encerrar participação
                </Button>
              ) : (
                <Typography
                  variant="overline"
                  color="primary"
                  sx={{ display: { xs: 'none', md: 'block' } }}
                >
                  Seu próximo passo começa aqui
                </Typography>
              )}
            </Box>
          </Toolbar>
        </Container>
      </AppBar>
      <Container
        component="main"
        id="main-content"
        tabIndex={-1}
        maxWidth="lg"
        sx={{ mt: { xs: 3, sm: 4 }, mb: 8, minHeight: 'calc(100vh - 300px)' }}
      >
        {step !== null && (
          <Stepper
            component="ol"
            activeStep={step - 1}
            aria-label="Etapas do quiz"
            sx={{
              listStyle: 'none',
              px: 0,
              pb: 3,
              mb: { xs: 4, md: 5 },
              borderBottom: 1,
              borderColor: 'divider',
              '& .MuiStepLabel-label': { fontSize: { xs: '.65rem', sm: '.8rem' } },
              '& .MuiStepIcon-root': { fontSize: { xs: '1.2rem', sm: '1.5rem' } },
              '& .MuiStep-root': { px: { xs: 0.5, sm: 1 } },
              '& .MuiStepLabel-iconContainer': { pr: { xs: 0.5, sm: 1 } },
            }}
          >
            {['Sobre você', 'Suas escolhas', 'Sua descoberta'].map((label, index) => (
              <Step key={label} component="li">
                <StepLabel aria-current={step === index + 1 ? 'step' : undefined}>
                  {label}
                </StepLabel>
              </Step>
            ))}
          </Stepper>
        )}
        {children}
      </Container>
      <Box component="footer" sx={{ bgcolor: brand.footer, color: '#e2eaf1', py: 3.5 }}>
        <Container maxWidth="lg">
          <Stack
            direction={{ xs: 'column', sm: 'row' }}
            spacing={1}
            sx={{ justifyContent: 'space-between' }}
          >
            <Typography variant="caption">ISECENSA · ISE DAY · Quiz de afinidades</Typography>
            <Typography variant="caption">Há muitos caminhos para descobrir.</Typography>
          </Stack>
        </Container>
      </Box>
    </>
  )
}
