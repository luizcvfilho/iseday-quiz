import { test, expect } from '@playwright/test'

test('catálogo original: cadastro até encaminhamento com API e PostgreSQL reais', async ({
  page,
}, testInfo) => {
  test.setTimeout(60_000)
  await page.goto('/')
  await expect(page.getByLabel('Nome completo')).toBeVisible()
  await page.evaluate(() => document.fonts.ready)
  await page.screenshot({ path: testInfo.outputPath('cadastro-desktop.png'), fullPage: true })
  await page.getByLabel('Nome completo').fill('Aluno fictício para teste')
  await page.getByRole('textbox', { name: /^Escola/ }).fill('Escola de teste')
  await page.getByLabel('Telefone com DDD').fill('(11) 99999-9999')
  await page.getByRole('textbox', { name: /^E-mail/ }).fill('teste@example.org')
  await page.getByRole('button', { name: 'Começar meu quiz' }).click()
  await expect(page.getByRole('checkbox')).toHaveCount(74)
  if (process.env.ISEDAY_PRODUCTION_TEST_URL) {
    const cookie = (await page.context().cookies()).find(
      (item) => item.name === '__Host-iseday_participant',
    )
    expect(cookie).toMatchObject({ secure: true, httpOnly: true, sameSite: 'Strict', path: '/' })
  }
  await page.screenshot({
    path: testInfo.outputPath('afirmativas-desktop.png'),
    fullPage: true,
  })
  for (let i = 0; i < 25; i++) await page.getByRole('checkbox').nth(i).check()
  await page.getByRole('button', { name: 'Revisar escolhas' }).click()
  await page.getByRole('button', { name: 'Confirmar 25 escolhas' }).click()
  await expect(page.getByRole('heading', { name: 'Saúde', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Espaços de vivência' })).toBeVisible()
  await expect(page.getByText('CEMA, SPA, Anatômico e complexo esportivo')).toBeVisible()
  await expect(page.getByText('Ver pontuação por área')).toHaveCount(0)
  await expect(page.getByText('Enfermagem e Fisioterapia', { exact: true })).toBeVisible()
  await expect(page.getByText('Enfermagem', { exact: true })).toHaveCount(0)
  await expect(page.getByText('Fisioterapia', { exact: true })).toHaveCount(0)
  await page.screenshot({ path: testInfo.outputPath('resultado-desktop.png'), fullPage: true })
  await page.getByRole('radio', { name: 'Sim, faz sentido' }).check()
  await page
    .getByLabel('Qual curso você quer conhecer?')
    .selectOption({ label: 'Enfermagem e Fisioterapia · Saúde' })
  await page.getByRole('button', { name: 'Ver meu encaminhamento' }).click()
  await expect(page.getByRole('heading', { name: 'Vamos conhecer de perto?' })).toBeVisible()
  await page.screenshot({
    path: testInfo.outputPath('encaminhamento-desktop.png'),
    fullPage: true,
  })
  await page.reload()
  await page.getByRole('button', { name: 'Continuar minha participação' }).click()
  await expect(page.getByRole('heading', { name: 'Vamos conhecer de perto?' })).toBeVisible()
  expect((await page.request.get('/api/participations/me')).status()).toBe(200)
  expect((await page.request.get('/api/admin/participations')).status()).toBe(401)
  await page.goto('/admin')
  await expect(page.getByRole('heading', { name: 'Entrar na administração' })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('admin-login.png'), fullPage: true })
  await page.getByRole('textbox', { name: 'E-mail', exact: true }).fill('admin@example.org')
  await page.getByLabel(/^Senha/).fill('admin test password only')
  await page.getByRole('button', { name: 'Entrar', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Estudantes encontrados (1)' })).toBeVisible()
  if (process.env.ISEDAY_PRODUCTION_TEST_URL) {
    const cookie = (await page.context().cookies()).find(
      (item) => item.name === '__Host-iseday_admin',
    )
    expect(cookie).toMatchObject({ secure: true, httpOnly: true, sameSite: 'Strict', path: '/' })
  }
  await page.getByLabel('Nome do estudante').fill('Aluno fictício')
  await page.getByRole('combobox', { name: 'Escola', exact: true }).click()
  await page.getByRole('option', { name: 'Escola de teste', exact: true }).click()
  await page.getByRole('button', { name: 'Aplicar filtros' }).click()
  await expect(page).toHaveURL(/school_name=Escola\+de\+teste/)
  await expect(
    page.getByRole('link', { name: 'Ver resultado de Aluno fictício para teste' }),
  ).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('admin-painel.png'), fullPage: true })
  await page.getByRole('link', { name: 'Ver resultado de Aluno fictício para teste' }).click()
  await expect(page.getByText('teste@example.org')).toBeVisible()
  await expect(page.getByText('Escola de teste', { exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Escolas', exact: true })).toHaveCount(0)
  await expect(
    page.getByRole('heading', { name: 'Afirmativas selecionadas (25)' }),
  ).toBeVisible()
  await expect(
    page.getByRole('table', { name: 'Pontuação por curso' }).getByText('Sugerido'),
  ).toHaveCount(1)
  await expect(page.getByText('Curso escolhido: Enfermagem e Fisioterapia')).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('admin-detalhe.png'), fullPage: true })
  await expect(page.getByRole('link', { name: 'Versões e destinos' })).toHaveCount(0)
  expect((await page.request.get('/api/admin/versions')).status()).toBe(404)
  const current = await (await page.request.get('/api/quiz/current')).json()
  expect(current).not.toHaveProperty('version_number')
  expect(current.statements).toHaveLength(74)
  await page.getByRole('link', { name: 'Participações', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Estudantes encontrados (1)' })).toBeVisible()
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Exportar resultados filtrados (CSV)' }).click()
  await (await download).saveAs(testInfo.outputPath('participacoes.csv'))
  await page.getByRole('link', { name: 'Ver resultado de Aluno fictício para teste' }).click()
  await expect(page.getByText('Curso escolhido: Enfermagem e Fisioterapia')).toBeVisible()
  await page.getByRole('button', { name: 'Sair', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Entrar na administração' })).toBeVisible()
  expect((await page.request.get('/api/admin/me')).status()).toBe(401)
})
