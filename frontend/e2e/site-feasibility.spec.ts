import { expect, test } from '@playwright/test'

test('Site feasibility: map, filters, a site panel, the link to its validation, and Excel', async ({ page }) => {
  await page.goto('/site-feasibility')
  await expect(page.getByRole('heading', { name: 'Site feasibility' })).toBeVisible()
  await expect(page.getByTestId('feasibility-headline')).toContainText('12 sites surveyed')
  await expect(page.getByTestId('site-pin')).toHaveCount(12)

  // Filter: licensed for 225Ac.
  await page.getByRole('button', { name: '225Ac', exact: true }).click()
  await expect(page).toHaveURL(/isotope=225Ac/)
  await expect(page.getByTestId('site-pin')).toHaveCount(5)

  // Excel of the filtered sites (before a site panel opens over the page header).
  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('link', { name: /Excel/ }).click()
  const download = await downloadPromise
  expect(download.suggestedFilename()).toMatch(/^Site feasibility \d{4}-\d{2}-\d{2}\.xlsx$/)

  // Open a site, look at its IP readiness, then follow the link to Site validation.
  await page.getByRole('button', { name: /^Demo Site 103, Melbourne VIC/ }).click()
  const panel = page.getByTestId('feasibility-panel')
  await expect(panel).toContainText('Diagnostics and therapeutics')
  await panel.getByRole('tab', { name: 'IP', exact: true }).click()
  await expect(panel.getByRole('table', { name: 'IP readiness by isotope' })).toBeVisible()

  await panel.getByRole('link', { name: /Open on Site validation/ }).click()
  await expect(page).toHaveURL(/\/site-validation\?site=demo-103/)
  await expect(page.getByRole('dialog', { name: 'Demo Site 103' }).getByTestId('site-panel')).toBeVisible()
})
