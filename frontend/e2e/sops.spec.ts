import { expect, test } from '@playwright/test'

test('find an SOP, open it, download it and see the download in the audit trail', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible()

  // Navigate via global search (works on desktop and tablet layouts).
  await page.getByRole('searchbox', { name: 'Global search' }).fill('site activation')
  await page.keyboard.press('Enter')

  await expect(page).toHaveURL(/\/documents\/sops\?q=site/)
  await expect(page.getByText('Demo data: SharePoint is not connected')).toBeVisible()
  await page.getByRole('link', { name: 'Site Activation', exact: true }).click()

  await expect(page.getByRole('heading', { name: /SOP-011 · Site Activation/ })).toBeVisible()
  await expect(page.getByText('Key information')).toBeVisible()

  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('link', { name: /Download demo file/ }).click()
  const download = await downloadPromise
  expect(download.suggestedFilename()).toContain('SOP-011 Site Activation')

  await page.goto('/audit')
  await expect(page.getByRole('cell', { name: /Downloaded SOP-011 Site Activation/ }).first()).toBeVisible()
})

test('filters SOPs by status', async ({ page }) => {
  await page.goto('/documents/sops')
  await page.getByRole('combobox', { name: 'Filter by status' }).click()
  await page.getByTitle('Draft').click()
  await expect(page).toHaveURL(/status=Draft/)
  await expect(page.getByRole('link', { name: 'Data Query Management' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Site Activation', exact: true })).toHaveCount(0)
})

test('administration shows the SharePoint connector in demo mode', async ({ page }) => {
  await page.goto('/admin')
  await expect(page).toHaveURL(/\/admin\/connectors/)
  await expect(page.getByText('SharePoint: SOP library')).toBeVisible()
  await expect(page.getByText('Demo mode')).toBeVisible()
})
