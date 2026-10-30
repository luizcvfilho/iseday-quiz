import { test, expect } from '@playwright/test'

test('produção: HTTPS, rotas diretas, cache e API sem fallback HTML', async ({ page }) => {
  const home = await page.request.get('/')
  expect(home.status()).toBe(200)
  expect(home.headers()['cache-control']).toBe('no-cache')
  const html = await home.text()
  const asset = html.match(/src="([^"]+\.js)"/)?.[1]
  expect(asset).toBeTruthy()
  const script = await page.request.get(asset!)
  expect(script.status()).toBe(200)
  expect(script.headers()['cache-control']).toContain('immutable')
  expect((await page.request.get('/assets/inexistente.js')).status()).toBe(404)

  for (const path of ['/api/docs', '/api/openapi.json', '/api/inexistente']) {
    const response = await page.request.get(path)
    expect(response.status()).toBe(404)
    expect(response.headers()['content-type']).toContain('application/json')
    expect(response.headers()['cache-control']).toBe('no-store')
  }
  expect((await page.request.get('/api/health/ready')).status()).toBe(200)

  await page.goto('/admin/login')
  await expect(page.getByRole('heading', { name: 'Entrar na administração' })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Entrar na administração' })).toBeVisible()
})
