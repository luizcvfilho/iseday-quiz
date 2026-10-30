import { request } from '../api'
import type { Participant, Result, Statement } from '../api'

export type Named = { id: string; name: string }
export type Admin = Named & { email: string; expires_at: string }
export type AdminOptions = {
  schools: Named[]
  versions: (Named & { version_number: number })[]
  areas: (Named & { quiz_version_id: string })[]
  courses: (Named & { quiz_version_id: string })[]
}
export type ParticipationRow = {
  id: string
  full_name: string
  school: Named
  quiz_version_id: string
  version_number: number
  status: Participant['status']
  started_at: string
  submitted_at: string | null
  completed_at: string | null
  agrees_with_result: boolean | null
  winning_areas: Named[]
  recommended_courses: Named[]
}
export type ParticipationPage = {
  items: ParticipationRow[]
  total: number
  page: number
  page_size: number
}
export type ParticipationDetail = ParticipationRow & {
  email: string
  phone: string
  event_name: string
  privacy_notice_version: string
  selections: Statement[]
  result: Result | null
}
export type Count = Named & { count: number; version_number?: number | null }
export type Summary = {
  total: number
  draft: number
  submitted: number
  completed: number
  agreed: number
  disagreed: number
  agreement_rate: number | null
  schools: Count[]
  areas: Count[]
  courses: Count[]
}
export const adminApi = {
  me: () => request<Admin>('/admin/me'),
  login: (email: string, password: string) => request<Admin>('/admin/login', { email, password }),
  logout: () => request<void>('/admin/logout', {}),
  options: (signal: AbortSignal) => request<AdminOptions>('/admin/options', undefined, signal),
  list: (params: URLSearchParams, signal: AbortSignal) =>
    request<ParticipationPage>(`/admin/participations?${params}`, undefined, signal),
  summary: (params: URLSearchParams, signal: AbortSignal) =>
    request<Summary>(`/admin/summary?${params}`, undefined, signal),
  detail: (id: string, signal: AbortSignal) =>
    request<ParticipationDetail>(
      `/admin/participations/${encodeURIComponent(id)}`,
      undefined,
      signal,
    ),
}
export const statusLabel = {
  draft: 'Em andamento',
  submitted: 'Aguarda confirmação',
  completed: 'Concluída',
}
export const agreementLabel = (value: boolean | null) =>
  value === null ? 'Sem resposta' : value ? 'Concordou' : 'Discordou'
export const dateTime = (value: string | null) =>
  value
    ? new Intl.DateTimeFormat('pt-BR', {
        dateStyle: 'short',
        timeStyle: 'short',
        timeZone: 'America/Sao_Paulo',
      }).format(new Date(value))
    : '—'
