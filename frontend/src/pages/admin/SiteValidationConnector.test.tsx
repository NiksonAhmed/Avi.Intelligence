import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { SiteValidationConnector } from '../../api/types'
import { adminUser, mockApi, renderRoute } from '../../test/utils'

const DEMO: SiteValidationConnector = {
  mode: 'demo',
  reason: 'The site validation lists are not connected to SharePoint yet (SITE_VALIDATION_SITES_LIST).',
  site_url: null,
  sites_list: null,
  validations_list: null,
  scans_list: null,
  ok: null,
  error: null,
  fetched_at: null,
  counts: {},
  skipped: {},
}

describe('Administration: site validation connector', () => {
  it('shows demo mode until the SharePoint lists are set', async () => {
    mockApi({ '/me': { ...adminUser, permissions: [...adminUser.permissions] }, '/connectors/site-validation': DEMO })
    renderRoute('/admin/connectors')
    const card = await screen.findByTestId('site-validation-connector')
    expect(await within(card).findByText('Demo mode')).toBeInTheDocument()
    expect(within(card).getByText(DEMO.reason!)).toBeInTheDocument()
    expect(within(card).getByRole('button', { name: /Test connection/ })).toBeDisabled()
  })

  it('shows what was read, and rows it could not use', async () => {
    mockApi({
      '/me': adminUser,
      '/connectors/site-validation': {
        ...DEMO,
        mode: 'sharepoint',
        reason: null,
        site_url: 'https://example.sharepoint.com/sites/physics',
        sites_list: 'Site validation - Sites',
        validations_list: 'Site validation - Validations',
        scans_list: 'Phantom scans',
        ok: true,
        fetched_at: '2026-11-17T09:00:00Z',
        counts: { sites: 31, validations: 120, scans: 14 },
        skipped: { sites: 0, validations: 2, scans: 0, not_matched_to_a_site: 1 },
      },
    })
    renderRoute('/admin/connectors')
    const card = await screen.findByTestId('site-validation-connector')
    expect(await within(card).findByText('Connected')).toBeInTheDocument()
    expect(within(card).getByText('31 sites, 120 validations, 14 phantom scans')).toBeInTheDocument()
    expect(within(card).getByText(/2 validation rows/)).toBeInTheDocument()
    expect(within(card).getByText(/1 rows whose site name matches no site/)).toBeInTheDocument()
  })
})
