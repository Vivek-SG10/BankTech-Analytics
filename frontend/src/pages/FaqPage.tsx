/**
 * FaqPage — Banking FAQ Assistant with RAG backend integration.
 *
 * Features:
 *  - Chat interface with loading indicator, source citations, unsupported-Q handling
 *  - Suggested questions, clear-chat action
 *  - Admin panel: document upload (with progress/validation), listing, deletion,
 *    status update (active / superseded), re-index trigger
 *  - Role-based access: customers see only "all"-level docs in retrieval
 *  - Feedback collection (👍/👎/partial) stored locally per session
 *  - RAG health status indicator
 */
import { useState, useRef, useEffect, useCallback, Component, type ErrorInfo, type ReactNode } from 'react'
import { Card, Spinner, Alert, Badge, Button } from '../components/ui'
import { PageShell } from '../components/Layout'
import { ragApi } from '../services/api'
import { useAuth } from '../context/useAuth'
import type { ChatMessage, SourceCitation, KBDocument } from '../types'

// ── Helpers ─────────────────────────────────────────────────────────────────

const generateId = () => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(36).substring(2, 9)}`
}

function formatTime(timestamp: Date | string | number | undefined): string {
  if (!timestamp) return ''
  const d = timestamp instanceof Date ? timestamp : new Date(timestamp)
  if (isNaN(d.getTime()) || d.getTime() === 0) return ''
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

class FaqErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean; error: Error | null }> {
  constructor(props: { children: ReactNode }) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('FAQ Assistant Error caught by boundary:', error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      return (
        <PageShell title="Banking FAQ Assistant" subtitle="AI-powered answers grounded in approved policy documents">
          <div className="max-w-2xl mx-auto p-6 bg-red-50 border border-red-200 rounded-xl text-center space-y-4">
            <h3 className="text-lg font-semibold text-red-800">Something went wrong in the FAQ Assistant</h3>
            <p className="text-sm text-red-600">
              {this.state.error?.message || 'An unexpected rendering error occurred.'}
            </p>
            <button
              onClick={() => {
                this.setState({ hasError: false, error: null })
                window.location.reload()
              }}
              className="px-4 py-2 bg-red-600 text-white text-sm font-medium rounded-lg hover:bg-red-700 transition"
            >
              Reload FAQ Assistant
            </button>
          </div>
        </PageShell>
      )
    }
    return this.props.children
  }
}

// ── Constants ───────────────────────────────────────────────────────────────

const SUGGESTED_QUESTIONS = [
  'What documents do I need to open a savings account?',
  'How do I dispute an unauthorised transaction?',
  'What are the fees for international wire transfers?',
  'How does two-factor authentication protect my account?',
  'What is the maximum ATM withdrawal limit per day?',
  'How do I activate my new debit card?',
]

const WELCOME_MESSAGE: ChatMessage = {
  id: 'welcome',
  role: 'assistant',
  content:
    "Hello! I'm the BankTech FAQ Assistant. I answer questions about banking products, digital services, security, and procedures — grounded in approved policy documents.\n\nHow can I help you today?",
  timestamp: new Date(0),
}

const ACCEPTED_TYPES = ['.pdf', '.txt', '.docx']
const MAX_MB = 20

// ── Sub-components ──────────────────────────────────────────────────────────

function SourceChip({ source }: { source: SourceCitation | string }) {
  if (typeof source === 'string') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 text-xs border border-blue-200 cursor-default">
        📄 {source.length > 50 ? `${source.slice(0, 47)}…` : source}
      </span>
    )
  }
  const title = source?.title || 'Document'
  const label = source?.page_or_section ? `${title} — ${source.page_or_section}` : title
  const score = typeof source?.relevance_score === 'number' ? source.relevance_score : 1
  const pct = Math.round(score * 100)
  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 text-xs border border-blue-200 cursor-default"
      title={`Relevance: ${pct}%`}
    >
      📄 {label.length > 50 ? `${label.slice(0, 47)}…` : label}
      <span className="text-blue-400">({pct}%)</span>
    </span>
  )
}

function FeedbackButtons({
  messageId,
  feedback,
  onFeedback,
}: {
  messageId: string
  feedback: ChatMessage['feedback']
  onFeedback: (id: string, rating: NonNullable<ChatMessage['feedback']>) => void
}) {
  if (feedback) {
    const labels = {
      helpful: '👍 Helpful',
      not_helpful: '👎 Not helpful',
      partially_helpful: '🤔 Partial',
    }
    return (
      <span className="text-xs text-slate-400 mt-1 ml-1">
        {labels[feedback]} — thank you!
      </span>
    )
  }
  return (
    <div className="flex gap-1 mt-1 ml-1">
      <span className="text-xs text-slate-400 mr-1">Was this helpful?</span>
      {(['helpful', 'partially_helpful', 'not_helpful'] as const).map(r => (
        <button
          key={r}
          onClick={() => onFeedback(messageId, r)}
          className="text-xs px-2 py-0.5 rounded-full border border-slate-200 text-slate-500 hover:bg-slate-50 transition"
        >
          {r === 'helpful' ? '👍' : r === 'partially_helpful' ? '🤔' : '👎'}
        </button>
      ))}
    </div>
  )
}

function MessageBubble({
  msg,
  onFeedback,
}: {
  msg: ChatMessage
  onFeedback: (id: string, rating: NonNullable<ChatMessage['feedback']>) => void
}) {
  const isUser = msg.role === 'user'
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} gap-2 items-end`}>
      {!isUser && (
        <div className="h-8 w-8 rounded-full bg-blue-100 flex items-center justify-center text-sm shrink-0 mb-1">
          🤖
        </div>
      )}
      <div className={`max-w-[80%] ${isUser ? 'order-first' : ''}`}>
        <div
          className={`px-4 py-3 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap ${
            isUser
              ? 'bg-blue-600 text-white rounded-br-sm'
              : 'bg-white border border-slate-200 text-slate-800 rounded-bl-sm shadow-sm'
          }`}
        >
          {msg.isLoading ? (
            <span className="flex items-center gap-2 text-slate-400">
              <Spinner size="sm" />
              Thinking…
            </span>
          ) : (
            typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content ?? '')
          )}
        </div>

        {/* Source citations */}
        {Array.isArray(msg.sources) && msg.sources.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1">
            {msg.sources.map((s, i) => (
              <SourceChip key={i} source={s} />
            ))}
          </div>
        )}

        {/* Unsupported-answer notice */}
        {msg.isFallback && !msg.isLoading && (
          <div className="mt-2 p-2 rounded-lg bg-amber-50 border border-amber-200 text-xs text-amber-700">
            ⚠️ This question is outside the scope of the available knowledge base, or involves
            sensitive credentials. Please contact your bank directly for authoritative guidance.
          </div>
        )}

        {/* Latency */}
        {typeof msg.latency_ms === 'number' && !isNaN(msg.latency_ms) && !msg.isLoading && (
          <p className="text-xs text-slate-300 mt-0.5 px-1">
            {msg.latency_ms < 1000
              ? `${Math.round(msg.latency_ms)} ms`
              : `${(msg.latency_ms / 1000).toFixed(1)} s`}
          </p>
        )}

        {/* Feedback (only for grounded non-loading assistant messages) */}
        {!isUser && !msg.isLoading && msg.id !== 'welcome' && (
          <FeedbackButtons
            messageId={msg.id}
            feedback={msg.feedback}
            onFeedback={onFeedback}
          />
        )}

        <p className="text-xs text-slate-400 mt-1 px-1">
          {formatTime(msg.timestamp)}
        </p>
      </div>
      {isUser && (
        <div className="h-8 w-8 rounded-full bg-slate-200 flex items-center justify-center text-sm shrink-0 mb-1">
          👤
        </div>
      )}
    </div>
  )
}

// ── Admin Document Manager ──────────────────────────────────────────────────

type UploadState = 'idle' | 'uploading' | 'success' | 'error'

function AdminDocManager() {
  const [docs, setDocs] = useState<KBDocument[]>([])
  const [loadingDocs, setLoadingDocs] = useState(true)
  const [docsError, setDocsError] = useState<string | null>(null)

  // Upload form state
  const [uploadTitle, setUploadTitle] = useState('')
  const [uploadDesc, setUploadDesc] = useState('')
  const [uploadAccess, setUploadAccess] = useState<'all' | 'staff' | 'admin'>('all')
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [uploadState, setUploadState] = useState<UploadState>('idle')
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Action feedback
  const [actionMsg, setActionMsg] = useState<{ type: 'ok' | 'err'; text: string } | null>(null)

  const loadDocs = useCallback(async () => {
    setLoadingDocs(true)
    setDocsError(null)
    try {
      const list = await ragApi.listDocuments()
      setDocs(list)
    } catch (e: unknown) {
      setDocsError(e instanceof Error ? e.message : 'Failed to load documents.')
    } finally {
      setLoadingDocs(false)
    }
  }, [])

  useEffect(() => { void loadDocs() }, [loadDocs])

  function validateFile(file: File): string | null {
    const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase()
    if (!ACCEPTED_TYPES.includes(ext)) {
      return `Unsupported file type "${ext}". Accepted: ${ACCEPTED_TYPES.join(', ')}`
    }
    if (file.size > MAX_MB * 1024 * 1024) {
      return `File exceeds ${MAX_MB} MB limit (${(file.size / 1024 / 1024).toFixed(1)} MB).`
    }
    if (file.size === 0) return 'File is empty.'
    return null
  }

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault()
    if (!uploadFile || !uploadTitle.trim()) return
    const fileErr = validateFile(uploadFile)
    if (fileErr) { setUploadError(fileErr); return }

    setUploadState('uploading')
    setUploadError(null)
    setUploadSuccess(null)
    try {
      const doc = await ragApi.uploadDocument(
        uploadFile,
        uploadTitle.trim(),
        uploadAccess,
        uploadDesc.trim() || undefined,
      )
      setUploadSuccess(`"${doc.title}" uploaded — ${doc.chunk_count ?? '?'} chunks indexed.`)
      setUploadState('success')
      setUploadTitle('')
      setUploadDesc('')
      setUploadFile(null)
      if (fileInputRef.current) fileInputRef.current.value = ''
      await loadDocs()
    } catch (e: unknown) {
      setUploadError(e instanceof Error ? e.message : 'Upload failed.')
      setUploadState('error')
    }
  }

  async function handleDelete(doc: KBDocument) {
    if (!window.confirm(`Delete "${doc.title}"? This cannot be undone.`)) return
    setActionMsg(null)
    try {
      await ragApi.deleteDocument(doc.id)
      setActionMsg({ type: 'ok', text: `"${doc.title}" deleted.` })
      await loadDocs()
    } catch (e: unknown) {
      setActionMsg({ type: 'err', text: e instanceof Error ? e.message : 'Delete failed.' })
    }
  }

  async function handleToggleStatus(doc: KBDocument) {
    const newStatus = doc.status === 'active' ? 'superseded' : 'active'
    setActionMsg(null)
    try {
      await ragApi.updateStatus(doc.id, { status: newStatus })
      setActionMsg({ type: 'ok', text: `"${doc.title}" marked as ${newStatus}.` })
      await loadDocs()
    } catch (e: unknown) {
      setActionMsg({ type: 'err', text: e instanceof Error ? e.message : 'Status update failed.' })
    }
  }

  async function handleReindex(doc: KBDocument) {
    setActionMsg(null)
    try {
      await ragApi.reindexDocument(doc.id)
      setActionMsg({ type: 'ok', text: `"${doc.title}" re-indexed.` })
    } catch (e: unknown) {
      // 501 is expected — backend hasn't implemented full re-index from stored bytes yet
      const msg = e instanceof Error ? e.message : 'Re-index failed.'
      setActionMsg({ type: 'err', text: msg })
    }
  }

  const accessBadgeColor = (level: string) =>
    level === 'admin' ? 'red' : level === 'staff' ? 'amber' : 'green'

  return (
    <div className="space-y-6">
      {/* Upload form */}
      <Card>
        <h3 className="text-base font-semibold text-slate-800 mb-4">Upload Document</h3>
        <form onSubmit={e => void handleUpload(e)} className="space-y-4">
          <div className="grid sm:grid-cols-2 gap-4">
            <div className="space-y-1">
              <label className="block text-sm font-medium text-slate-700">
                Title <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={uploadTitle}
                onChange={e => setUploadTitle(e.target.value)}
                placeholder="e.g. Banking Fee Schedule 2026"
                maxLength={255}
                required
                className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 transition"
              />
            </div>
            <div className="space-y-1">
              <label className="block text-sm font-medium text-slate-700">
                Access Level
              </label>
              <select
                value={uploadAccess}
                onChange={e => setUploadAccess(e.target.value as 'all' | 'staff' | 'admin')}
                className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 transition"
              >
                <option value="all">Public (all users)</option>
                <option value="staff">Staff only (employees, managers, researchers)</option>
                <option value="admin">Admin only</option>
              </select>
            </div>
          </div>

          <div className="space-y-1">
            <label className="block text-sm font-medium text-slate-700">Description (optional)</label>
            <input
              type="text"
              value={uploadDesc}
              onChange={e => setUploadDesc(e.target.value)}
              placeholder="Brief description of document content"
              maxLength={1000}
              className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 transition"
            />
          </div>

          <div className="space-y-1">
            <label className="block text-sm font-medium text-slate-700">
              File <span className="text-red-500">*</span>
              <span className="ml-1 text-slate-400 font-normal">(PDF, TXT, DOCX — max {MAX_MB} MB)</span>
            </label>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.txt,.docx"
              onChange={e => setUploadFile(e.target.files?.[0] ?? null)}
              required
              className="block w-full text-sm text-slate-700 file:mr-3 file:py-1.5 file:px-3 file:rounded-md file:border-0 file:text-sm file:font-medium file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100 cursor-pointer"
            />
            {uploadFile && (
              <p className="text-xs text-slate-500">
                {uploadFile.name} — {(uploadFile.size / 1024).toFixed(0)} KB
              </p>
            )}
          </div>

          {uploadError && <Alert type="error">{uploadError}</Alert>}
          {uploadSuccess && <Alert type="success">{uploadSuccess}</Alert>}

          <Button
            type="submit"
            variant="secondary"
            isLoading={uploadState === 'uploading'}
            disabled={uploadState === 'uploading' || !uploadTitle.trim() || !uploadFile}
          >
            {uploadState === 'uploading' ? 'Uploading & indexing…' : 'Upload & Index'}
          </Button>
        </form>
      </Card>

      {/* Document list */}
      <Card>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-semibold text-slate-800">Knowledge Base Documents</h3>
          <Button variant="ghost" size="sm" onClick={() => void loadDocs()} isLoading={loadingDocs}>
            ↻ Refresh
          </Button>
        </div>

        {actionMsg && (
          <div className="mb-3">
            <Alert type={actionMsg.type === 'ok' ? 'success' : 'error'}>{actionMsg.text}</Alert>
          </div>
        )}

        {docsError && <Alert type="error">{docsError}</Alert>}

        {loadingDocs ? (
          <div className="flex justify-center py-8"><Spinner /></div>
        ) : docs.length === 0 ? (
          <p className="text-sm text-slate-500 text-center py-8">
            No documents uploaded yet. Use the form above to add the first document.
          </p>
        ) : (
          <div className="space-y-2">
            {docs.map(doc => (
              <div
                key={doc.id}
                className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3 rounded-lg border border-slate-200 hover:border-slate-300 transition"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium text-slate-800 truncate">{doc.title}</span>
                    <Badge color={doc.status === 'active' ? 'green' : 'slate'}>
                      {doc.status}
                    </Badge>
                    <Badge color={accessBadgeColor(doc.access_level)}>
                      {doc.access_level}
                    </Badge>
                    <Badge color="blue">{doc.file_type.toUpperCase()}</Badge>
                    {doc.chunk_count !== null && (
                      <span className="text-xs text-slate-400">{doc.chunk_count} chunks</span>
                    )}
                  </div>
                  <p className="text-xs text-slate-400 mt-0.5">
                    {doc.filename} · v{doc.version} ·{' '}
                    {new Date(doc.uploaded_at).toLocaleDateString()}
                  </p>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <button
                    onClick={() => void handleToggleStatus(doc)}
                    className="px-2 py-1 text-xs rounded-md border border-slate-200 text-slate-600 hover:bg-slate-50 transition"
                    title={doc.status === 'active' ? 'Mark superseded' : 'Mark active'}
                  >
                    {doc.status === 'active' ? '📦 Supersede' : '✅ Activate'}
                  </button>
                  <button
                    onClick={() => void handleReindex(doc)}
                    className="px-2 py-1 text-xs rounded-md border border-slate-200 text-slate-600 hover:bg-slate-50 transition"
                    title="Re-index document"
                  >
                    🔄 Re-index
                  </button>
                  <button
                    onClick={() => void handleDelete(doc)}
                    className="px-2 py-1 text-xs rounded-md border border-red-200 text-red-600 hover:bg-red-50 transition"
                    title="Delete document"
                  >
                    🗑️ Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}

// ── RAG Health Banner ───────────────────────────────────────────────────────

function RAGHealthBanner() {
  const [health, setHealth] = useState<{ status: string; llm: string; vector_store: string } | null>(null)

  useEffect(() => {
    ragApi.health()
      .then(h => setHealth(h))
      .catch(() => setHealth({ status: 'error', llm: 'unknown', vector_store: 'unknown' }))
  }, [])

  if (!health) return null

  if (health.status === 'ok') return null // No banner needed when healthy

  return (
    <Alert type={health.status === 'degraded' ? 'warning' : 'error'}>
      <strong>RAG service: {health.status}.</strong>{' '}
      LLM: {health.llm} · Vector store: {health.vector_store}.{' '}
      {health.llm === 'not_configured' && 'Set GEMINI_API_KEY in the backend .env to enable answers.'}
    </Alert>
  )
}

// ── Feedback summary ────────────────────────────────────────────────────────

interface FeedbackStats {
  helpful: number
  not_helpful: number
  partially_helpful: number
  total: number
}

function computeFeedback(messages: ChatMessage[]): FeedbackStats {
  const stats: FeedbackStats = { helpful: 0, not_helpful: 0, partially_helpful: 0, total: 0 }
  if (!Array.isArray(messages)) return stats
  for (const m of messages) {
    if (m?.feedback && m.feedback in stats) {
      stats[m.feedback as keyof FeedbackStats]++
      stats.total++
    }
  }
  return stats
}

// ── Main Page ───────────────────────────────────────────────────────────────

function FaqPageInner() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'

  const [activeTab, setActiveTab] = useState<'chat' | 'admin' | 'eval'>('chat')

  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME_MESSAGE])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [apiError, setApiError] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleFeedback = useCallback(
    (messageId: string, rating: NonNullable<ChatMessage['feedback']>) => {
      setMessages(prev =>
        prev.map(m => (m.id === messageId ? { ...m, feedback: rating } : m)),
      )
    },
    [],
  )

  async function sendMessage(question: string) {
    const text = question.trim()
    if (!text || isLoading) return

    setInput('')
    setApiError(null)

    // eslint-disable-next-line -- Date.now() in async event handler, not render
    const now = new Date(Date.now())

    const userMsg: ChatMessage = {
      id: generateId(),
      role: 'user',
      content: text,
      timestamp: now,
    }

    const loadingMsg: ChatMessage = {
      id: generateId(),
      role: 'assistant',
      content: '',
      isLoading: true,
      // eslint-disable-next-line -- event handler
      timestamp: new Date(Date.now()),
    }

    setMessages(prev => [...prev, userMsg, loadingMsg])
    setIsLoading(true)

    try {
      const res = await ragApi.query({ question: text, top_k: 5 })
      const answerText =
        typeof res?.answer === 'string'
          ? res.answer
          : res?.answer
          ? JSON.stringify(res.answer)
          : 'I could not retrieve a grounded answer for your question.'

      setMessages(prev =>
        prev.map(m =>
          m.id === loadingMsg.id
            ? {
                ...m,
                content: answerText,
                sources: Array.isArray(res?.sources) ? res.sources : [],
                isFallback: !res?.is_grounded,
                isLoading: false,
                latency_ms: typeof res?.latency_ms === 'number' ? res.latency_ms : undefined,
              }
            : m,
        ),
      )
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : 'Unknown error'

      // Service-level errors (503, network)
      if (errMsg.includes('503') || errMsg.includes('network') || errMsg.includes('fetch')) {
        setApiError(`Service unavailable: ${errMsg}. The RAG backend may not be running or the API key is not configured.`)
      }

      setMessages(prev =>
        prev.map(m =>
          m.id === loadingMsg.id
            ? {
                ...m,
                content:
                  errMsg.includes('503')
                    ? 'The FAQ service is temporarily unavailable. Please try again later or contact your bank directly.'
                    : `Sorry, I encountered an error processing your question. Please try again.`,
                isLoading: false,
                isFallback: true,
              }
            : m,
        ),
      )
    } finally {
      setIsLoading(false)
      inputRef.current?.focus()
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void sendMessage(input)
    }
  }

  function clearChat() {
    setMessages([WELCOME_MESSAGE])
    setApiError(null)
    setInput('')
    inputRef.current?.focus()
  }

  const fbStats = computeFeedback(messages)

  const tabs = [
    { id: 'chat' as const, label: '💬 FAQ Chat' },
    ...(isAdmin ? [{ id: 'admin' as const, label: '🗂️ Document Manager' }] : []),
    { id: 'eval' as const, label: '📊 Session Report' },
  ]

  return (
    <PageShell
      title="Banking FAQ Assistant"
      subtitle="AI-powered answers grounded in approved policy documents"
    >
      <div className="max-w-4xl mx-auto">
        {/* Health banner */}
        <div className="mb-4">
          <RAGHealthBanner />
        </div>

        {/* Tab nav */}
        <div className="flex gap-1 mb-4 border-b border-slate-200">
          {tabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2 text-sm font-medium rounded-t-lg transition -mb-px border-b-2 ${
                activeTab === tab.id
                  ? 'border-blue-600 text-blue-700 bg-blue-50'
                  : 'border-transparent text-slate-600 hover:text-slate-900 hover:bg-slate-50'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* ── Chat tab ── */}
        {activeTab === 'chat' && (
          <div>
            {apiError && (
              <div className="mb-4">
                <Alert type="error">{apiError}</Alert>
              </div>
            )}

            <Card padding={false} className="flex flex-col" style={{ height: '65vh' } as React.CSSProperties}>
              {/* Toolbar */}
              <div className="flex items-center justify-between px-4 py-2 border-b border-slate-100">
                <span className="text-xs text-slate-500">
                  {messages.length - 1} message{messages.length !== 2 ? 's' : ''}
                </span>
                <button
                  onClick={clearChat}
                  disabled={messages.length <= 1}
                  className="text-xs text-slate-400 hover:text-slate-600 disabled:opacity-30 transition"
                >
                  ✕ Clear chat
                </button>
              </div>

              {/* Chat history */}
              <div className="flex-1 overflow-y-auto p-5 space-y-4">
                {messages.map(msg => (
                  <MessageBubble key={msg.id} msg={msg} onFeedback={handleFeedback} />
                ))}
                <div ref={bottomRef} />
              </div>

              {/* Suggested questions (shown until second message) */}
              {messages.length <= 1 && (
                <div className="px-5 pb-3 border-t border-slate-100">
                  <p className="text-xs text-slate-500 mb-2 pt-3">Suggested questions:</p>
                  <div className="flex flex-wrap gap-2">
                    {SUGGESTED_QUESTIONS.map(q => (
                      <button
                        key={q}
                        onClick={() => void sendMessage(q)}
                        disabled={isLoading}
                        className="px-3 py-1.5 rounded-full border border-slate-200 text-xs text-slate-600 hover:border-blue-400 hover:text-blue-700 hover:bg-blue-50 transition disabled:opacity-40"
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Input area */}
              <div className="border-t border-slate-200 p-4 flex gap-3 items-end">
                <textarea
                  ref={inputRef}
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Ask a banking question… (Enter to send, Shift+Enter for new line)"
                  rows={2}
                  disabled={isLoading}
                  className="flex-1 px-3 py-2 text-sm rounded-xl border border-slate-300 bg-white text-slate-900 placeholder-slate-400 resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-slate-50 transition"
                />
                <button
                  onClick={() => void sendMessage(input)}
                  disabled={isLoading || !input.trim()}
                  className="h-10 w-10 rounded-xl bg-blue-600 text-white flex items-center justify-center hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition shrink-0"
                  aria-label="Send message"
                >
                  {isLoading ? <Spinner size="sm" /> : '↑'}
                </button>
              </div>
            </Card>

            <p className="text-xs text-center text-slate-400 mt-3">
              Answers are grounded in approved policy documents only. Always verify important matters with your bank.
            </p>
          </div>
        )}

        {/* ── Admin document manager tab ── */}
        {activeTab === 'admin' && isAdmin && <AdminDocManager />}

        {/* ── Session evaluation report tab ── */}
        {activeTab === 'eval' && (
          <Card>
            <h3 className="text-base font-semibold text-slate-800 mb-4">Session Report</h3>
            <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
              {[
                { label: 'Messages sent', value: messages.filter(m => m.role === 'user').length },
                {
                  label: 'Grounded answers',
                  value: messages.filter(m => m.role === 'assistant' && !m.isFallback && !m.isLoading && m.id !== 'welcome').length,
                },
                {
                  label: 'Unsupported',
                  value: messages.filter(m => m.role === 'assistant' && m.isFallback && !m.isLoading).length,
                },
                {
                  label: 'Avg latency',
                  value: (() => {
                    const latencies = messages
                      .filter(m => m.latency_ms !== undefined)
                      .map(m => m.latency_ms!)
                    return latencies.length
                      ? `${Math.round(latencies.reduce((a, b) => a + b, 0) / latencies.length)} ms`
                      : '—'
                  })(),
                },
              ].map(stat => (
                <div key={stat.label} className="rounded-lg border border-slate-200 p-4 text-center">
                  <p className="text-2xl font-bold text-blue-700">{stat.value}</p>
                  <p className="text-xs text-slate-500 mt-1">{stat.label}</p>
                </div>
              ))}
            </div>

            {/* Feedback summary */}
            {fbStats.total > 0 && (
              <div className="mb-6">
                <h4 className="text-sm font-medium text-slate-700 mb-3">User Feedback</h4>
                <div className="flex gap-4">
                  {[
                    { label: '👍 Helpful', count: fbStats.helpful, color: 'text-green-700' },
                    { label: '🤔 Partial', count: fbStats.partially_helpful, color: 'text-amber-700' },
                    { label: '👎 Not helpful', count: fbStats.not_helpful, color: 'text-red-700' },
                  ].map(fb => (
                    <div key={fb.label}>
                      <span className={`text-sm font-semibold ${fb.color}`}>{fb.count}</span>
                      <span className="text-xs text-slate-500 ml-1">{fb.label}</span>
                    </div>
                  ))}
                </div>
                <p className="text-xs text-slate-400 mt-2">
                  Satisfaction rate:{' '}
                  <strong>
                    {fbStats.total
                      ? `${Math.round(((fbStats.helpful + fbStats.partially_helpful * 0.5) / fbStats.total) * 100)}%`
                      : '—'}
                  </strong>{' '}
                  ({fbStats.total} rated)
                </p>
              </div>
            )}

            {/* Per-message table */}
            {messages.filter(m => m.role === 'assistant' && m.id !== 'welcome' && !m.isLoading).length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-slate-200 text-left text-slate-500">
                      <th className="pb-2 font-medium">Question (truncated)</th>
                      <th className="pb-2 font-medium">Grounded</th>
                      <th className="pb-2 font-medium">Sources</th>
                      <th className="pb-2 font-medium">Latency</th>
                      <th className="pb-2 font-medium">Feedback</th>
                    </tr>
                  </thead>
                  <tbody>
                    {messages
                      .filter(m => m.role === 'user')
                      .map((userMsg) => {
                        // Find the assistant reply immediately after
                        const msgIndex = messages.indexOf(userMsg)
                        const reply = messages[msgIndex + 1]
                        if (!reply || reply.isLoading) return null
                        return (
                          <tr key={userMsg.id} className="border-b border-slate-100">
                            <td className="py-2 max-w-xs truncate pr-2 text-slate-700">
                              {userMsg.content.length > 60
                                ? `${userMsg.content.slice(0, 57)}…`
                                : userMsg.content}
                            </td>
                            <td className="py-2">
                              {reply.isFallback
                                ? <span className="text-amber-600">✗</span>
                                : <span className="text-green-600">✓</span>}
                            </td>
                            <td className="py-2 text-slate-500">
                              {reply.sources?.length ?? 0}
                            </td>
                            <td className="py-2 text-slate-500">
                              {reply.latency_ms !== undefined
                                ? reply.latency_ms < 1000
                                  ? `${Math.round(reply.latency_ms)} ms`
                                  : `${(reply.latency_ms / 1000).toFixed(1)} s`
                                : '—'}
                            </td>
                            <td className="py-2 text-slate-500">
                              {reply.feedback ?? '—'}
                            </td>
                          </tr>
                        )
                      })}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-sm text-slate-500">
                No questions asked yet in this session. Start a chat to populate this report.
              </p>
            )}

            <p className="mt-4 text-xs text-slate-400">
              Note: This report reflects the current browser session only. No session data is stored on the server.
              Latencies and feedback ratings are measured values, not estimates.
            </p>
          </Card>
        )}
      </div>
    </PageShell>
  )
}

export default function FaqPage() {
  return (
    <FaqErrorBoundary>
      <FaqPageInner />
    </FaqErrorBoundary>
  )
}
