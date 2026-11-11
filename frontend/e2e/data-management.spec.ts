import { expect, test } from '@playwright/test'

// Runs against the demo Viedoc study (VIEDOC_MODE=mock): never a real Viedoc study.
test('Data Management: overview, site drill-down and a query timeline', async ({ page }) => {
  await page.goto('/')
  // The menu entry exists (on tablet the menu is folded away, so open the page by its address).
  await expect(page.locator('a[href="/data-management"]')).toHaveCount(1)
  await page.goto('/data-management')
  await expect(page.getByText('Demo data: no Viedoc study is connected')).toBeVisible()
  await expect(page.getByTestId('dm-environment')).toHaveText('Demo study')
  await expect(page.getByTestId('dm-tile-open_at_site')).toHaveText('6')
  await expect(page.getByTestId('dm-tile-awaiting_approval')).toHaveText('5')

  // Open site 102's queries that are open at the site.
  const site = page.getByTestId('dm-site-row').filter({ hasText: '102 · Demo Cancer Centre' })
  await site.getByRole('button', { name: 'Open at site 102' }).click()
  await expect(page).toHaveURL(/tab=queries.*site=102.*state=open_at_site|tab=queries.*state=open_at_site.*site=102/)
  await expect(page.getByTestId('dm-query-row')).toHaveCount(3)

  // A query answered, sent back and answered again: its full history.
  await page.getByRole('combobox', { name: 'Query state' }).click()
  await page.getByTitle('Not closed (open or awaiting)').click()
  await expect(page).not.toHaveURL(/state=open_at_site/)
  await page.getByText('Sent back at least once', { exact: true }).click()
  await expect(page).toHaveURL(/reopened=true/)
  await expect(page.getByTestId('dm-query-row')).toHaveCount(1)
  await page.getByTestId('dm-query-row').click()
  const drawer = page.getByRole('dialog')
  await expect(drawer.getByText('History')).toBeVisible()
  await expect(drawer.getByText('Query Resolved', { exact: true })).toHaveCount(2)
  await expect(drawer.getByText(/answer and approve queries in Viedoc/)).toBeVisible()

  // Sync now (demo) works for administrators.
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: /Sync now/ }).click()
  await expect(page.getByText(/Synced: 14 queries/)).toBeVisible()
})
