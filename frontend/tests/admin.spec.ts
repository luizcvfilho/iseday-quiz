import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'

const admin = {
  id: 'admin-1',
  name: 'Equipe de teste',
  email: 'admin@example.org',
  expires_at: new Date(Date.now() + 3600000).toISOString(),
}
const areas = [
  { id: 'a1', name: 'Saúde', score: 20, is_winner: true },
  { id: 'a2', name: 'Educação', score: 20, is_winner: true },
]
const courses = [
  { id: 'c1', area_id: 'a1', name: 'Enfermagem', score: 15, is_recommended: true },
  { id: 'c2', area_id: 'a2', name: 'Pedagogia', score: 12, is_recommended: true },
]
const row = {
  id: 'p1',
  full_name: 'Ana de Teste',
  school: { id: 'school-1', name: 'Escola de teste' },
  quiz_version_id: 'v1',
  version_number: 1,
  status: 'completed',
  started_at: '2026-10-30T12:00:00Z',
  submitted_at: '2026-10-30T12:05:00Z',
  completed_at: '2026-10-30T12:06:00Z',
  agrees_with_result: true,
  winning_areas: areas,
  recommended_courses: courses,
}
const summary = {
  total: 1,
  draft: 0,
  submitted: 0,
  completed: 1,
  agreed: 1,
  disagreed: 0,
  agreement_rate: 100,
  schools: [{ ...row.school, count: 1 }],
  areas: areas.map((a) => ({ ...a, count: 1 })),
  courses: courses.map((c) => ({ ...c, count: 1 })),
}

async function mockAdmin(page: Page, authenticated = false) {
  const state = {
    authenticated,
    failLogout: false,
    failReports: false,
    expired: false,
    filters: [] as URLSearchParams[],
  }
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const reply = (status: number, body: unknown) => route.fulfill({ status, json: body })
    if (request.method() === 'POST') expect(request.headers()['x-quiz-request']).toBe('1')
    if (url.pathname === '/api/admin/login') {
      if (request.postDataJSON().password !== 'correct password')
        return reply(401, { detail: 'E-mail ou senha inválidos.' })
      state.authenticated = true
      return reply(200, admin)
    }
    if (url.pathname === '/api/admin/logout') {
      if (state.failLogout) return route.abort()
      state.authenticated = false
      return route.fulfill({ status: 204 })
    }
    if (!state.authenticated || state.expired) return reply(401, { detail: 'Sessão expirada.' })
    if (url.pathname === '/api/admin/me') return reply(200, admin)
    if (url.pathname === '/api/admin/options')
      return reply(200, {
        schools: [row.school],
        versions: [{ id: 'v1', name: 'ISE Day', version_number: 1 }],
        areas: areas.map((a) => ({ ...a, quiz_version_id: 'v1' })),
        courses: courses.map((c) => ({ ...c, quiz_version_id: 'v1' })),
      })
    if (state.failReports)
      return reply(503, { detail: 'Serviço indisponível. Tente novamente.' })
    if (url.pathname === '/api/admin/participations') {
      state.filters.push(url.searchParams)
      const items = url.searchParams.get('q') === 'Ausente' ? [] : [row]
      return reply(200, {
        items,
        total: items.length,
        page: Number(url.searchParams.get('page') ?? 1),
        page_size: Number(url.searchParams.get('page_size') ?? 20),
      })
    }
    if (url.pathname === '/api/admin/summary') return reply(200, summary)
    if (url.pathname === '/api/admin/participations/missing')
      return reply(404, { detail: 'Participação não encontrada.' })
    if (url.pathname === '/api/admin/participations/p1')
      return reply(200, {
        ...row,
        email: 'ana@example.org',
        phone: '+5522999999999',
        event_name: 'ISE Day',
        privacy_notice_version: 'test-v1',
        selections: Array.from({ length: 25 }, (_, i) => ({
          id: `s${i}`,
          display_order: i + 1,
          text: `Afirmativa ${i + 1}`,
        })),
        result: {
          participation_id: 'p1',
          quiz_version_id: 'v1',
          status: 'completed',
          submitted_at: row.submitted_at,
          statement_ids: [],
          areas,
          courses,
          feedback: {
            participation_id: 'p1',
            status: 'completed',
            completed_at: row.completed_at,
            agrees_with_result: true,
            chosen_course_id: 'c1',
            destination: 'Espaço de Saúde',
            destination_instructions: 'Procure a equipe de recepção.',
            answered_at: row.completed_at,
          },
        },
      })
    return reply(404, { detail: 'Não encontrado.' })
  })
  return state
}

async function signIn(page: Page) {
  await page.getByRole('textbox', { name: 'E-mail', exact: true }).fill('admin@example.org')
  await page.getByLabel(/^Senha/).fill('correct password')
  await page.getByRole('button', { name: 'Entrar', exact: true }).click()
}

test('login protege acesso direto, mostra erro e retorna ao resultado solicitado', async ({
  page,
}) => {
  await mockAdmin(page)
  await page.goto('/admin/participations/p1')
  await expect(page).toHaveURL(/\/admin\/login/)
  await page.getByRole('textbox', { name: 'E-mail', exact: true }).fill('admin@example.org')
  await page.getByLabel(/^Senha/).fill('wrong password')
  await page.getByRole('button', { name: 'Entrar', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('E-mail ou senha inválidos.')
  await expect(page.getByLabel(/^Senha/)).toHaveValue('')
  await signIn(page)
  await expect(page.getByRole('heading', { name: 'Ana de Teste' })).toBeVisible()
  await expect(page.getByText('ana@example.org')).toBeVisible()
  await expect(
    page.getByRole('heading', { name: 'Afirmativas selecionadas (25)' }),
  ).toBeVisible()
  await expect(page.getByText('Espaço de Saúde')).toBeVisible()
  await expect(
    page.getByRole('table', { name: 'Pontuação por área' }).getByText('Vencedora'),
  ).toHaveCount(2)
  await expect(
    page.getByRole('table', { name: 'Pontuação por curso' }).getByText('Sugerido'),
  ).toHaveCount(2)
})

test('filtros ficam na URL, detalhe volta à busca e logout limpa dados', async ({ page }) => {
  const state = await mockAdmin(page, true)
  await page.goto('/admin')
  await expect(page.getByRole('heading', { name: 'Estudantes encontrados (1)' })).toBeVisible()
  await page.getByLabel('Nome do estudante').fill('Ana')
  await page.getByRole('button', { name: 'Aplicar filtros' }).click()
  await expect(page).toHaveURL(/q=Ana/)
  await page.getByRole('button', { name: 'Aplicar filtros' }).waitFor({ state: 'visible' })
  await page.getByRole('link', { name: 'Ver resultado de Ana de Teste' }).click()
  await expect(page.getByText('ana@example.org')).toBeVisible()
  await page.getByRole('link', { name: 'Voltar às participações' }).click()
  await expect(page.getByLabel('Nome do estudante')).toHaveValue('Ana')
  await expect(page.getByRole('heading', { name: 'Estudantes encontrados (1)' })).toBeVisible()
  expect(state.filters.some((params) => params.get('q') === 'Ana')).toBe(true)
  await page.getByRole('button', { name: 'Sair', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Entrar na administração' })).toBeVisible()
  await expect(page.getByText('Ana de Teste')).toHaveCount(0)
  expect(await page.evaluate(() => ({ ...localStorage, ...sessionStorage }))).toEqual({})
})

test('falhas de consulta e logout podem ser recuperadas sem manter dados na tela', async ({
  page,
}) => {
  const state = await mockAdmin(page, true)
  state.failReports = true
  await page.goto('/admin')
  await expect(page.getByRole('alert')).toContainText('Serviço indisponível')
  state.failReports = false
  await page.getByRole('button', { name: 'Tentar novamente' }).click()
  await expect(page.getByText('Ana de Teste', { exact: true })).toBeVisible()
  state.failLogout = true
  await page.getByRole('button', { name: 'Sair', exact: true }).click()
  await expect(page.getByText('Ana de Teste', { exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Tentar novamente' })).toBeVisible()
  state.failLogout = false
  await page.getByRole('button', { name: 'Tentar novamente' }).click()
  await expect(page.getByRole('heading', { name: 'Entrar na administração' })).toBeVisible()
})

test('sessão expirada remove o resultado e participação ausente tem retorno', async ({
  page,
}) => {
  const state = await mockAdmin(page, true)
  await page.goto('/admin/participations/missing')
  await expect(page.getByRole('alert')).toContainText('Participação não encontrada.')
  await page.getByRole('link', { name: 'Voltar às participações' }).click()
  await expect(page.getByText('Ana de Teste', { exact: true })).toBeVisible()
  state.expired = true
  await page.getByRole('button', { name: 'Atualizar', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Entrar na administração' })).toBeVisible()
  await expect(page.getByText('Ana de Teste', { exact: true })).toHaveCount(0)
})

test('painel e detalhe cabem no celular e busca vazia tem mensagem', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await mockAdmin(page, true)
  await page.goto('/admin')
  await expect(page.getByRole('heading', { name: 'Estudantes encontrados (1)' })).toBeVisible()
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBe(true)
  await page.getByRole('link', { name: 'Ver resultado de Ana de Teste' }).click()
  await expect(page.getByText('ana@example.org')).toBeVisible()
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBe(true)
  await page.getByRole('link', { name: 'Voltar às participações' }).click()
  await page.getByLabel('Nome do estudante').fill('Ausente')
  await page.getByRole('button', { name: 'Aplicar filtros' }).click()
  await expect(
    page.getByText('Nenhuma participação encontrada para estes filtros.'),
  ).toBeVisible()
})

test('exportação usa os filtros aplicados e baixa CSV', async ({ page }) => {
  await mockAdmin(page, true)
  let exported: URLSearchParams | undefined
  await page.route('**/api/admin/export.csv?*', async (route) => {
    exported = new URL(route.request().url()).searchParams
    await route.fulfill({
      contentType: 'text/csv; charset=utf-8',
      body: '\ufeffNome;Escola\r\nAna de Teste;Escola de teste\r\n',
    })
  })
  await page.goto('/admin?q=Ana&page=2&page_size=20')
  const button = page.getByRole('button', { name: 'Exportar resultados filtrados (CSV)' })
  await expect(button).toBeEnabled()
  const download = page.waitForEvent('download')
  await button.click()
  expect((await download).suggestedFilename()).toBe('participacoes-iseday.csv')
  expect(exported?.get('q')).toBe('Ana')
  expect(exported?.has('page')).toBe(false)
  expect(exported?.has('page_size')).toBe(false)
})
