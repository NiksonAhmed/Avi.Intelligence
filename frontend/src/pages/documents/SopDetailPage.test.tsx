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
    expect(screen.queryByText('SharePoint save history')).not.toBeInTheDocument()

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

  it("shows the document's own version, review date, sign-off and change history", async () => {
    const doc = makeSop({
      version: '2.0',
      version_source: 'document',
      file_name_version: '1.0',
      effective_date: null,
      review_date: '2027-11-11T00:00:00Z',
      details: {
        version: '2.0',
        effective_date: null,
        review_date: '2027-11-11',
        prepared_by: 'Alex Writer',
        prepared_date: '2025-10-09',
        reviewed_by: 'Blair Checker',
        reviewed_date: '2025-10-21',
        approved_by: 'Casey Approver',
        approved_date: '2025-11-14',
        revisions: [
          { issued: '2023-03-23', version: '1.0', changes: 'New Issue' },
          { issued: null, version: '2.0', changes: 'General review' },
        ],
      },
    })
    mockApi({ '/me': adminUser, '/sops/demo-sop-011': makeSopDetail(doc) })
    renderRoute('/documents/sops/demo-sop-011')

    expect(await screen.findByText("From the document's cover page.")).toBeInTheDocument()
    expect(screen.getByText('File name says 1.0')).toBeInTheDocument()
    expect(screen.getByText("Not stated on the document's cover (approved 14 Nov 2025)")).toBeInTheDocument()
    expect(screen.getByText('Casey Approver, 14 Nov 2025')).toBeInTheDocument()
    expect(screen.getByText('Change history')).toBeInTheDocument()
    expect(screen.getByText('General review')).toBeInTheDocument()
    expect(screen.getByText('23 Mar 2023')).toBeInTheDocument()
  })

  it('lists the forms and templates of an SOP', async () => {
    const form = makeSop({
      id: 'f1',
      kind: 'form',
      sop_number: 'CO-005-A',
      parent_sop_number: 'CO-SOP-005',
      title: 'Site Qualification Visit Report',
      file_name: 'CO-005-A_Site_Qualification_Visit_Report_2.0.pdf',
      editable_copy: { id: 'w1', file_name: 'CO-005-A Site Qualification Visit Report_2.0.docx', size_bytes: 1, mime_type: null },
    })
    mockApi({ '/me': adminUser, '/sops/demo-sop-011': makeSopDetail(makeSop(), { forms: [form] }) })
    renderRoute('/documents/sops/demo-sop-011')
    expect(await screen.findByText('Forms and templates (1)')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Site Qualification Visit Report' })).toHaveAttribute(
      'href',
      '/documents/sops/f1',
    )
    // Word first for filling in, the signed PDF alongside.
    expect(screen.getByRole('link', { name: 'Download CO-005-A as Word' })).toHaveAttribute(
      'href',
      '/api/v1/sops/f1/download?format=word',
    )
    expect(screen.getByRole('link', { name: 'Download CO-005-A as PDF' })).toHaveAttribute(
      'href',
      '/api/v1/sops/f1/download',
    )
  })

  it('offers Word on a live form page but only the filed copy for an SOP', async () => {
    const form = makeSop({
      id: 'f1',
      kind: 'form',
      sop_number: 'CO-005-A',
      file_name: 'CO-005-A_Report.pdf',
      editable_copy: { id: 'w1', file_name: 'CO-005-A Report.docx', size_bytes: 1, mime_type: null },
    })
    const live = makeSopDetail(form)
    live.source = { ...live.source, mode: 'live' }
    mockApi({ '/me': adminUser, '/sops/f1': live })
    const { unmount } = renderRoute('/documents/sops/f1')
    expect(await screen.findByRole('link', { name: 'Download CO-005-A as Word' })).toBeInTheDocument()
    unmount()

    const sop = makeSopDetail(makeSop({ file_name: 'SOP-011 Site Activation.pdf' }))
    sop.source = { ...sop.source, mode: 'live' }
    mockApi({ '/me': adminUser, '/sops/demo-sop-011': sop })
    renderRoute('/documents/sops/demo-sop-011')
    expect(await screen.findByRole('link', { name: /Download$/ })).toHaveAttribute(
      'href',
      '/api/v1/sops/demo-sop-011/download',
    )
    expect(screen.queryByRole('link', { name: /as Word/ })).not.toBeInTheDocument()
  })

  it('links a form back to its SOP', async () => {
    const sop = makeSop({ id: 's5', sop_number: 'CO-SOP-005', title: 'Investigator Site Selection' })
    const form = makeSop({ id: 'f1', kind: 'form', sop_number: 'CO-005-A', parent_sop_number: 'CO-SOP-005' })
    mockApi({ '/me': adminUser, '/sops/f1': makeSopDetail(form, { parent: sop }) })
    renderRoute('/documents/sops/f1')
    expect(await screen.findByText('Form number')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'CO-SOP-005 · Investigator Site Selection' })).toHaveAttribute(
      'href',
      '/documents/sops/s5',
    )
    expect(screen.queryByText(/Forms and templates/)).not.toBeInTheDocument()
  })

  it('shows not found for unknown SOPs', async () => {
    mockApi({ '/me': adminUser })
    renderRoute('/documents/sops/missing')
    expect(await screen.findByText('SOP not found')).toBeInTheDocument()
  })
})
