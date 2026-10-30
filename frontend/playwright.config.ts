import { defineConfig, devices } from '@playwright/test'
import path from 'node:path'

const live = process.env.ISEDAY_UI_LIVE === '1'
const built = process.env.ISEDAY_UI_BUILD === '1'
// Usado exclusivamente pelo ensaio descartável de scripts/check-production.sh.
const productionUrl = process.env.ISEDAY_PRODUCTION_TEST_URL
if (productionUrl && !/^https:\/\/localhost:\d+$/.test(productionUrl)) {
  throw new Error('O ensaio de produção exige https://localhost:PORTA')
}
export default defineConfig({
  testDir: './tests',
  testMatch: productionUrl
    ? ['**/live.spec.ts', '**/production.spec.ts']
    : live
      ? ['**/live.spec.ts']
      : undefined,
  testIgnore: productionUrl || live ? [] : ['**/live.spec.ts', '**/production.spec.ts'],
  fullyParallel: true,
  timeout: 30_000,
  use: {
    baseURL: productionUrl ?? 'http://127.0.0.1:5179',
    ignoreHTTPSErrors: Boolean(productionUrl),
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: productionUrl
    ? []
    : [
        ...(live
          ? [
              {
                command: 'uv run --project ../backend --frozen python tests/live_server.py',
                url: 'http://127.0.0.1:8009/api/health/ready',
                timeout: 60_000,
                env: { PYTHONPATH: path.resolve(import.meta.dirname, '../backend') },
              },
            ]
          : []),
        {
          command: built
            ? 'npm run preview -- --host 127.0.0.1 --port 5179'
            : 'npm run dev -- --host 127.0.0.1 --port 5179',
          url: 'http://127.0.0.1:5179',
          env: { API_PROXY_TARGET: 'http://127.0.0.1:8009' },
        },
      ],
})
