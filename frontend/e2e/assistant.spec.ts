import { expect, test } from '@playwright/test'

// Runs against the demo SOPs without an Anthropic key, so the assistant returns SOP passages.
test('ask a question and get relevant SOP passages linked to the SOP', async ({ page }) => {
  await page.goto('/documents/sops')
  await page.getByRole('tab', { name: 'Ask Avi.Intelligence' }).click()
  await expect(page).toHaveURL(/\/documents\/ask/)

  await page.getByRole('textbox', { name: 'Your question' }).fill('How quickly must an SAE be reported?')
  await page.getByRole('button', { name: /Ask$/ }).click()

  const passage = page.getByText(/reports an SAE to Avion Safety within 24 hours/)
  await expect(passage).toBeVisible()
  await page.getByRole('link', { name: /SOP-030 Safety Reporting/ }).first().click()
  await expect(page.getByRole('heading', { name: /SOP-030 · Safety Reporting/ })).toBeVisible()
})

test('the header button opens the assistant from any page', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Ask Avi.Intelligence' }).click()
  await expect(page).toHaveURL(/\/documents\/ask/)
  await expect(page.getByRole('textbox', { name: 'Your question' })).toBeVisible()
})
