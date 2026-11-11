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

// Study questions are answered from the (demo) SimpleTrials copy by fixed rules: no AI key needed.
test('ask about studies and follow a link to the Study Command Centre', async ({ page }) => {
  await page.goto('/documents/ask')
  await page.getByRole('button', { name: 'Is anything due for study close-out?' }).click()
  await expect(page.getByTestId('study-understood')).toContainText('What is due · close-out')
  await expect(page.getByTestId('study-headline')).toBeVisible()
  await expect(page.getByText('No AI · worked out by fixed rules')).toBeVisible()

  await page.getByRole('textbox', { name: 'Your question' }).fill('When is database lock?')
  await page.getByRole('button', { name: /Ask$/ }).click()
  await expect(page.getByTestId('study-understood')).toContainText('Milestone dates')
  const row = page.getByTestId('study-answer-row').first()
  await expect(row).toContainText('Database lock')
  await row.getByRole('link').first().click()
  await expect(page).toHaveURL(/\/command-centre\/.+tab=milestones/)
})
