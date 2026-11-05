import { useCallback, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Link, NavLink, Navigate, Outlet, useLocation, useNavigate } from 'react-router'
import {
  Alert,
  AppBar,
  Box,
  Button,
  Container,
  Paper,
  Stack,
  TextField,
  Toolbar,
  Typography,
} from '@mui/material'
import { ApiError, errorMessage } from '../api'
import { StatusScreen } from '../components/Presentation'
import { adminApi } from './api'
import type { Admin } from './api'

import { AdminContext, useAdmin } from './context'

export function AdminProvider() {
  const [user, setUser] = useState<Admin | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [ending, setEnding] = useState(false)
  const channel = useRef<BroadcastChannel | null>(null)
  const call = useCallback(async <T,>(work: () => Promise<T>): Promise<T> => {
    try {
      return await work()
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) setUser(null)
      throw e
    }
  }, [])
  const check = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      setUser(await adminApi.me())
    } catch (e) {
      setUser(null)
      if (!(e instanceof ApiError && e.status === 401)) setError(errorMessage(e))
    } finally {
      setLoading(false)
    }
  }, [])
  useEffect(() => {
    let active = true
    void adminApi
      .me()
      .then((identity) => {
        if (active) setUser(identity)
      })
      .catch((e) => {
        if (active && !(e instanceof ApiError && e.status === 401)) setError(errorMessage(e))
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [])
  useEffect(() => {
    if (typeof BroadcastChannel === 'undefined') return
    const current = new BroadcastChannel('iseday-admin')
    channel.current = current
    current.onmessage = () => {
      setUser(null)
    }
    return () => {
      current.close()
      channel.current = null
    }
  }, [])
  useEffect(() => {
    if (!user) return
    const timer = window.setTimeout(
      () => setUser(null),
      Math.max(0, Date.parse(user.expires_at) - Date.now()),
    )
    const refresh = () => {
      if (document.visibilityState === 'visible') void call(adminApi.me).catch(() => {})
    }
    document.addEventListener('visibilitychange', refresh)
    return () => {
      window.clearTimeout(timer)
      document.removeEventListener('visibilitychange', refresh)
    }
  }, [user, call])
  const signIn = async (email: string, password: string) => {
    const identity = await adminApi.login(email, password)
    setUser(identity)
  }
  const signOut = async () => {
    setEnding(true)
    setUser(null)
    setError('')
    channel.current?.postMessage('logout')
    try {
      await adminApi.logout()
      setEnding(false)
    } catch (e) {
      setError(errorMessage(e))
    }
  }
  if (loading || error || ending)
    return (
      <AdminShell>
        <StatusScreen
          tag="ADMINISTRAÇÃO"
          title={
            ending
              ? 'Encerrando acesso'
              : loading
                ? 'Verificando acesso'
                : 'Acesso indisponível'
          }
          loading={loading || (ending && !error)}
          actions={
            error && (
              <Button variant="contained" onClick={() => void (ending ? signOut() : check())}>
                Tentar novamente
              </Button>
            )
          }
        >
          {error ||
            (ending ? 'Aguarde a confirmação do encerramento.' : 'Aguarde um instante.')}
        </StatusScreen>
      </AdminShell>
    )
  return (
    <AdminContext.Provider value={{ user, call, signIn, signOut }}>
      <Outlet />
    </AdminContext.Provider>
  )
}

export function AdminShell({
  children,
  user,
  onExit,
}: {
  children: ReactNode
  user?: Admin
  onExit?: () => void
}) {
  return (
    <>
      <a className="skip-link" href="#admin-content">
        Ir para o conteúdo
      </a>
      <AppBar
        position="static"
        color="inherit"
        elevation={0}
        sx={{
          borderTop: 3,
          borderTopColor: 'primary.main',
          borderBottom: 1,
          borderBottomColor: 'divider',
        }}
      >
        <Container maxWidth="lg">
          <Toolbar disableGutters sx={{ py: 1.5, gap: 2, flexWrap: 'wrap' }}>
            <Box
              component={Link}
              to="/admin"
              sx={{
                display: 'flex',
                alignItems: 'center',
                gap: 1.5,
                textDecoration: 'none',
                color: 'text.primary',
              }}
            >
              <Box
                component="img"
                src="/brand/brasao-isecensa.png"
                alt="Brasão do ISECENSA"
                sx={{ width: 38, height: 46, objectFit: 'contain' }}
              />
              <Box>
                <Typography sx={{ fontWeight: 800 }}>ISECENSA · ISE DAY</Typography>
                <Typography variant="caption" color="primary">
                  ÁREA ADMINISTRATIVA
                </Typography>
              </Box>
            </Box>
            <Stack direction="row" spacing={2} sx={{ ml: 'auto', alignItems: 'center' }}>
              {user && (
                <Typography variant="body2" sx={{ display: { xs: 'none', sm: 'block' } }}>
                  {user.name}
                </Typography>
              )}
              {onExit ? (
                <Button onClick={onExit}>Sair</Button>
              ) : (
                <Button component={Link} to="/">
                  Voltar ao quiz
                </Button>
              )}
            </Stack>
          </Toolbar>
          {user && (
            <Stack
              component="nav"
              aria-label="Administração"
              direction="row"
              spacing={1}
              sx={{ pb: 2, flexWrap: 'wrap' }}
            >
              {[
                ['/admin', 'Participações'],
                ['/admin/versions', 'Versões e destinos'],
              ].map(([path, label]) => (
                <Button
                  key={path}
                  component={NavLink}
                  to={path}
                  end={path === '/admin'}
                  sx={{ '&.active': { bgcolor: 'action.selected', fontWeight: 800 } }}
                >
                  {label}
                </Button>
              ))}
            </Stack>
          )}
        </Container>
      </AppBar>
      <Container
        component="main"
        id="admin-content"
        tabIndex={-1}
        maxWidth="lg"
        sx={{ py: { xs: 3, md: 5 }, minHeight: 'calc(100vh - 160px)' }}
      >
        {children}
      </Container>
      <Container component="footer" maxWidth="lg" sx={{ py: 3 }}>
        <Typography variant="caption" color="text.secondary">
          ISECENSA · Administração do ISE Day
        </Typography>
      </Container>
    </>
  )
}

export function RequireAdmin() {
  const { user, signOut } = useAdmin()
  const location = useLocation()
  if (!user)
    return (
      <Navigate
        to="/admin/login"
        replace
        state={{ from: location.pathname + location.search }}
      />
    )
  return (
    <AdminShell user={user} onExit={() => void signOut()}>
      <Outlet />
    </AdminShell>
  )
}

export function AdminLogin() {
  const { user, signIn } = useAdmin()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const from = location.state?.from
  const destination =
    typeof from === 'string' &&
    /^\/admin(?:\?|$|\/(?:participations|versions)(?:\/|\?|$))/.test(from)
      ? from
      : '/admin'
  if (user) return <Navigate to={destination} replace />
  return (
    <AdminShell>
      <Paper
        component="section"
        variant="outlined"
        sx={{
          maxWidth: 460,
          mx: 'auto',
          my: { xs: 2, md: 6 },
          p: { xs: 3, sm: 4 },
        }}
      >
        <Typography variant="overline" color="primary">
          ACESSO DA EQUIPE
        </Typography>
        <Typography component="h1" variant="h4" sx={{ mt: 1, mb: 2 }}>
          Entrar na administração
        </Typography>
        <Typography color="text.secondary" sx={{ mb: 3 }}>
          Gerencie o quiz e consulte as participações dos estudantes.
        </Typography>
        <Box
          component="form"
          onSubmit={async (event) => {
            event.preventDefault()
            setBusy(true)
            setError('')
            try {
              await signIn(email.trim(), password)
              navigate(destination, { replace: true })
            } catch (e) {
              setError(errorMessage(e))
            } finally {
              setPassword('')
              setBusy(false)
            }
          }}
        >
          <Stack spacing={2.5}>
            {error && <Alert severity="error">{error}</Alert>}
            <TextField
              label="E-mail"
              type="email"
              autoComplete="username"
              required
              fullWidth
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={busy}
              slotProps={{ htmlInput: { maxLength: 254 } }}
            />
            <TextField
              label="Senha"
              type="password"
              autoComplete="current-password"
              required
              fullWidth
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={busy}
              slotProps={{ htmlInput: { maxLength: 1024 } }}
            />
            <Button type="submit" variant="contained" size="large" disabled={busy}>
              {busy ? 'Entrando…' : 'Entrar'}
            </Button>
            <Typography variant="caption" color="text.secondary">
              O acesso é exclusivo para administradores cadastrados. Para criar uma conta ou
              redefinir sua senha, procure o responsável pelo sistema.
            </Typography>
          </Stack>
        </Box>
      </Paper>
    </AdminShell>
  )
}
