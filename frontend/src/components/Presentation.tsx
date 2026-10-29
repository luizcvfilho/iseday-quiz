import type { ReactNode } from 'react'
import { Box, CircularProgress, Stack, Typography } from '@mui/material'

export function Eyebrow({ children }: { children: ReactNode }) {
  return (
    <Typography
      component="span"
      variant="overline"
      color="primary"
      sx={{ display: 'block', mb: 2 }}
    >
      {children}
    </Typography>
  )
}

export function SectionHeading({
  id,
  tag,
  title,
  children,
  centered = false,
}: {
  id?: string
  tag: string
  title: ReactNode
  children?: ReactNode
  centered?: boolean
}) {
  return (
    <Box sx={{ mb: 3.5, textAlign: centered ? 'center' : 'left' }}>
      <Eyebrow>{tag}</Eyebrow>
      <Typography
        id={id}
        component="h1"
        tabIndex={-1}
        variant="h1"
        sx={{ fontSize: { xs: '2.1rem', sm: '2.8rem', md: '3.3rem' }, mb: 2.5 }}
      >
        {title}
      </Typography>
      {children && (
        <Typography
          component="p"
          color="textSecondary"
          sx={{
            fontSize: { xs: '.95rem', sm: '1.05rem' },
            maxWidth: 650,
            mx: centered ? 'auto' : 0,
          }}
        >
          {children}
        </Typography>
      )}
    </Box>
  )
}

export function StatusScreen({
  tag,
  title,
  children,
  actions,
  loading = false,
}: {
  tag: string
  title: string
  children: ReactNode
  actions?: ReactNode
  loading?: boolean
}) {
  return (
    <Box
      component="section"
      role={loading ? 'status' : undefined}
      sx={{ maxWidth: 720, mx: 'auto', my: { xs: 6, md: 10 }, textAlign: 'center' }}
    >
      {loading && <CircularProgress size={32} sx={{ mb: 3 }} />}
      <SectionHeading tag={tag} title={title} centered>
        {children}
      </SectionHeading>
      {actions && (
        <Stack
          direction={{ xs: 'column', sm: 'row' }}
          spacing={1.5}
          sx={{ justifyContent: 'center', mt: 3 }}
        >
          {actions}
        </Stack>
      )}
    </Box>
  )
}
