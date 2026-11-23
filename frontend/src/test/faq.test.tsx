import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import FaqPage from '../pages/FaqPage'
import { ragApi } from '../services/api'

// Mock api
vi.mock('../services/api', () => ({
  ragApi: {
    health: vi.fn().mockResolvedValue({ status: 'ok', llm: 'configured', vector_store: 'ok' }),
    query: vi.fn(),
    listDocuments: vi.fn().mockResolvedValue([]),
    getDocument: vi.fn(),
    uploadDocument: vi.fn(),
    deleteDocument: vi.fn(),
    updateStatus: vi.fn(),
    reindexDocument: vi.fn(),
  },
  authApi: {
    me: vi.fn().mockResolvedValue({ id: 'u1', name: 'Test User', role: 'customer' }),
  }
}))

vi.mock('../context/useAuth', () => ({
  useAuth: () => ({
    user: { id: 'u1', name: 'Test User', role: 'customer' },
    isAuthenticated: true,
    isLoading: false,
  })
}))

// Mock scrollIntoView
window.HTMLElement.prototype.scrollIntoView = vi.fn()

describe('FaqPage Component', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders welcome message and suggested questions', () => {
    render(
      <MemoryRouter>
        <FaqPage />
      </MemoryRouter>
    )

    expect(screen.getByText(/Banking FAQ Assistant/i)).toBeDefined()
    expect(screen.getByText(/What documents do I need to open a savings account\?/i)).toBeDefined()
  })

  it('handles clicking a suggested question without crashing', async () => {
    vi.mocked(ragApi.query).mockResolvedValueOnce({
      answer: 'Savings accounts require government photo ID and address proof.',
      sources: [
        { document_id: 'doc-1', title: 'Account Opening Policy', page_or_section: 'Section 2', relevance_score: 0.92 }
      ],
      is_grounded: true,
      latency_ms: 150
    })

    render(
      <MemoryRouter>
        <FaqPage />
      </MemoryRouter>
    )

    const questionBtn = screen.getByText('What documents do I need to open a savings account?')
    fireEvent.click(questionBtn)

    await waitFor(() => {
      expect(screen.getByText(/Savings accounts require government photo ID/i)).toBeDefined()
    })
    // Regular customer must NOT see source citations
    expect(screen.queryByText(/Account Opening Policy/i)).toBeNull()
  })

  it('handles backend network/500/503 error without crashing', async () => {
    vi.mocked(ragApi.query).mockRejectedValueOnce(new Error('HTTP 500 Internal Server Error'))

    render(
      <MemoryRouter>
        <FaqPage />
      </MemoryRouter>
    )

    const input = screen.getByPlaceholderText(/Ask a banking question/i)
    fireEvent.change(input, { target: { value: 'documents required for ekyc' } })

    const sendBtn = screen.getByLabelText('Send message')
    fireEvent.click(sendBtn)

    await waitFor(() => {
      expect(screen.getByText(/Sorry, I encountered an error processing your question/i)).toBeDefined()
    })
  })
})
