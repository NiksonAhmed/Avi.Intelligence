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

test('Work management report: overdue task and person', async ({ page }, testInfo) => {
  const title = `E2E return temperature loggers (${testInfo.project.name})`
  const due = new Date(Date.now() - 6 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10)
  const task = await page.request.post('/api/v1/tasks', {
    data: { category: 'vendor', subject_name: 'E2E Courier Ltd', title, assignee_ids: ['demo-dm-1'], due_date: due },
  })
  expect(task.status()).toBe(201)
  // Risks and issues come from SimpleTrials only: they can no longer be raised here.
  expect((await page.request.post('/api/v1/risks', { data: {} })).status()).toBe(405)

  await page.goto('/reports')
  await page.getByRole('tab', { name: 'Work management' }).click()
  await expect(page).toHaveURL(/tab=work/)
  const overdue = page.getByTestId('overdue-row').filter({ hasText: title })
  await expect(overdue).toContainText('Waiting on Demo Data Manager')
  await expect(overdue).toContainText(/[67] days late/)
  await expect(page.getByTestId('person-row').filter({ hasText: 'Demo Data Manager' })).toBeVisible()
  await expect(page.getByText('Risk heat map')).toHaveCount(0)

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

test('Risks and issues report: SimpleTrials issues, overdue first, with Excel export', async ({ page }) => {
  await page.goto('/reports?tab=risks')
  await expect(page.getByRole('tab', { name: 'Risks and issues', selected: true })).toBeVisible()
  await expect(page.getByTestId('issue-row').first()).toContainText('days overdue')
  await expect(page.getByRole('button', { name: /Sync now/ })).toBeVisible()
  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('link', { name: /Excel/ }).click()
  expect((await downloadPromise).suggestedFilename()).toMatch(/^Risks and issues \d{4}-\d{2}-\d{2}\.xlsx$/)
})

test('Quality (SOPs) report: review schedule, department filter and Excel export', async ({ page }) => {
  await page.goto('/reports')
  await page.getByRole('tab', { name: 'Quality (SOPs)' }).click()
  await expect(page).toHaveURL(/tab=quality/)
  await expect(page.getByText('Demo data: SharePoint is not connected')).toBeVisible()
  await expect(page.getByTestId('tile-approved')).toHaveText('11')
  await expect(page.getByTestId('review-month')).toHaveCount(13)
  const sop001 = page.getByTestId('schedule-row').filter({ hasText: 'SOP-001' })
  await expect(sop001).toContainText('Overdue')

  await page.getByRole('combobox', { name: 'Filter by department' }).click()
  await page.getByTitle('Pharmacovigilance', { exact: true }).click()
  await expect(page).toHaveURL(/department=Pharmacovigilance/)
  await expect(page.getByTestId('schedule-row').filter({ hasText: 'SOP-001' })).toHaveCount(0)
  await expect(page.getByTestId('schedule-row').first()).toContainText('Pharmacovigilance')

  // Open an SOP from the schedule.
  await page.getByTestId('schedule-row').first().getByRole('link').click()
  await expect(page).toHaveURL(/\/documents\/sops\//)
  await page.goBack()

  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('link', { name: /Excel/ }).click()
  const download = await downloadPromise
  expect(download.suggestedFilename()).toMatch(/^Quality SOPs \d{4}-\d{2}-\d{2}\.xlsx$/)
})

test('eTMF report: completeness, heat map, expiring documents and Excel export', async ({ page }) => {
  await page.goto('/reports')
  await page.getByRole('tab', { name: 'eTMF' }).click()
  await expect(page).toHaveURL(/tab=etmf/)
  await expect(page.getByText('Demo data: SimpleTrials is not connected')).toBeVisible()
  await expect(page.getByTestId('tile-completeness')).toContainText('%')
  await expect(page.getByRole('img', { name: /^eTMF completeness: \d+ of \d+/ })).toBeVisible()
  await expect(page.getByTestId('study-completeness-row')).toHaveCount(4)
  await expect(page.getByTestId('heat-row').first()).toBeVisible()
  await expect(page.getByTestId('expiring-row').first()).toBeVisible()

  await page.getByRole('combobox', { name: 'Filter by study' }).click()
  await page.getByTitle(/^DEMO-CV-201 ·/).click()
  await expect(page).toHaveURL(/study=/)
  await expect(page.getByTestId('study-completeness-row')).toHaveCount(1)
  await expect(page.getByTestId('study-completeness-row')).toContainText('DEMO-CV-201')

  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('link', { name: /Excel/ }).click()
  const download = await downloadPromise
  expect(download.suggestedFilename()).toMatch(/^eTMF \d{4}-\d{2}-\d{2}\.xlsx$/)
})
