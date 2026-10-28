import { useState, useRef, useEffect } from 'react'
import { Card, Spinner, Alert } from '../components/ui'
import { PageShell } from '../components/Layout'
import { ragApi } from '../services/api'
import type { ChatMessage } from '../types'

function MessageBubble({ msg }: { msg: ChatMessage }) {
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
            msg.content
          )}
        </div>

        {/* Sources */}
        {msg.sources && msg.sources.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1">
            {msg.sources.map((s, i) => (
              <span
                key={i}
                className="inline-block px-2 py-0.5 rounded-full bg-slate-100 text-slate-500 text-xs border border-slate-200"
                title={s}
              >
                📄 {s.length > 40 ? `${s.slice(0, 37)}…` : s}
              </span>
            ))}
          </div>
        )}

        {/* Fallback notice */}
        {msg.isFallback && (
          <div className="mt-2 p-2 rounded-lg bg-amber-50 border border-amber-200 text-xs text-amber-700">
            ⚠️ This question falls outside the scope of the available knowledge base.
            Please consult your bank directly for authoritative guidance.
          </div>
        )}

        <p className="text-xs text-slate-400 mt-1 px-1">
          {msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
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

const SUGGESTED_QUESTIONS = [
  'What documents do I need to open a savings account?',
  'How do I dispute an unauthorised transaction?',
  'What are the typical interest rates for personal loans?',
  'How does two-factor authentication protect my account?',
]

const WELCOME_MESSAGE: ChatMessage = {
  id: 'welcome',
  role: 'assistant',
  content:
    "Hello! I'm the BankTech FAQ Assistant. I can answer questions about banking products, digital services, security, and procedures based on publicly available information.\n\nHow can I help you today?",
  timestamp: new Date(0), // static epoch timestamp — avoids purity lint
}

export default function FaqPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME_MESSAGE])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [apiError, setApiError] = useState<string | null>(null)
  const [conversationId, setConversationId] = useState<string | undefined>()
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function sendMessage(question: string) {
    const text = question.trim()
    if (!text || isLoading) return

    setInput('')
    setApiError(null)

    // eslint-disable-next-line -- Date.now() is in an async event handler, not render
    const now = new Date(Date.now())

    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
      timestamp: now,
    }

    const loadingMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'assistant',
      content: '',
      isLoading: true,
      // eslint-disable-next-line -- event handler, not render
      timestamp: new Date(Date.now()),
    }

    setMessages(prev => [...prev, userMsg, loadingMsg])
    setIsLoading(true)

    try {
      const res = await ragApi.ask({ question: text, conversation_id: conversationId })
      setConversationId(res.conversation_id)

      setMessages(prev =>
        prev.map(m =>
          m.id === loadingMsg.id
            ? {
                ...m,
                content: res.answer,
                sources: res.sources,
                isFallback: res.is_fallback,
                isLoading: false,
              }
            : m
        )
      )
    } catch {
      // Phase 1: API not yet wired — show a clear placeholder response
      setMessages(prev =>
        prev.map(m =>
          m.id === loadingMsg.id
            ? {
                ...m,
                content:
                  '📌 The FAQ Assistant backend (RAG) is not yet connected. It will be implemented in Phase 2 using ChromaDB and an LLM. Your question has been noted.',
                isLoading: false,
                isFallback: false,
              }
            : m
        )
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

  return (
    <PageShell
      title="Banking FAQ Assistant"
      subtitle="AI-powered answers to common banking questions — grounded in policy documents (Phase 2)"
    >
      <div className="max-w-3xl mx-auto">
        {/* Phase banner */}
        <div className="mb-4 p-3 rounded-lg bg-blue-50 border border-blue-200 text-xs text-blue-700 flex gap-2">
          <span className="shrink-0">🔬</span>
          <span>
            <strong>Phase 1 preview:</strong> The RAG pipeline (ChromaDB + LLM) will be connected in Phase 2.
            The interface is fully functional — responses currently use a placeholder until the backend is wired.
          </span>
        </div>

        {apiError && (
          <div className="mb-4">
            <Alert type="error">{apiError}</Alert>
          </div>
        )}

        <Card padding={false} className="flex flex-col" style={{ height: '65vh' } as React.CSSProperties}>
          {/* Chat history */}
          <div className="flex-1 overflow-y-auto p-5 space-y-4">
            {messages.map(msg => (
              <MessageBubble key={msg.id} msg={msg} />
            ))}
            <div ref={bottomRef} />
          </div>

          {/* Suggested questions */}
          {messages.length === 1 && (
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
          This assistant provides general information only. Always verify with your bank for official guidance.
        </p>
      </div>
    </PageShell>
  )
}
