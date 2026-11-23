import { expect, test } from '@playwright/test'

test('Site validation: demo notice, map, a site’s capabilities, filter and export', async ({ page }) => {
  await page.goto('/site-validation')
  await expect(page.getByRole('heading', { name: 'Site validation status' })).toBeVisible()
  await expect(page.getByText(/Demo sites: the site validation tracker is not connected yet/)).toBeVisible()
  await expect(page.getByTestId('site-headline')).toContainText('sites hold an in-date validation')
  await expect(page.getByTestId('site-pin')).toHaveCount(12)

  await page.getByRole('button', { name: /Demo Site 103, Melbourne VIC: Overdue/ }).click()
  const panel = page.getByTestId('site-panel')
  await expect(panel.getByRole('table', { name: 'Isotope validation' })).toBeVisible()
  await expect(panel.getByText('Phantoms and QA/QC')).toBeVisible()
  await page.keyboard.press('Escape')

  await page.getByRole('button', { name: '225Ac', exact: true }).click()
  await expect(page).toHaveURL(/isotope=225Ac/)
  // Its overdue PET/CT 90Y is filtered out; the worst left is the gamma counter 225Ac review due in 52 days.
  await expect(page.getByRole('button', { name: /Demo Site 103, Melbourne VIC: Due soon/ })).toBeVisible()

  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('link', { name: /Excel/ }).click()
  expect((await downloadPromise).suggestedFilename()).toMatch(/^Site validation \d{4}-\d{2}-\d{2}\.xlsx$/)
})
