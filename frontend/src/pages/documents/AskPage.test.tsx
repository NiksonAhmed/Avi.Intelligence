import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { AskResponse, AssistantStatus } from '../../api/types'
import { answerAsText } from '../../lib/assistant'
import { adminUser, mockApi, renderRoute } from '../../test/utils'

const status: AssistantStatus = {
  ai_enabled: true,
  model: 'claude-opus-5-5',
  demo: true,
  documents: 11,
  passages: 60,
  failed: 0,
  last_indexed_at: '2026-11-05T00:00:00Z',
  suggested_questions: ['What are the key steps in SOP-011 Site Activation?'],
  study_questions: ['How are my studies going?'],
}

const aiAnswer: AskResponse = {
  interaction_id: 'i1',
  mode: 'ai',
  outcome: 'answered',
  segments: [
    { text: 'The CRA conducts the site initiation visit', citations: [1] },
    { text: ' and all staff complete protocol training.', citations: [1, 2] },
  ],
  citations: [
    {
      number: 1,
      sop_id: 'demo-sop-011',
      sop_number: 'SOP-011',
      title: 'Site Activation',
      version: '3.0',
      section: '4.3 Site initiation visit',
      cited_text: 'The CRA conducts the site initiation visit (SIV) using the approved SIV checklist.',
      web_url: null,
    },
    {
      number: 2,
      sop_id: 'demo-sop-011',
      sop_number: 'SOP-011',
      title: 'Site Activation',
      version: '3.0',
      section: '4.3 Site initiation visit',
      cited_text: 'All site staff on the delegation log must complete protocol training.',
      web_url: null,
    },
  ],
  excerpts: [],
  notice: null,
  model: 'claude-opus-5-5',
  demo: true,
  kind: 'sop',
  study: null,
}

describe('Ask Avi.Intelligence', () => {
  it('asks a question and shows a cited AI answer with linked sources', async () => {
    const fetchMock = mockApi({ '/me': adminUser, '/assistant/status': status, '/assistant/ask': aiAnswer })
    renderRoute('/documents/ask')

    await userEvent.type(
      await screen.findByRole('textbox', { name: 'Your question' }),
      'What happens at the SIV?',
    )
    await userEvent.click(screen.getByRole('button', { name: /Ask$/ }))

    expect(await screen.findByText('Grounded in effective SOPs')).toBeInTheDocument()
    expect(screen.getAllByText(/The CRA conducts the site initiation visit/)).toHaveLength(2) // answer + quote
    expect(screen.getByText(/AI suggestion/)).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: 'Source 1' })).toHaveLength(2)

    const sources = screen.getByRole('list', { name: 'Source documents' })
    const links = within(sources).getAllByRole('link', { name: 'SOP-011 Site Activation v3.0' })
    expect(links[0]).toHaveAttribute('href', '/documents/sops/demo-sop-011')

    const calls = fetchMock.mock.calls as unknown as [string, RequestInit | undefined][]
    const askCall = calls.find(([u]) => u.includes('/assistant/ask'))
    expect(askCall?.[1]?.method).toBe('POST')
    expect(JSON.parse(String(askCall?.[1]?.body))).toEqual({ question: 'What happens at the SIV?' })
  })

  it('runs a suggested question', async () => {
    mockApi({ '/me': adminUser, '/assistant/status': status, '/assistant/ask': aiAnswer })
    renderRoute('/documents/ask')
    await userEvent.click(await screen.findByRole('button', { name: status.suggested_questions[0] }))
    expect(await screen.findByText(/all staff complete protocol training/)).toBeInTheDocument()
  })

  it('shows SOP passages and explains when AI is not switched on', async () => {
    const searchOnly: AskResponse = {
      ...aiAnswer,
      mode: 'search-only',
      segments: [],
      citations: [],
      model: null,
      notice: 'AI answers are not switched on yet (no Anthropic API key configured).',
      excerpts: [
        {
          sop_id: 'demo-sop-030',
          sop_number: 'SOP-030',
          title: 'Safety Reporting',
          version: '4.0',
          section: '2.1 Site reporting',
          text: 'The investigator reports an SAE within 24 hours.',
        },
      ],
    }
    mockApi({
      '/me': adminUser,
      '/assistant/status': { ...status, ai_enabled: false, model: null },
      '/assistant/ask': searchOnly,
    })
    renderRoute('/documents/ask')
    expect(await screen.findByText('AI answers are not switched on yet')).toBeInTheDocument()
    await userEvent.type(screen.getByRole('textbox', { name: 'Your question' }), 'SAE timelines{Control>}{Enter}{/Control}')
    expect(await screen.findByText('The investigator reports an SAE within 24 hours.')).toBeInTheDocument()
    expect(screen.queryByText(/AI suggestion/)).not.toBeInTheDocument()
    expect(screen.getByText(/Source record · SOP passages/)).toBeInTheDocument()
  })

  it('shows the error when the AI service is unavailable', async () => {
    mockApi({ '/me': adminUser, '/assistant/status': status })
    renderRoute('/documents/ask')
    await userEvent.type(await screen.findByRole('textbox', { name: 'Your question' }), 'anything here')
    await userEvent.click(screen.getByRole('button', { name: /Ask$/ }))
    await waitFor(() => expect(screen.getByText('Could not answer')).toBeInTheDocument())
  })
})

describe('answerAsText', () => {
  it('keeps numbered references and lists sources', () => {
    const text = answerAsText(aiAnswer)
    expect(text).toContain('site initiation visit [1] and all staff complete protocol training. [1] [2]')
    expect(text).toContain('[2] SOP-011 Site Activation v3.0, section: 4.3 Site initiation visit')
  })
})
