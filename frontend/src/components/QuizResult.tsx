import { useState } from 'react'
import {
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
  Typography,
} from '@mui/material'
import ArrowForwardRounded from '@mui/icons-material/ArrowForwardRounded'
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
        Conheça os cursos que se destacaram em cada uma e visite seus estandes no ginásio.
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
      <Paper
        component="form"
        variant="outlined"
        sx={{ p: { xs: 2.5, sm: 4 } }}
        onSubmit={(event) => {
          event.preventDefault()
          if (agrees !== null && !busy && !uncertain)
            onConfirm({ agrees_with_result: agrees })
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
            }}
            sx={{ gap: 1.5, mb: 3 }}
          >
            {[
              { value: 'yes', label: 'Concordo com o resultado', selected: agrees === true },
              { value: 'no', label: 'Não concordo', selected: agrees === false },
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
        </FormControl>
        <Button
          variant="contained"
          type="submit"
          disabled={busy || uncertain || agrees === null}
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
