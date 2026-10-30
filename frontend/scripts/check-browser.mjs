import { chromium } from '@playwright/test'

try {
  const browser = await chromium.launch()
  await browser.close()
} catch (error) {
  const detail = error instanceof Error ? error.message : String(error)
  console.error('Não foi possível iniciar o Chromium do Playwright.')
  if (detail.includes("Executable doesn't exist")) {
    console.error('Instale a versão exigida pelo projeto: make setup-browser')
  } else {
    const missingLibrary = detail.match(/error while loading shared libraries: ([^:]+)/)?.[1]
    console.error(missingLibrary ? `Biblioteca de sistema ausente: ${missingLibrary}` : detail)
    console.error('Se faltarem bibliotecas do sistema, execute: make setup-browser-deps')
  }
  console.error('Confira também PLAYWRIGHT_BROWSERS_PATH, se estiver configurado.')
  process.exitCode = 1
}
