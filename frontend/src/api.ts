export type Statement = { id: string; display_order: number; text: string }
export type Quiz = {
  event_name: string
  required_selection_count: number
  statements: Statement[]
}
export type CurrentQuiz = Quiz & { privacy_notice_version: string; privacy_notice_text: string }
export type Participant = {
  id: string
  status: 'draft' | 'submitted' | 'completed'
  access_expires_at: string
}
export type Area = {
  id: string
  name: string
  destination: string
  score: number
  is_winner: boolean
}
export type Course = {
  id: string
  area_id: string
  name: string
  score: number
  is_recommended: boolean
}
export type Feedback = { agrees_with_result: boolean; chosen_course_id: string | null }
export type Referral = Feedback & {
  participation_id: string
  status: 'completed'
  completed_at: string
  destination: string
  destination_instructions: string
  answered_at: string
}
export type Result = {
  participation_id: string
  status: 'submitted' | 'completed'
  submitted_at: string
  statement_ids: string[]
  areas: Area[]
  courses: Course[]
  feedback: Referral | null
}
export type Registration = {
  school_name: string
  full_name: string
  phone: string
  email: string
  privacy_notice_version: string
}

export class ApiError extends Error {
  status: number
  fields: string[]
  constructor(status: number, message: string, fields: string[] = []) {
    super(message)
    this.status = status
    this.fields = fields
  }
}

export async function request<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const timeout = AbortSignal.timeout(15_000)
  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      method: body === undefined ? 'GET' : 'POST',
      credentials: 'same-origin',
      cache: 'no-store',
      signal: signal ? AbortSignal.any([timeout, signal]) : timeout,
      headers:
        body === undefined ? {} : { 'Content-Type': 'application/json', 'X-Quiz-Request': '1' },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiError(0, 'Não foi possível conectar. Confira a conexão e tente novamente.')
  }
  if (response.status === 204) return undefined as T
  let data
  try {
    data = await response.json()
  } catch {
    throw new ApiError(
      response.ok ? 0 : response.status,
      'Não foi possível ler a resposta. Tente novamente.',
    )
  }
  if (!response.ok) {
    const details = data.detail
    const fields = Array.isArray(details)
      ? details.map((item: { loc?: unknown[] }) => String(item.loc?.[1] ?? ''))
      : []
    throw new ApiError(
      response.status,
      typeof details === 'string' ? details : 'Revise os campos indicados e tente novamente.',
      fields,
    )
  }
  return data as T
}

export const api = {
  current: () => request<CurrentQuiz>('/quiz/current'),
  me: () => request<Participant>('/participations/me'),
  quiz: () => request<Quiz>('/participations/me/quiz'),
  register: (data: Registration) => request<Participant>('/participations', data),
  submit: (ids: string[]) => request<Result>('/participations/me/submit', { statement_ids: ids }),
  result: () => request<Result>('/participations/me/result'),
  feedback: (data: Feedback) => request<Referral>('/participations/me/feedback', data),
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 429)
      return 'Muitas tentativas em pouco tempo. Aguarde um minuto e tente novamente.'
    return error.message
  }
  return 'Não foi possível concluir. Tente novamente.'
}

export function normalizePhone(value: string): string | null {
  if (!/^[+()\d\s.-]+$/.test(value) || (value.includes('+') && !value.trim().startsWith('+55')))
    return null
  const digits = value.replace(/\D/g, '')
  const phone = digits.length === 10 || digits.length === 11 ? `+55${digits}` : `+${digits}`
  return /^\+55[1-9]\d\d{8,9}$/.test(phone) ? phone : null
}
