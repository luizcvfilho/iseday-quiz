import {
  Box,
  Button,
  Checkbox,
  FormControlLabel,
  LinearProgress,
  List,
  ListItem,
  Paper,
  Stack,
  Typography,
} from '@mui/material'
import ArrowForwardRounded from '@mui/icons-material/ArrowForwardRounded'
import InfoOutlined from '@mui/icons-material/InfoOutlined'
import type { Quiz } from '../api'
import { brand } from '../theme'
import { SectionHeading } from './Presentation'

type Props = {
  quiz: Quiz
  selected: string[]
  review: boolean
  busy: boolean
  uncertain: boolean
  onToggle: (id: string) => void
  onReview: () => void
  onEdit: () => void
  onSubmit: () => void
}
export function QuizSelection({
  quiz,
  selected,
  review,
  busy,
  uncertain,
  onToggle,
  onReview,
  onEdit,
  onSubmit,
}: Props) {
  const limit = quiz.required_selection_count
  const complete = selected.length === limit
  const statements = review
    ? quiz.statements.filter((s) => selected.includes(s.id))
    : quiz.statements
  return (
    <Box component="section" aria-labelledby="quiz-title">
      <SectionHeading
        id="quiz-title"
        tag={review ? 'ANTES DE ENVIAR' : 'SEUS INTERESSES, SUAS ESCOLHAS'}
        title={review ? 'Está tudo com a sua cara?' : 'O que combina com você?'}
      >
        {review
          ? 'Confira suas 25 escolhas. Depois de enviar, elas não poderão ser alteradas.'
          : 'Marque exatamente 25 afirmativas com as quais você mais se identifica. Não existem respostas certas ou erradas.'}
      </SectionHeading>
      {!review && (
        <Stack
          direction="row"
          spacing={1}
          sx={{ alignItems: 'center', color: 'primary.main', mb: 2 }}
        >
          <InfoOutlined fontSize="small" />
          <Typography variant="body2">
            Ao chegar a 25, desmarque uma afirmativa para escolher outra.
          </Typography>
        </Stack>
      )}
      <Paper
        variant="outlined"
        sx={{
          position: 'sticky',
          top: 12,
          zIndex: 2,
          p: { xs: 2, sm: 2.5 },
          mb: 3,
          bgcolor: brand.paleBlue,
          display: 'flex',
          alignItems: 'center',
          gap: { xs: 2, sm: 4 },
        }}
      >
        <Typography
          component="div"
          aria-live="polite"
          aria-atomic="true"
          sx={{ whiteSpace: 'nowrap', fontSize: '.8rem' }}
        >
          <Box component="strong" sx={{ fontSize: '1.5rem', color: 'primary.main' }}>
            {selected.length}
          </Box>{' '}
          de {limit} selecionadas
        </Typography>
        <LinearProgress
          variant="determinate"
          value={(selected.length / limit) * 100}
          aria-label="Afirmativas selecionadas"
          sx={{ flex: 1, height: 6, borderRadius: 3 }}
        />
        <Typography variant="caption" sx={{ display: { xs: 'none', sm: 'block' } }}>
          {complete
            ? 'Tudo pronto para revisar'
            : 'Faltam ' + (limit - selected.length) + ' escolhas'}
        </Typography>
      </Paper>
      {review ? (
        <List
          component="ol"
          aria-label="Suas 25 escolhas"
          sx={{
            p: 0,
            mb: 18,
            display: 'grid',
            gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' },
            gap: 1.25,
          }}
        >
          {statements.map((s) => (
            <ListItem
              key={s.id}
              sx={{ border: 1, borderColor: 'divider', borderRadius: 1, gap: 2, p: 2 }}
            >
              <Typography variant="caption" color="textSecondary">
                {String(s.display_order).padStart(2, '0')}
              </Typography>
              <Typography variant="body2">{s.text}</Typography>
            </ListItem>
          ))}
        </List>
      ) : (
        <Box
          role="group"
          aria-label="Afirmativas do quiz"
          sx={{
            display: 'grid',
            gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' },
            gap: 1.25,
            mb: 18,
          }}
        >
          {statements.map((s) => {
            const checked = selected.includes(s.id)
            const disabled = busy || (!checked && complete)
            return (
              <Paper
                key={s.id}
                variant="outlined"
                sx={{
                  bgcolor: checked ? brand.paleBlue : disabled ? '#f6f8fa' : 'background.paper',
                  borderColor: checked ? 'primary.main' : 'divider',
                  '&:hover': disabled ? {} : { borderColor: 'primary.main' },
                  '&:has(:focus-visible)': {
                    outline: '3px solid',
                    outlineColor: 'primary.main',
                    outlineOffset: 2,
                  },
                }}
              >
                <FormControlLabel
                  disabled={disabled}
                  labelPlacement="start"
                  sx={{
                    width: '100%',
                    m: 0,
                    p: 1.5,
                    gap: 1,
                    minHeight: 76,
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    '& .MuiFormControlLabel-label': { flex: 1 },
                  }}
                  control={<Checkbox checked={checked} onChange={() => onToggle(s.id)} />}
                  label={
                    <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center' }}>
                      <Typography
                        component="span"
                        variant="caption"
                        color="textSecondary"
                        aria-hidden="true"
                      >
                        {String(s.display_order).padStart(2, '0')}
                      </Typography>
                      <Typography component="span" variant="body2">
                        {s.text}
                      </Typography>
                    </Stack>
                  }
                />
              </Paper>
            )
          })}
        </Box>
      )}
      <Paper
        elevation={3}
        sx={{
          position: 'fixed',
          bottom: { xs: 0, sm: 20 },
          left: '50%',
          transform: 'translateX(-50%)',
          width: { xs: '100%', sm: '92%' },
          maxWidth: 1100,
          zIndex: 3,
          p: { xs: 2, sm: 2.5 },
          pb: { xs: 'max(16px, env(safe-area-inset-bottom))', sm: 2.5 },
          border: 1,
          borderColor: 'divider',
          borderRadius: { xs: '14px 14px 0 0', sm: 1 },
          bgcolor: '#fffffffa',
          backdropFilter: 'blur(12px)',
        }}
      >
        <Stack
          direction="row"
          spacing={2}
          sx={{ alignItems: 'center', justifyContent: 'space-between' }}
        >
          <Box sx={{ display: { xs: 'none', sm: 'block' } }}>
            <Typography variant="body2" sx={{ fontWeight: 700 }}>
              {review
                ? 'Suas escolhas estão prontas'
                : selected.length + ' de ' + limit + ' escolhas'}
            </Typography>
            <Typography variant="caption" color="textSecondary">
              {review ? 'Vamos descobrir suas afinidades?' : 'Escolha no seu tempo.'}
            </Typography>
          </Box>
          <Stack
            direction="row"
            spacing={1.5}
            sx={{
              width: { xs: '100%', sm: 'auto' },
              '& .MuiButton-root': { flex: { xs: 1, sm: 'initial' } },
            }}
          >
            {review && (
              <Button variant="outlined" onClick={onEdit} disabled={busy || uncertain}>
                Voltar e editar
              </Button>
            )}
            <Button
              variant="contained"
              disabled={!complete || busy}
              loading={busy}
              loadingPosition="end"
              endIcon={<ArrowForwardRounded />}
              onClick={review ? onSubmit : onReview}
            >
              {busy ? 'Enviando…' : review ? 'Confirmar 25 escolhas' : 'Revisar escolhas'}
            </Button>
          </Stack>
        </Stack>
      </Paper>
    </Box>
  )
}
