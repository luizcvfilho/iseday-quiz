import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'

async function management(page: Page) {
  const version = {
    id: 'v2',
    event_name: 'ISE Day',
    version_number: 2,
    status: 'draft',
    created_at: '2026-10-30T12:00:00Z',
    statement_count: 74,
    revision: 'r1',
    psychology_destination: 'SPA',
    psychology_instructions: 'Procure a equipe.',
    areas: [
      { id: 'a1', name: 'Saúde', destination: 'Bloco A', destination_instructions: 'Térreo.' },
    ],
    courses: [
      {
        id: 'c1',
        name: 'Enfermagem',
        area_id: 'a1',
        destination: null,
        destination_instructions: null,
      },
      {
        id: 'c2',
        name: 'Fisioterapia',
        area_id: 'a1',
        destination: null,
        destination_instructions: null,
      },
    ],
    review_notes: ['Confirmar locais.'],
    statements: [
      {
        id: 'st1',
        number: 1,
        text: 'Gosto de cuidar de pessoas.',
        courses: [{ course_id: 'c1', course: 'Enfermagem', weight: 1 }],
      },
    ],
  }
  const published = { ...version, id: 'v1', version_number: 1, status: 'published' }
  const state = { version, published, saved: false, failSave: false }
  await page.route('**/api/**', async (route) => {
    const req = route.request()
    const url = new URL(req.url())
    const post = req.method() === 'POST'
    const body = post ? req.postDataJSON() : undefined
    if (post) expect(req.headers()['x-quiz-request']).toBe('1')
    const reply = (data: unknown, status = 200) => route.fulfill({ status, json: data })
    if (url.pathname === '/api/admin/me')
      return reply({
        id: 'admin',
        name: 'Equipe',
        email: 'admin@example.org',
        expires_at: new Date(Date.now() + 3600000).toISOString(),
      })
    if (url.pathname === '/api/admin/versions' && post) {
      expect(body).toEqual({ event_name: 'Novo evento', source_version_id: null })
      return reply(state.version, 201)
    }
    if (url.pathname === '/api/admin/versions') return reply([state.version, state.published])
    if (url.pathname === '/api/admin/versions/v2/publish') {
      expect(state.saved).toBe(true)
      expect(body).toEqual({
        reviewed: true,
        expected_published_id: 'v1',
        expected_revision: 'r2',
      })
      state.version.status = 'published'
      state.published.status = 'archived'
      return reply(state.version)
    }
    if (url.pathname === '/api/admin/versions/v2/archive') {
      state.version.status = 'archived'
      return reply(state.version)
    }
    if (url.pathname === '/api/admin/versions/v2') {
      if (!post) return reply(state.version)
      if (state.failSave)
        return reply(
          { detail: 'Este rascunho foi alterado. Recarregue a versão antes de salvar.' },
          409,
        )
      expect(body.expected_revision).toBe('r1')
      state.version = {
        ...state.version,
        ...body,
        areas: state.version.areas.map((area) => ({
          ...area,
          ...body.areas.find((a: { id: string }) => a.id === area.id),
        })),
        courses: state.version.courses.map((course) => ({
          ...course,
          ...body.courses.find((c: { id: string }) => c.id === course.id),
        })),
        statement_count: body.statements.length,
        statements: body.statements.map(
          (
            statement: {
              id: string | null
              text: string
              courses: { course_id: string; weight: number }[]
            },
            index: number,
          ) => ({
            ...statement,
            id: statement.id ?? `new-${index}`,
            number: index + 1,
            courses: statement.courses.map((link) => ({
              ...link,
              course: state.version.courses.find((c) => c.id === link.course_id)!.name,
            })),
          }),
        ),
        revision: 'r2',
      }
      state.saved = true
      return reply(state.version)
    }
    return reply({ detail: 'Não encontrado.' }, 404)
  })
  return state
}

test('versões: criar, configurar destinos, revisar, publicar e arquivar', async ({ page }) => {
  const state = await management(page)
  await page.goto('/admin/versions')
  await page.getByRole('button', { name: 'Criar versão', exact: true }).click()
  await page.getByLabel('Nome do evento').fill('Novo evento')
  await page.getByRole('button', { name: 'Criar rascunho', exact: true }).click()
  await expect(page).toHaveURL(/\/admin\/versions\/v2$/)
  await page.getByLabel('Destino · Saúde').fill('Bloco B')
  await expect(
    page.getByRole('button', { name: 'Publicar versão', exact: true }),
  ).toBeDisabled()
  await page.getByRole('button', { name: 'Salvar rascunho' }).click()
  await expect(page.getByRole('alert')).toContainText('Rascunho salvo.')
  expect(state.version.areas[0].destination).toBe('Bloco B')
  await page.getByRole('button', { name: /Perguntas e pesos/ }).click()
  await expect(page.getByText('1. Gosto de cuidar de pessoas.')).toBeVisible()
  await page.getByRole('button', { name: 'Publicar versão', exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText('A versão 1 será arquivada.')
  await expect(page.getByRole('button', { name: 'Confirmar publicação' })).toBeDisabled()
  await page.getByRole('checkbox').check()
  await page.getByRole('button', { name: 'Confirmar publicação' }).click()
  await expect(page.getByRole('alert').filter({ hasText: 'Versão publicada.' })).toBeVisible()
  await expect(page.getByLabel('Destino · Saúde')).toBeDisabled()
  await page.getByRole('button', { name: 'Arquivar versão' }).click()
  await expect(page.getByRole('dialog')).toContainText('Novos cadastros ficarão indisponíveis')
  await page.getByRole('button', { name: 'Confirmar arquivamento' }).click()
  await expect(page.getByRole('alert').filter({ hasText: 'Versão arquivada.' })).toBeVisible()
})

test('conflito preserva o formulário e recarregar recupera o rascunho', async ({ page }) => {
  const state = await management(page)
  await page.goto('/admin/versions/v2')
  await page.getByLabel('Destino · Saúde').fill('Minha alteração')
  state.failSave = true
  await page.getByRole('button', { name: 'Salvar rascunho' }).click()
  await expect(page.getByRole('alert')).toContainText('Este rascunho foi alterado.')
  await expect(page.getByLabel('Destino · Saúde')).toHaveValue('Minha alteração')
  state.failSave = false
  await page.getByRole('button', { name: 'Recarregar versão' }).click()
  await expect(page.getByLabel('Destino · Saúde')).toHaveValue('Bloco A')
})

test('gestão cabe no celular e navegação mantém as opções acessíveis', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await management(page)
  await page.goto('/admin/versions')
  await expect(page.getByRole('link', { name: 'Escolas', exact: true })).toHaveCount(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
    true,
  )
  await page.getByRole('link', { name: 'Versões e destinos' }).click()
  await page.getByRole('link', { name: 'Abrir versão 2', exact: true }).click()
  await expect(page.getByLabel('Destino de Psicologia / SPA')).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
    true,
  )
})

test('afirmativas: editar texto e pesos, vincular cursos e adicionar nova pergunta', async ({
  page,
}) => {
  const state = await management(page)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/admin/versions/v2')
  await page.getByRole('button', { name: /Perguntas e pesos/ }).click()
  await page.getByRole('button', { name: 'Editar afirmativa 1', exact: true }).click()
  await page.getByLabel('Texto da afirmativa').fill('Gosto de aprender sobre saúde.')
  await page.getByRole('spinbutton', { name: 'Peso 1', exact: true }).fill('4')
  await page.getByRole('button', { name: 'Adicionar curso e peso' }).click()
  await expect(page.getByRole('combobox', { name: 'Curso 2' })).toContainText('Fisioterapia')
  await page.getByRole('spinbutton', { name: 'Peso 2', exact: true }).fill('0')
  await expect(page.getByRole('button', { name: 'Aplicar ao rascunho' })).toBeDisabled()
  await page.getByRole('spinbutton', { name: 'Peso 2', exact: true }).fill('7')
  await page.getByRole('button', { name: 'Aplicar ao rascunho' }).click()
  await expect(page.getByText('Enfermagem (peso 4) · Fisioterapia (peso 7)')).toBeVisible()
  expect(state.saved).toBe(false)
  await page.getByRole('button', { name: 'Adicionar afirmativa', exact: true }).click()
  await page.getByLabel('Texto da afirmativa').fill('Quero pesquisar novas formas de cuidar.')
  await expect(page.getByRole('button', { name: 'Aplicar ao rascunho' })).toBeDisabled()
  await page.getByRole('button', { name: 'Adicionar curso e peso' }).click()
  await page.getByRole('spinbutton', { name: 'Peso 1', exact: true }).fill('3')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
    true,
  )
  await page.getByRole('button', { name: 'Aplicar ao rascunho' }).click()
  await expect(page.getByText('Nova afirmativa · ainda não salva')).toBeVisible()
  await expect(
    page.getByRole('button', { name: 'Publicar versão', exact: true }),
  ).toBeDisabled()
  await page.getByRole('button', { name: 'Salvar rascunho' }).click()
  await expect(page.getByRole('alert')).toContainText('Rascunho salvo.')
  expect(state.version.statements).toHaveLength(2)
  expect(state.version.statements[0].courses.map((c) => c.weight)).toEqual([4, 7])
  expect(state.published.statements[0].text).toBe('Gosto de cuidar de pessoas.')
  await page.reload()
  await page.getByRole('button', { name: /Perguntas e pesos/ }).click()
  await expect(page.getByText('2. Quero pesquisar novas formas de cuidar.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Salvar rascunho' })).toBeDisabled()
})

test('editor rejeita duplicata e vínculo vazio, cancelar preserva o rascunho', async ({
  page,
}) => {
  await management(page)
  await page.goto('/admin/versions/v2')
  await page.getByRole('button', { name: /Perguntas e pesos/ }).click()
  await page.getByRole('button', { name: 'Adicionar afirmativa', exact: true }).click()
  await page.getByLabel('Texto da afirmativa').fill('Gosto de cuidar de pessoas.')
  await page.getByRole('button', { name: 'Adicionar curso e peso' }).click()
  await expect(page.getByText('Já existe uma afirmativa com esse texto.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Aplicar ao rascunho' })).toBeDisabled()
  await page.getByRole('button', { name: 'Cancelar', exact: true }).click()
  await page.getByRole('button', { name: 'Editar afirmativa 1', exact: true }).click()
  await page.getByRole('button', { name: 'Remover vínculo 1' }).click()
  await expect(page.getByRole('button', { name: 'Aplicar ao rascunho' })).toBeDisabled()
  await page.getByRole('button', { name: 'Cancelar', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Salvar rascunho' })).toBeDisabled()
})

test('perguntas e pesos publicados ficam disponíveis apenas para consulta', async ({
  page,
}) => {
  const state = await management(page)
  state.version.status = 'published'
  await page.goto('/admin/versions/v2')
  await page.getByRole('button', { name: /Perguntas e pesos/ }).click()
  await expect(page.getByText('1. Gosto de cuidar de pessoas.')).toBeVisible()
  await expect(
    page.getByRole('button', { name: 'Adicionar afirmativa', exact: true }),
  ).toHaveCount(0)
  await expect(
    page.getByRole('button', { name: 'Editar afirmativa 1', exact: true }),
  ).toHaveCount(0)
})
