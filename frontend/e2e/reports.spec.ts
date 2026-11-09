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

test('Work management report: overdue task, person and risk heat map', async ({ page }, testInfo) => {
  const title = `E2E return temperature loggers (${testInfo.project.name})`
  const studies = (await (await page.request.get('/api/v1/studies')).json()) as { studies: { id: string }[] }
  const due = new Date(Date.now() - 6 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10)
  const task = await page.request.post('/api/v1/tasks', {
    data: { category: 'vendor', subject_name: 'E2E Courier Ltd', title, assignee_ids: ['demo-dm-1'], due_date: due },
  })
  expect(task.status()).toBe(201)
  const risk = await page.request.post('/api/v1/risks', {
    data: { study_id: studies.studies[0]!.id, kind: 'risk', title: 'E2E courier delays', likelihood: 3, impact: 3, owner_id: 'demo-pm-1' },
  })
  expect(risk.status()).toBe(201)

  await page.goto('/reports')
  await page.getByRole('tab', { name: 'Work management' }).click()
  await expect(page).toHaveURL(/tab=work/)
  const overdue = page.getByTestId('overdue-row').filter({ hasText: title })
  await expect(overdue).toContainText('Waiting on Demo Data Manager')
  await expect(overdue).toContainText(/[67] days late/)
  await expect(page.getByTestId('person-row').filter({ hasText: 'Demo Data Manager' })).toBeVisible()
  await expect(page.getByTestId('heat-3-3')).not.toContainText(/^0/)

  // Filter to Vendor tasks: the study chart goes away.
  await page.getByRole('combobox', { name: 'Filter by task category' }).click()
  await page.getByTitle('Vendor', { exact: true }).click()
  await expect(page).toHaveURL(/category=vendor/)
  await expect(page.getByText('Open study tasks by study')).toHaveCount(0)
  await expect(page.getByTestId('category-row')).toHaveCount(1)

  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('link', { name: /Excel/ }).click()
  const download = await downloadPromise
  expect(download.suggestedFilename()).toMatch(/^Work management \d{4}-\d{2}-\d{2}\.xlsx$/)
})
