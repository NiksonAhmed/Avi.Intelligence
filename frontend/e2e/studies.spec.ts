import { expect, test } from '@playwright/test'

test('portfolio to command centre: create a task, complete it, see it in the audit trail', async ({ page }) => {
  const title = `E2E task ${Date.now()}`

  await page.goto('/portfolio')
  await expect(page.getByRole('heading', { name: 'Study Portfolio' })).toBeVisible()
  await expect(page.getByText('Demo data: SimpleTrials is not connected')).toBeVisible()
  await page.getByRole('link', { name: 'DEMO-ONC-301' }).click()

  await expect(page.getByRole('heading', { name: /DEMO-ONC-301 ·/ })).toBeVisible()
  await expect(page.getByText('Key information')).toBeVisible()
  await page.getByRole('tab', { name: /Tasks/ }).click()

  // The development user is an administrator, so they can create and assign tasks.
  await page.getByRole('button', { name: 'New task' }).click()
  const dialog = page.getByRole('dialog', { name: 'New task' })
  await dialog.getByLabel('Task').fill(title)
  await dialog.getByLabel('Assign to').click()
  await page.getByTitle('Local Developer (Developer (you))').click()
  await dialog.getByRole('button', { name: 'Create task' }).click()
  await expect(page.getByText('Task created and assigned')).toBeVisible()

  // It appears in My Tasks, where the assignee can change its status.
  await page.goto('/tasks')
  const row = page.getByRole('row', { name: new RegExp(title) })
  await expect(row).toBeVisible()
  await row.getByRole('combobox', { name: /Status of TSK-/ }).click()
  await page.getByTitle('Completed').click()
  await expect(page.getByText(/marked Completed/)).toBeVisible()
  await expect(page.getByRole('row', { name: new RegExp(title) })).toHaveCount(0)

  await page.goto('/audit')
  await expect(page.getByRole('cell', { name: new RegExp(`Created TSK-\\d+ "${title}"`) }).first()).toBeVisible()
  await expect(page.getByRole('cell', { name: /status changed from Not started to Completed/ }).first()).toBeVisible()
})

test('risks and issues register shows the scoring rule', async ({ page }) => {
  await page.goto('/risks')
  await expect(page.getByRole('heading', { name: 'Risks and Issues' })).toBeVisible()
  await expect(page.getByText(/likelihood × impact as entered by the risk owner/)).toBeVisible()
})

test('administration shows the SimpleTrials connector in demo mode', async ({ page }) => {
  await page.goto('/admin/connectors')
  await expect(page.getByText('SimpleTrials: studies, sites and milestones')).toBeVisible()
})
