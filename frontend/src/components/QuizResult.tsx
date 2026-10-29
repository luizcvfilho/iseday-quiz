import { useState } from 'react'
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  FormControl,
  FormControlLabel,
  FormLabel,
  List,
  ListItem,
  Paper,
  Radio,
  RadioGroup,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import ArrowForwardRounded from '@mui/icons-material/ArrowForwardRounded'
import ExpandMoreRounded from '@mui/icons-material/ExpandMoreRounded'
import NorthEastRounded from '@mui/icons-material/NorthEastRounded'
import type { Feedback, Result } from '../api'
import { brand } from '../theme'
import { SectionHeading } from './Presentation'

export function QuizResult({
  result,
  busy,
  uncertain,
  onConfirm,
}: {
  result: Result
  busy: boolean
  uncertain: boolean
  onConfirm: (data: Feedback) => void
}) {
  const [agrees, setAgrees] = useState<boolean | null>(null)
  const [course, setCourse] = useState('')
  const winners = result.areas.filter((a) => a.is_winner)
  const recommended = result.courses.filter((c) => c.is_recommended)
  return (
    <Box component="section" aria-labelledby="result-title" sx={{ maxWidth: 960, mx: 'auto' }}>
      <SectionHeading
        id="result-title"
        tag="SUA DESCOBERTA COMEÇA AQUI"
        title={
          <>
            Novas possibilidades
            <br />
            para{' '}
            <Box component="span" sx={{ color: 'primary.main' }}>
              explorar.
            </Box>
          </>
        }
      >
        Suas escolhas apontam afinidade com {winners.length === 1 ? 'esta área' : 'estas áreas'}.
        Conheça os cursos que se destacaram em cada uma.
      </SectionHeading>
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(min(270px, 100%), 1fr))',
          gap: 2.5,
          my: 4,
        }}
      >
        {winners.map((area, index) => (
          <Card
            component="article"
            key={area.id}
            sx={{ background: brand.gradient, color: 'white', border: 0 }}
          >
            <CardContent sx={{ p: 3.5, '&:last-child': { pb: 3.5 } }}>
              <Stack
                direction="row"
                sx={{ alignItems: 'center', justifyContent: 'space-between', mb: 3 }}
              >
                <Typography variant="overline" sx={{ color: '#dceefa' }}>
                  ÁREA DE AFINIDADE
                </Typography>
                <Stack direction="row" spacing={1} aria-hidden="true" sx={{ alignItems: 'center' }}>
                  <Typography variant="caption">{String(index + 1).padStart(2, '0')}</Typography>
                  <NorthEastRounded fontSize="small" />
                </Stack>
              </Stack>
              <Typography component="h2" variant="h4" sx={{ mb: 3 }}>
                {area.name}
              </Typography>
              <Typography variant="caption" sx={{ color: '#dceefa' }}>
                Cursos para conhecer
              </Typography>
              <List disablePadding>
                {recommended
                  .filter((c) => c.area_id === area.id)
                  .map((c) => (
                    <ListItem
                      key={c.id}
                      sx={{ px: 0, mt: 1.25, pt: 1.5, pb: 0.5, borderTop: '1px solid #ffffff40' }}
                    >
                      <Typography>{c.name}</Typography>
                    </ListItem>
                  ))}
              </List>
            </CardContent>
          </Card>
        ))}
      </Box>
      <Typography variant="body2" color="textSecondary" sx={{ maxWidth: 680, mb: 3 }}>
        Um ponto de partida para conhecer possibilidades. Seus interesses podem mudar, e a escolha
        do seu caminho continua sendo sua.
      </Typography>
      <Accordion
        elevation={0}
        disableGutters
        sx={{
          mb: 4,
          border: 1,
          borderColor: 'divider',
          borderRadius: '14px !important',
          '&::before': { display: 'none' },
        }}
      >
        <AccordionSummary expandIcon={<ExpandMoreRounded />}>
          <Typography variant="body2" color="primary">
            Ver pontuação por área
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          <List disablePadding sx={{ maxWidth: 600 }}>
            {result.areas.map((a) => (
              <ListItem
                key={a.id}
                sx={{
                  px: 0,
                  borderBottom: 1,
                  borderColor: 'divider',
                  display: 'flex',
                  justifyContent: 'space-between',
                  gap: 2,
                }}
              >
                <Typography variant="body2">{a.name}</Typography>
                <Typography variant="body2" sx={{ fontWeight: 700, whiteSpace: 'nowrap' }}>
                  {a.score} {a.score === 1 ? 'ponto' : 'pontos'}
                </Typography>
              </ListItem>
            ))}
          </List>
          <Typography variant="caption" component="p" color="textSecondary" sx={{ mt: 2 }}>
            Os pontos representam suas escolhas neste quiz, sem indicar um percentual de
            compatibilidade. Todos os empates são preservados.
          </Typography>
        </AccordionDetails>
      </Accordion>
      <Paper
        component="form"
        variant="outlined"
        sx={{ p: { xs: 2.5, sm: 4 } }}
        onSubmit={(event) => {
          event.preventDefault()
          if (agrees !== null && (!agrees || course) && !busy)
            onConfirm({ agrees_with_result: agrees, chosen_course_id: agrees ? course : null })
        }}
      >
        <FormControl component="fieldset" disabled={busy || uncertain} fullWidth>
          <FormLabel component="legend" sx={{ typography: 'h5', color: 'text.primary', mb: 1 }}>
            Esse resultado faz sentido para você?
          </FormLabel>
          <Typography variant="body2" color="textSecondary" sx={{ mb: 3 }}>
            Conte para a gente e descubra seu próximo destino no evento.
          </Typography>
          <RadioGroup
            row
            name="agreement"
            value={agrees === null ? '' : agrees ? 'yes' : 'no'}
            onChange={(_, value) => {
              setAgrees(value === 'yes')
              if (value === 'no') setCourse('')
            }}
            sx={{ gap: 1.5, mb: 3 }}
          >
            {[
              { value: 'yes', label: 'Sim, faz sentido', selected: agrees === true },
              { value: 'no', label: 'Não me identifiquei', selected: agrees === false },
            ].map((option) => (
              <Paper
                key={option.value}
                variant="outlined"
                sx={{
                  borderColor: option.selected ? 'primary.main' : 'divider',
                  bgcolor: option.selected ? brand.paleBlue : 'background.paper',
                  flex: { xs: '1 0 100%', sm: 'initial' },
                }}
              >
                <FormControlLabel
                  value={option.value}
                  control={<Radio />}
                  label={option.label}
                  sx={{
                    mx: 0,
                    pr: 2,
                    py: 0.5,
                    width: '100%',
                    '& .MuiFormControlLabel-label': { typography: 'body2' },
                  }}
                />
              </Paper>
            ))}
          </RadioGroup>
          {agrees === true && (
            <TextField
              id="chosen-course"
              select
              label="Qual curso você quer conhecer?"
              required
              value={course}
              disabled={busy || uncertain}
              onChange={(event) => setCourse(event.target.value)}
              helperText="Sua escolha não altera a pontuação do quiz."
              slotProps={{ select: { native: true }, inputLabel: { shrink: true } }}
              sx={{ maxWidth: 600, mb: 3 }}
            >
              <option value="">Escolha entre os cursos sugeridos</option>
              {recommended.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} · {winners.find((a) => a.id === c.area_id)?.name}
                </option>
              ))}
            </TextField>
          )}
          {agrees === false && (
            <Alert severity="info" sx={{ mb: 3 }}>
              A equipe de Psicologia no SPA pode conversar com você sobre seus interesses e
              possibilidades.
            </Alert>
          )}
        </FormControl>
        <Button
          variant="contained"
          type="submit"
          disabled={busy || agrees === null || (agrees && !course)}
          loading={busy}
          loadingPosition="end"
          endIcon={<ArrowForwardRounded />}
          sx={{ width: { xs: '100%', sm: 'auto' } }}
        >
          {busy ? 'Confirmando…' : 'Ver meu encaminhamento'}
        </Button>
      </Paper>
    </Box>
  )
}
