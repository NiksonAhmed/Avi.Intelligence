import { expect, test } from '@playwright/test'

test('Study delivery report: figures, filter by study and Excel export', async ({ page }) => {
  await page.goto('/reports')
  await expect(page.getByRole('heading', { name: 'Reports and Insights' })).toBeVisible()
  await expect(page.getByText('Demo data: SimpleTrials is not connected')).toBeVisible()
  await expect(page.getByTestId('tile-on_plan')).toContainText('of 4')
  await expect(page.getByTestId('timeline-row').first()).toBeVisible()
  await expect(page.getByTestId('activation-figure')).toContainText('5 of 7')

  // Filter to one study: only its milestones remain.
  await page.getByRole('combobox', { name: 'Filter by study' }).click()
  await page.getByTitle(/^DEMO-ONC-301 ·/).click()
  await expect(page).toHaveURL(/study=/)
  await expect(page.getByTestId('timeline-row').first()).toContainText('DEMO-ONC-301')
  await expect(page.getByTestId('timeline-row').filter({ hasText: 'DEMO-CV-201' })).toHaveCount(0)

  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('link', { name: /Excel/ }).click()
  const download = await downloadPromise
  expect(download.suggestedFilename()).toMatch(/^Study delivery \d{4}-\d{2}-\d{2}\.xlsx$/)
})
