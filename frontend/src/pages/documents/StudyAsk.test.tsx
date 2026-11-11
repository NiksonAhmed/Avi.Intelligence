import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { AskResponse, AssistantStatus } from '../../api/types'
import { studyAnswerAsText } from '../../lib/assistant'
import { adminUser, mockApi, renderRoute } from '../../test/utils'

const status: AssistantStatus = {
  ai_enabled: false,
  model: null,
  demo: true,
  documents: 11,
  passages: 60,
  failed: 0,
  last_indexed_at: '2026-11-05T00:00:00Z',
  suggested_questions: ['What are the key steps in SOP-011 Site Activation?'],
  study_questions: ['How are my studies going?', 'Is anything due for study close-out?'],
}

const studyAnswer: AskResponse = {
  interaction_id: 'i2',
  mode: 'study-lookup',
  outcome: 'answered',
  segments: [],
  citations: [],
  excerpts: [],
  notice: null,
  model: null,
  demo: true,
  kind: 'study',
  study: {
    intent: 'due',
    understood: 'What is due · close-out · next 90 days · all studies',
    headline: '2 close-out entries need attention in the next 90 days.',
    lines: ['1 close-out plan entry due in the next 90 days.', '1 already overdue.'],
    tables: [
      {
        title: 'Close-out due and overdue entries',
        columns: ['Study', 'Plan entry', 'Original end', 'Current end', 'Slip', 'Status'],
        rows: [['DEMO-NEU-101', 'Database lock', '—', '6 Nov 2026 (5 days ago)', 'no original date', 'Overdue']],
        links: ['/command-centre/s3?tab=milestones'],
        more: 0,
      },
    ],
    sources: [{ label: 'DEMO-NEU-101 · Study Command Centre', url: '/command-centre/s3?tab=milestones' }],
    as_of: '2026-11-11T02:00:00Z',
    sandbox_only: false,
    follow_ups: ['Are we falling behind?'],
    note: 'Worked out by Avi.Intelligence from its read-only copy of SimpleTrials.',
  },
}

describe('Ask Avi.Intelligence about studies', () => {
  it('shows a study answer with how it was read, a linked table, sources and follow-ups', async () => {
    const fetchMock = mockApi({ '/me': adminUser, '/assistant/status': status, '/assistant/ask': studyAnswer })
    renderRoute('/documents/ask')

    // Study examples are offered, and they work without an AI key.
    await userEvent.click(await screen.findByRole('button', { name: 'Is anything due for study close-out?' }))

    expect(await screen.findByTestId('study-headline')).toHaveTextContent('2 close-out entries need attention')
    expect(screen.getByTestId('study-understood')).toHaveTextContent('Read as: What is due · close-out · next 90 days')
    expect(screen.getByText('No AI · worked out by fixed rules')).toBeInTheDocument()
    expect(screen.getByText('1 already overdue.')).toBeInTheDocument()

    const row = screen.getByTestId('study-answer-row')
    expect(within(row).getByRole('link', { name: 'Database lock' })).toHaveAttribute('href', '/command-centre/s3?tab=milestones')
    expect(screen.getByRole('link', { name: /DEMO-NEU-101 · Study Command Centre/ })).toBeInTheDocument()
    expect(screen.getByText(/Data as of/)).toBeInTheDocument()

    // A follow-up asks again.
    await userEvent.click(screen.getByRole('button', { name: 'Are we falling behind?' }))
    const asks = fetchMock.mock.calls.filter(([u]) => String(u).includes('/assistant/ask'))
    expect(asks).toHaveLength(2)
    expect(JSON.parse(String((asks[1]![1] as RequestInit).body))).toEqual({ question: 'Are we falling behind?' })
  })

  it('copies a study answer as plain text', () => {
    const text = studyAnswerAsText(studyAnswer)
    expect(text).toContain('2 close-out entries need attention')
    expect(text).toContain('- 1 already overdue.')
    expect(text).toContain('DEMO-NEU-101 | Database lock')
  })
})
