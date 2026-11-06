import { request } from '../api'
import { ApiError } from '../api'
import type { Participant, Result, Statement } from '../api'

export type Named = { id: string; name: string }
export type Admin = Named & { email: string; expires_at: string }
export type AdminOptions = {
  schools: string[]
  areas: Named[]
  courses: Named[]
}
export type ParticipationRow = {
  id: string
  full_name: string
  school_name: string
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
export type Count = Named & { count: number }
export type Summary = {
  total: number
  draft: number
  submitted: number
  completed: number
  agreed: number
  disagreed: number
  agreement_rate: number | null
  schools: { name: string; count: number }[]
  areas: Count[]
  courses: Count[]
}
export const adminApi = {
  me: () => request<Admin>('/admin/me'),
  login: (email: string, password: string) =>
    request<Admin>('/admin/login', { email, password }),
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
  exportReport: async (
    format: 'csv' | 'xlsx',
    params: URLSearchParams,
    signal: AbortSignal,
  ) => {
    let response: Response
    try {
      response = await fetch(`/api/admin/export.${format}?${params}`, {
        credentials: 'same-origin',
        cache: 'no-store',
        signal: AbortSignal.any([signal, AbortSignal.timeout(30_000)]),
      })
    } catch {
      throw new ApiError(0, 'Não foi possível exportar. Confira a conexão e tente novamente.')
    }
    if (!response.ok) {
      const data = await response.json().catch(() => ({}))
      throw new ApiError(
        response.status,
        typeof data.detail === 'string' ? data.detail : 'Não foi possível exportar.',
      )
    }
    return response.blob()
  },
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
