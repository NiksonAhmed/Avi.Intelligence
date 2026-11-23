import { expect, test } from '@playwright/test'

// The local developer is an administrator, so the Overview shows the Administrator page and can preview others.
test('Overview: what needs you, role sections with links, and previewing another role', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Needs your attention' })).toBeVisible()
  await expect(page.getByTestId('overview-attention-count')).toHaveCount(3)
  await expect(page.getByTestId('overview-section-connectors')).toBeVisible()
  await expect(page.getByTestId('overview-section-risks')).toContainText('Open issues')
  await expect(page.getByTestId('overview-source').first()).toContainText('SimpleTrials')

  // Preview the CRA page: sites (all, until an administrator assigns some) and site visits.
  await page.goto('/?view=cra')
  await expect(page.getByTestId('overview-section-my_sites')).toContainText('No sites are assigned to you yet')
  await expect(page.getByTestId('overview-section-visits')).toBeVisible()

  // A figure opens its report.
  await page.goto('/')
  await page.getByTestId('overview-section-risks').getByRole('link', { name: /Open issues/ }).click()
  await expect(page).toHaveURL(/\/reports\?tab=risks/)
})
