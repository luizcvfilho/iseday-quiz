import { createTheme } from '@mui/material/styles'
import { ptBR } from '@mui/material/locale'

// References: isecensa.edu.br home, inspected 2026-10-29. These are application
// tokens based on the website, not a substitute for an institutional brand manual.
export const brand = {
  blue: '#006aa3',
  navy: '#0b172b',
  deepBlue: '#0b3d65',
  footer: '#001a33',
  sky: '#0a81b8',
  gold: '#d3a64a',
  sand: '#f0e7da',
  paleBlue: '#edf5fb',
  gradient: 'linear-gradient(135deg, #0b3d65 0%, #0a81b8 100%)',
}

export const theme = createTheme(
  {
    cssVariables: true,
    palette: {
      primary: { main: brand.blue, dark: brand.deepBlue, light: '#dceefa' },
      secondary: { main: '#8a651c', light: brand.sand },
      background: { default: '#fff', paper: '#fff' },
      text: { primary: brand.navy, secondary: '#526376' },
      divider: '#dae4ed',
      info: { main: brand.blue },
    },
    typography: {
      fontFamily: 'Inter, Arial, sans-serif',
      h1: {
        fontFamily: '"Open Sans", Arial, sans-serif',
        fontWeight: 800,
        letterSpacing: '-0.045em',
        lineHeight: 1.13,
      },
      h2: {
        fontFamily: '"Open Sans", Arial, sans-serif',
        fontWeight: 800,
        letterSpacing: '-0.035em',
        lineHeight: 1.2,
      },
      h3: {
        fontFamily: '"Open Sans", Arial, sans-serif',
        fontWeight: 800,
        letterSpacing: '-0.025em',
        lineHeight: 1.25,
      },
      h4: {
        fontFamily: '"Open Sans", Arial, sans-serif',
        fontWeight: 700,
        letterSpacing: '-0.025em',
      },
      h5: { fontFamily: '"Open Sans", Arial, sans-serif', fontWeight: 700 },
      h6: { fontFamily: '"Open Sans", Arial, sans-serif', fontWeight: 700 },
      body1: { lineHeight: 1.7 },
      body2: { lineHeight: 1.65 },
      button: { textTransform: 'none', fontWeight: 700 },
      overline: { fontSize: '.65rem', fontWeight: 700, letterSpacing: '.14em', lineHeight: 1.8 },
    },
    shape: { borderRadius: 14 },
    components: {
      MuiButton: {
        defaultProps: { disableElevation: true },
        styleOverrides: {
          root: { minHeight: 48, padding: '12px 22px', borderRadius: 12 },
          outlined: { borderColor: '#afc6d8' },
          text: { minHeight: 44, padding: '8px 12px' },
        },
      },
      MuiTextField: { defaultProps: { fullWidth: true, variant: 'outlined' } },
      MuiOutlinedInput: {
        styleOverrides: { root: { borderRadius: 10 }, input: { fontSize: '.9rem' } },
      },
      MuiInputLabel: { styleOverrides: { root: { fontSize: '.9rem' } } },
      MuiFormHelperText: {
        styleOverrides: { root: { marginLeft: 0, marginRight: 0, fontSize: '.7rem' } },
      },
      MuiPaper: { styleOverrides: { root: { backgroundImage: 'none' } } },
      MuiCard: { defaultProps: { variant: 'outlined' } },
      MuiAlert: { styleOverrides: { root: { borderRadius: 12 }, message: { minWidth: 0 } } },
      MuiCheckbox: { styleOverrides: { root: { padding: 10 } } },
      MuiRadio: { styleOverrides: { root: { padding: 10 } } },
      MuiDialog: { defaultProps: { fullWidth: true, maxWidth: 'sm' } },
      MuiDialogTitle: {
        styleOverrides: { root: { padding: '28px 28px 12px', fontSize: '1.35rem' } },
      },
      MuiDialogContent: { styleOverrides: { root: { padding: '8px 28px 16px' } } },
      MuiDialogActions: {
        styleOverrides: { root: { padding: '16px 28px 28px', gap: 8, flexWrap: 'wrap' } },
      },
      MuiCssBaseline: {
        styleOverrides: {
          body: { minWidth: 320 },
          'h1:focus': { outline: 'none' },
          '*:focus-visible': { outline: `3px solid ${brand.blue}`, outlineOffset: 3 },
          '@media (prefers-reduced-motion: reduce)': {
            '*, *::before, *::after': {
              animationDuration: '.01ms !important',
              transitionDuration: '.01ms !important',
              scrollBehavior: 'auto !important',
            },
          },
        },
      },
    },
  },
  ptBR,
)
