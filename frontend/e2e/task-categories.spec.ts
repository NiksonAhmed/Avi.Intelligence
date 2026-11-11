import { expect, test } from '@playwright/test'

test('raise a Procedures and SOPs review task from the SOP page', async ({ page }) => {
  const title = `E2E SOP review ${Date.now()}`
  await page.goto('/documents/sops/demo-sop-012')
  await expect(page.getByText('Tasks for this SOP', { exact: true })).toBeVisible()

  await page.getByRole('button', { name: 'New task' }).click()
  const dialog = page.getByRole('dialog', { name: 'New task' })
  // Opened from the SOP, so the category and the SOP are filled in.
  await expect(dialog.getByText('Procedures and SOPs')).toBeVisible()
  await expect(dialog.getByText(/SOP-012 v5\.0/)).toBeVisible()

  await dialog.getByLabel('Task').fill(title)
  await dialog.getByLabel('What to review (optional)').fill('Check section 6 against ICH E6(R3).')
  await dialog.getByRole('combobox', { name: 'Assign to' }).click()
  // Several people: each will update their own part.
  await page.getByTitle('Demo CRA One (Clinical Research Associate)').click()
  await page.getByTitle('Local Developer (Developer (you))').click()
  await dialog.getByText('New task', { exact: true }).click() // close the people list
  await dialog.getByRole('button', { name: 'Create task' }).click()
  await expect(page.getByText('Task created and assigned')).toBeVisible()
  await expect(page.getByText(title)).toBeVisible()

  // It appears under All tasks with what it is about, and the category filter finds it.
  await page.goto('/tasks?scope=all&category=sop')
  const row = page.getByRole('row', { name: new RegExp(title) })
  await expect(row.getByRole('link', { name: 'SOP-012 v5.0' })).toBeVisible()
  await expect(row.getByText('Procedures and SOPs')).toBeVisible()

  // I'm one of the people: marking my part done leaves the task in progress (1 of 2).
  await row.getByRole('combobox', { name: /Status of TSK-/ }).click()
  await page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden)').getByTitle('Completed').click()
  await expect(row.getByText('Your part · 1 of 2 completed')).toBeVisible()
  await expect(page.getByText(/Your part of TSK-\d+ marked Completed/)).toBeVisible()
})
