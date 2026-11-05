import { request } from '../api'
import { ApiError } from '../api'
import type { Participant, Result, Statement } from '../api'

export type Named = { id: string; name: string }
export type Admin = Named & { email: string; expires_at: string }
export type AdminOptions = {
  schools: string[]
  versions: (Named & { version_number: number })[]
  areas: (Named & { quiz_version_id: string })[]
  courses: (Named & { quiz_version_id: string })[]
}
export type ParticipationRow = {
  id: string
  full_name: string
  school_name: string
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
  schools: { name: string; count: number }[]
  areas: Count[]
  courses: Count[]
}
export type QuizVersion = {
  id: string
  event_name: string
  version_number: number
  status: 'draft' | 'published' | 'archived'
  created_at: string
  statement_count: number
}
export type Question = {
  id: string | null
  number: number
  text: string
  courses: { course_id: string; course: string; weight: number }[]
}
export type VersionForm = {
  event_name: string
  psychology_destination: string
  psychology_instructions: string
  areas: (Named & { destination: string; destination_instructions: string })[]
  courses: (Named & {
    area_id: string
    destination: string | null
    destination_instructions: string | null
  })[]
  statements: Question[]
}
export type VersionDetail = QuizVersion &
  VersionForm & {
    revision: string
    review_notes: string[]
  }
export const versionStatus = {
  draft: 'Rascunho',
  published: 'Publicada',
  archived: 'Arquivada',
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
  createVersion: (event_name: string, source_version_id: string | null) =>
    request<VersionDetail>('/admin/versions', { event_name, source_version_id }),
  saveVersion: (id: string, data: VersionForm, expected_revision: string) =>
    request<VersionDetail>(`/admin/versions/${encodeURIComponent(id)}`, {
      expected_revision,
      event_name: data.event_name,
      psychology_destination: data.psychology_destination,
      psychology_instructions: data.psychology_instructions,
      areas: data.areas.map(({ id, destination, destination_instructions }) => ({
        id,
        destination,
        destination_instructions,
      })),
      courses: data.courses.map(({ id, destination, destination_instructions }) => ({
        id,
        destination,
        destination_instructions,
      })),
      statements: data.statements.map(({ id, text, courses }) => ({
        id,
        text,
        courses: courses.map(({ course_id, weight }) => ({ course_id, weight })),
      })),
    }),
  publishVersion: (
    id: string,
    expected_published_id: string | null,
    expected_revision: string,
  ) =>
    request<VersionDetail>(`/admin/versions/${encodeURIComponent(id)}/publish`, {
      reviewed: true,
      expected_published_id,
      expected_revision,
    }),
  archiveVersion: (id: string) =>
    request<VersionDetail>(`/admin/versions/${encodeURIComponent(id)}/archive`, {}),
  exportCsv: async (params: URLSearchParams, signal: AbortSignal) => {
    let response: Response
    try {
      response = await fetch(`/api/admin/export.csv?${params}`, {
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
