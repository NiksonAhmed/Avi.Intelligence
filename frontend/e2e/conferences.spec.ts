import { expect, test } from '@playwright/test'

test('Conferences: demo notice, map pins, select a conference, filter and export', async ({ page }) => {
  await page.goto('/conferences')
  await expect(page.getByRole('heading', { name: 'Where Avion is going' })).toBeVisible()
  await expect(page.getByText(/Demo conferences: the BD team's SharePoint list is not connected yet/)).toBeVisible()
  await expect(page.getByTestId('conference-map')).toBeVisible()
  expect(await page.getByTestId('conference-pin').count()).toBeGreaterThan(3)

  await page.getByTestId('conference-pin').nth(1).click()
  await expect(page.getByTestId('conference-details')).toBeVisible()

  await page.getByRole('button', { name: 'Speaking', exact: true }).click()
  await expect(page).toHaveURL(/role=Speaking/)
  await expect(page.getByTestId('conference-row')).toHaveCount(2)

  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('link', { name: /Excel/ }).click()
  expect((await downloadPromise).suggestedFilename()).toMatch(/^Conferences \d{4} \d{4}-\d{2}-\d{2}\.xlsx$/)
})
