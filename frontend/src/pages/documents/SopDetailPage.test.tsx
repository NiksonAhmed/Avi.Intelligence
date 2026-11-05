import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { adminUser, makeSop, makeSopDetail, mockApi, renderRoute, viewerUser } from '../../test/utils'

describe('SOP detail page', () => {
  it('shows key information, version history and a download link', async () => {
    const doc = makeSop({ web_url: 'https://avion.sharepoint.com/sites/Quality/x.pdf' })
    mockApi({ '/me': adminUser, '/sops/demo-sop-011': makeSopDetail(doc) })
    renderRoute('/documents/sops/demo-sop-011')

    expect(await screen.findByText('Key information')).toBeInTheDocument()
    expect(screen.getByText('Director, Clinical Operations')).toBeInTheDocument()
    expect(screen.getByText('Version history')).toBeInTheDocument()

    const download = await screen.findByRole('link', { name: /Download demo file/ })
    expect(download).toHaveAttribute('href', '/api/v1/sops/demo-sop-011/download')
    const open = screen.getByRole('link', { name: /Open in SharePoint/ })
    expect(open).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('hides download for roles without permission', async () => {
    mockApi({ '/me': viewerUser, '/sops/demo-sop-011': makeSopDetail(makeSop()) })
    renderRoute('/documents/sops/demo-sop-011')
    expect(await screen.findByText('Key information')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Download/ })).not.toBeInTheDocument()
  })

  it('warns when the SOP is not effective', async () => {
    mockApi({ '/me': adminUser, '/sops/demo-sop-011': makeSopDetail(makeSop({ status: 'Draft' })) })
    renderRoute('/documents/sops/demo-sop-011')
    expect(await screen.findByText('This SOP is draft.')).toBeInTheDocument()
  })

  it('shows not found for unknown SOPs', async () => {
    mockApi({ '/me': adminUser })
    renderRoute('/documents/sops/missing')
    expect(await screen.findByText('SOP not found')).toBeInTheDocument()
  })
})
