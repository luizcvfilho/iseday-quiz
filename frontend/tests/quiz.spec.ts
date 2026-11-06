import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'

const statements = Array.from({ length: 30 }, (_, i) => ({
  id: `s${i + 1}`,
  text: `Afirmativa de teste ${i + 1}`,
  display_order: i + 1,
}))
const quiz = {
  event_name: 'ISE Day',
  required_selection_count: 25,
  statements,
  privacy_notice_version: 'test-v1',
  privacy_notice_text: 'Aviso de teste: use apenas dados fictícios.',
}

async function mockApi(page: Page) {
  const state = {
    session: null as null | {
      id: string
      status: string
      access_expires_at: string
    },
    saved: null as null | Record<string, unknown>,
    registrations: 0,
    submissions: 0,
    feedbacks: 0,
    ends: 0,
    loseSubmit: false,
    loseFeedback: false,
    failRead: false,
    failCurrent: false,
  }
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    const method = request.method()
    const reply = (status: number, body: unknown) => route.fulfill({ status, json: body })
    if (method === 'POST') expect(request.headers()['x-quiz-request']).toBe('1')
    if (path === '/api/quiz/current')
      return state.failCurrent ? reply(503, { detail: 'Quiz indisponível.' }) : reply(200, quiz)
    if (path === '/api/participations/me')
      return state.session ? reply(200, state.session) : reply(401, { detail: 'Sessão ausente.' })
    if (path === '/api/participations/me/quiz') return reply(200, quiz)
    if (path === '/api/participations') {
      state.registrations++
      expect(request.postDataJSON().phone).toBe('+5511999999999')
      expect(request.postDataJSON().school_name).toBe('Escola de teste')
      expect(request.postDataJSON()).not.toHaveProperty('school_id')
      state.session = {
        id: 'participant-1',
        status: 'draft',
        access_expires_at: new Date(Date.now() + 3600_000).toISOString(),
      }
      return reply(201, state.session)
    }
    if (path === '/api/participations/me/submit') {
      state.submissions++
      const ids = request.postDataJSON().statement_ids
      expect(ids).toHaveLength(25)
      expect(new Set(ids).size).toBe(25)
      state.session!.status = 'submitted'
      state.saved = {
        participation_id: 'participant-1',
        status: 'submitted',
        submitted_at: new Date().toISOString(),
        statement_ids: ids,
        areas: [
          {
            id: 'a1',
            name: 'Saúde',
            destination: 'CEMA, SPA, Anatômico e complexo esportivo',
            score: 17,
            is_winner: true,
          },
          {
            id: 'a2',
            name: 'Engenharia',
            destination: 'Laboratório de práticas tecnológicas e engenharia',
            score: 17,
            is_winner: true,
          },
        ],
        courses: [
          { id: 'c1', area_id: 'a1', name: 'Enfermagem', score: 12, is_recommended: true },
          { id: 'c2', area_id: 'a1', name: 'Fisioterapia', score: 12, is_recommended: true },
          { id: 'c3', area_id: 'a2', name: 'Engenharia Civil', score: 10, is_recommended: true },
        ],
        feedback: null,
      }
      if (state.loseSubmit) {
        state.loseSubmit = false
        return route.abort('failed')
      }
      return reply(200, state.saved)
    }
    if (path === '/api/participations/me/result') {
      if (state.failRead) {
        state.failRead = false
        return route.abort('failed')
      }
      return state.saved ? reply(200, state.saved) : reply(409, { detail: 'Ainda não submetida.' })
    }
    if (path === '/api/participations/me/feedback') {
      state.feedbacks++
      const body = request.postDataJSON()
      state.session!.status = 'completed'
      const feedback = {
        ...body,
        participation_id: 'participant-1',
        status: 'completed',
        completed_at: new Date().toISOString(),
        answered_at: new Date().toISOString(),
        destination: body.agrees_with_result ? 'Espaço de Saúde' : 'SPA',
        destination_instructions: body.agrees_with_result
          ? 'Procure a equipe no espaço indicado.'
          : 'Procure a equipe de Psicologia no SPA.',
      }
      state.saved = { ...state.saved!, status: 'completed', feedback }
      if (state.loseFeedback) {
        state.loseFeedback = false
        return route.abort('failed')
      }
      return reply(200, feedback)
    }
    if (path === '/api/participations/me/end') {
      state.ends++
      state.session = null
      return route.fulfill({ status: 204 })
    }
    throw new Error(`Unexpected request: ${path}`)
  })
  return state
}

async function register(page: Page) {
  await page.goto('/')
  await page.getByLabel('Nome completo').fill('Aluno de teste')
  await page.getByRole('textbox', { name: /^Escola/ }).fill('Escola de teste')
  await page.getByLabel('Telefone com DDD').fill('(11) 99999-9999')
  await page.getByRole('textbox', { name: /^E-mail/ }).fill('aluno@example.org')
  await page.getByRole('button', { name: 'Começar meu quiz' }).click()
  await expect(page.getByRole('heading', { name: 'O que combina com você?' })).toBeVisible()
}

async function selectAndSubmit(page: Page) {
  for (let i = 0; i < 25; i++) await page.getByRole('checkbox').nth(i).check()
  await page.getByRole('button', { name: 'Revisar escolhas' }).click()
  await expect(
    page.getByRole('list', { name: 'Suas 25 escolhas' }).getByRole('listitem'),
  ).toHaveCount(25)
  await page.getByRole('button', { name: 'Confirmar 25 escolhas' }).click()
  await expect(
    page.getByRole('heading', { name: 'Novas possibilidades para explorar.' }),
  ).toBeVisible()
}

test('cadastro, limite, edição, empates e confirmação preservam o encaminhamento', async ({ page }) => {
  const state = await mockApi(page)
  await register(page)
  await expect(page.getByRole('button', { name: 'Revisar escolhas' })).toBeDisabled()
  await page.getByRole('checkbox').first().focus()
  await page.keyboard.press('Space')
  for (let i = 1; i < 25; i++) await page.getByRole('checkbox').nth(i).check()
  await expect(page.getByRole('checkbox').nth(25)).toBeDisabled()
  await page.getByRole('checkbox').first().uncheck()
  await expect(page.getByRole('checkbox').nth(25)).toBeEnabled()
  await page.getByRole('checkbox').nth(25).check()
  await page.getByRole('button', { name: 'Revisar escolhas' }).click()
  await page.getByRole('button', { name: 'Voltar e editar' }).click()
  await expect(page.getByRole('checkbox', { checked: true })).toHaveCount(25)
  await page.getByRole('button', { name: 'Revisar escolhas' }).click()
  await page.getByRole('button', { name: 'Confirmar 25 escolhas' }).click()
  await expect(page.getByRole('heading', { name: 'Saúde', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Engenharia', exact: true })).toBeVisible()
  const healthCard = page.getByRole('article').filter({
    has: page.getByRole('heading', { name: 'Saúde', exact: true }),
  })
  const engineeringCard = page.getByRole('article').filter({
    has: page.getByRole('heading', { name: 'Engenharia', exact: true }),
  })
  await expect(healthCard.getByText('CEMA, SPA, Anatômico e complexo esportivo')).toBeVisible()
  await expect(
    engineeringCard.getByText('Laboratório de práticas tecnológicas e engenharia'),
  ).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Espaços de vivência' })).toHaveCount(2)
  await expect(page.getByText('Ver pontuação por área')).toHaveCount(0)
  await expect(page.getByText(/\d+ pontos?/)).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Ver meu encaminhamento' })).toBeDisabled()
  await page.getByRole('radio', { name: 'Sim, faz sentido' }).check()
  await expect(page.getByRole('button', { name: 'Ver meu encaminhamento' })).toBeDisabled()
  await expect(page.getByLabel('Qual curso você quer conhecer?').getByRole('option')).toHaveCount(4)
  await page.getByLabel('Qual curso você quer conhecer?').selectOption('c2')
  await page.getByRole('button', { name: 'Ver meu encaminhamento' }).click()
  await expect(page.getByRole('heading', { name: 'Espaço de Saúde' })).toBeVisible()
  await expect(
    page.getByRole('button', { name: /Encerrar|Começar outra participação/ }),
  ).toHaveCount(0)
  expect(state.ends).toBe(0)
  expect(state.registrations).toBe(1)
  expect(
    await page.evaluate(() => ({ local: localStorage.length, session: sessionStorage.length })),
  ).toEqual({ local: 0, session: 0 })
})

test('perda da resposta de submissão e feedback recupera histórico', async ({ page }) => {
  const state = await mockApi(page)
  state.loseSubmit = true
  state.loseFeedback = true
  await register(page)
  await selectAndSubmit(page)
  await page.getByRole('radio', { name: 'Não me identifiquei' }).check()
  await page.getByRole('button', { name: 'Ver meu encaminhamento' }).click()
  await expect(page.getByRole('heading', { name: 'SPA', exact: true })).toBeVisible()
  expect(state.submissions).toBe(1)
  expect(state.feedbacks).toBe(1)
})

test('falha dupla mantém escolhas e repete o mesmo conjunto', async ({ page }) => {
  const state = await mockApi(page)
  state.loseSubmit = true
  state.failRead = true
  await register(page)
  for (let i = 0; i < 25; i++) await page.getByRole('checkbox').nth(i).check()
  await page.getByRole('button', { name: 'Revisar escolhas' }).click()
  await page.getByRole('button', { name: 'Confirmar 25 escolhas' }).click()
  await expect(page.getByRole('alert')).toContainText('Suas escolhas estão preservadas')
  await expect(page.getByRole('button', { name: 'Voltar e editar' })).toBeDisabled()
  await page.getByRole('button', { name: 'Confirmar 25 escolhas' }).click()
  await expect(
    page.getByRole('heading', { name: 'Novas possibilidades para explorar.' }),
  ).toBeVisible()
  expect(state.submissions).toBe(2)
})

test('participação retoma o quiz e resultado concluído retoma o encaminhamento', async ({
  page,
}) => {
  await mockApi(page)
  await register(page)
  page.on('dialog', (dialog) => dialog.accept())
  await page.getByRole('checkbox').first().check()
  await page.reload()
  await expect(
    page.getByRole('heading', { name: 'Continue sua participação.' }),
  ).toBeVisible()
  await expect(page.getByRole('button', { name: 'Começar outra participação' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Continuar minha participação' }).click()
  await expect(page.getByRole('checkbox', { checked: true })).toHaveCount(0)
  await selectAndSubmit(page)
  await page.getByRole('radio', { name: 'Não me identifiquei' }).check()
  await page.getByRole('button', { name: 'Ver meu encaminhamento' }).click()
  await expect(page.getByRole('heading', { name: 'SPA', exact: true })).toBeVisible()
  await page.reload()
  await page.getByRole('button', { name: 'Continuar minha participação' }).click()
  await expect(page.getByRole('heading', { name: 'SPA', exact: true })).toBeVisible()
})

test('cadastro permanece preenchido após mais de cinco minutos sem interação', async ({ page }) => {
  await page.clock.install()
  const state = await mockApi(page)
  await page.goto('/')
  await page.getByLabel('Nome completo').fill('Contato temporário')
  await page.clock.fastForward(241_000)
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await page.clock.fastForward(120_000)
  await expect(page.getByLabel('Nome completo')).toHaveValue('Contato temporário')
  expect(state.ends).toBe(0)
})

test('escolhas, resultado e encaminhamento permanecem após pausas sem interação', async ({ page }) => {
  await page.clock.install()
  const state = await mockApi(page)
  await register(page)
  await page.getByRole('checkbox').first().check()
  await page.clock.fastForward(361_000)
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(page.getByRole('checkbox', { checked: true })).toHaveCount(1)
  for (let i = 1; i < 25; i++) await page.getByRole('checkbox').nth(i).check()
  await page.getByRole('button', { name: 'Revisar escolhas' }).click()
  await page.clock.fastForward(361_000)
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(
    page.getByRole('list', { name: 'Suas 25 escolhas' }).getByRole('listitem'),
  ).toHaveCount(25)
  await page.getByRole('button', { name: 'Confirmar 25 escolhas' }).click()
  await page.clock.fastForward(361_000)
  await expect(page.getByRole('heading', { name: 'Saúde', exact: true })).toBeVisible()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await page.getByRole('radio', { name: 'Não me identifiquei' }).check()
  await page.getByRole('button', { name: 'Ver meu encaminhamento' }).click()
  await page.clock.fastForward(361_000)
  await expect(page.getByRole('heading', { name: 'SPA', exact: true })).toBeVisible()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  expect(state.ends).toBe(0)
})

test('sessão expirada remove o conteúdo da participação', async ({ page }) => {
  await page.clock.install()
  const state = await mockApi(page)
  await register(page)
  state.session!.access_expires_at = new Date(Date.now() + 2000).toISOString()
  // Reload obtains the updated expiry through the actual recovery path.
  await page.reload()
  await page.getByRole('button', { name: 'Continuar minha participação' }).click()
  await page.clock.fastForward(5000)
  await expect(page.getByRole('heading', { name: 'Vamos começar de novo?' })).toBeVisible()
  await expect(page.getByRole('checkbox')).toHaveCount(0)
  state.session = null
  await page.getByRole('button', { name: 'Voltar ao início' }).click()
  await expect(page.getByLabel('Nome completo')).toHaveValue('')
  expect(state.ends).toBe(0)
})

test('telefone inválido e escola ausente têm mensagens acionáveis', async ({ page }) => {
  const state = await mockApi(page)
  await page.goto('/')
  await page.getByLabel('Nome completo').fill('Aluno de teste')
  await page.getByRole('textbox', { name: /^Escola/ }).fill('Escola de teste')
  await page.getByLabel('Telefone com DDD').fill('123')
  await page.getByRole('textbox', { name: /^E-mail/ }).fill('aluno@example.org')
  await page.getByRole('button', { name: 'Começar meu quiz' }).click()
  await expect(
    page.getByText('Informe um telefone brasileiro com DDD e 10 ou 11 dígitos.'),
  ).toBeVisible()
  expect(state.registrations).toBe(0)
  await page.getByRole('textbox', { name: /^Escola/ }).fill('   ')
  await expect(page.getByRole('button', { name: 'Começar meu quiz' })).toBeDisabled()
  await page.getByRole('textbox', { name: /^Escola/ }).fill('Escola de teste')
  await page.getByLabel('Telefone com DDD').fill('(11) 99999-9999')
  await page.getByRole('button', { name: 'Começar meu quiz' }).click()
  await expect(page.getByRole('heading', { name: 'O que combina com você?' })).toBeVisible()
  expect(state.registrations).toBe(1)
})

test('erro de disponibilidade pode ser recuperado', async ({ page }) => {
  const state = await mockApi(page)
  state.failCurrent = true
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Não foi possível abrir o quiz.' })).toBeVisible()
  state.failCurrent = false
  await page.getByRole('button', { name: 'Tentar novamente', exact: true }).click()
  await expect(page.getByLabel('Nome completo')).toBeVisible()
})

test('página desconhecida mantém a identidade e oferece retorno ao cadastro', async ({ page }) => {
  await mockApi(page)
  await page.goto('/pagina-inexistente')
  await expect(page.getByRole('heading', { name: 'Página não encontrada' })).toBeVisible()
  const crest = page.getByRole('img', { name: 'Brasão do ISECENSA' })
  await expect(crest).toBeVisible()
  await expect
    .poll(() => crest.evaluate((image) => (image as HTMLImageElement).naturalWidth))
    .toBeGreaterThan(0)
  await page.getByRole('link', { name: 'Voltar ao início' }).click()
  await expect(page.getByRole('textbox', { name: /^Escola/ })).toBeVisible()
})

test('layout móvel permite chegar ao encaminhamento sem rolagem horizontal', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await mockApi(page)
  await register(page)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await selectAndSubmit(page)
  await expect(page.getByText('CEMA, SPA, Anatômico e complexo esportivo')).toBeVisible()
  await expect(page.getByText('Laboratório de práticas tecnológicas e engenharia')).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.getByRole('radio', { name: 'Não me identifiquei' }).check()
  await page.getByRole('button', { name: 'Ver meu encaminhamento' }).click()
  await expect(page.getByRole('heading', { name: 'SPA', exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})
