import { useEffect, useRef, useState } from 'react'
import { FileText, Search as SearchIcon, Send } from 'lucide-react'
import { search as apiSearch } from '../api/search'
import type { SearchResponse } from '../types/api'
import LoadingSpinner from '../components/ui/LoadingSpinner'
import axios from 'axios'

interface Message {
  id: string
  type: 'question' | 'answer'
  text: string
  response?: SearchResponse
  errorText?: string
}

const EXAMPLE_QUERIES = [
  'What is the annual leave entitlement?',
  'What was the revenue in Q3 2025?',
  'How do I report a GDPR data breach?',
  'What is the expense reimbursement policy?',
]

export default function KnowledgeSearch() {
  const [messages, setMessages] = useState<Message[]>([])
  const [query, setQuery] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  async function submit() {
    const q = query.trim()
    if (!q || isLoading) return

    const qId = `${Date.now()}`
    setMessages((prev) => [...prev, { id: qId, type: 'question', text: q }])
    setQuery('')
    setIsLoading(true)

    try {
      const result = await apiSearch({ query: q, top_k: 5 })
      setMessages((prev) => [
        ...prev,
        { id: `${qId}_a`, type: 'answer', text: result.answer, response: result },
      ])
    } catch (err: unknown) {
      let errorText = 'Search failed. Please try again.'
      if (axios.isAxiosError(err)) {
        const detail = (err.response?.data as { detail?: string } | undefined)?.detail
        errorText = detail ?? errorText
      }
      setMessages((prev) => [
        ...prev,
        { id: `${qId}_e`, type: 'answer', text: '', errorText },
      ])
    } finally {
      setIsLoading(false)
      inputRef.current?.focus()
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void submit()
    }
  }

  return (
    <div className="flex h-full flex-col" style={{ height: 'calc(100vh - 112px)' }}>
      {/* Empty state */}
      {messages.length === 0 && !isLoading && (
        <div className="flex flex-1 flex-col items-center justify-center gap-4 px-4 text-center">
          <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-blue-100">
            <SearchIcon className="h-8 w-8 text-blue-600" />
          </div>
          <div>
            <h2 className="text-xl font-semibold text-gray-800">InsightHub Knowledge Search</h2>
            <p className="mt-1 max-w-md text-sm text-gray-500">
              Ask questions about company policies, reports, HR guidelines, compliance
              requirements, and more. Powered by Azure AI Search + GPT-4o.
            </p>
          </div>
          <div className="mt-2 flex flex-wrap justify-center gap-2">
            {EXAMPLE_QUERIES.map((q) => (
              <button
                key={q}
                onClick={() => {
                  setQuery(q)
                  inputRef.current?.focus()
                }}
                className="rounded-full border border-gray-200 bg-white px-3 py-1.5 text-xs text-gray-600 transition-colors hover:border-blue-300 hover:text-blue-600"
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Message thread */}
      {(messages.length > 0 || isLoading) && (
        <div className="flex-1 space-y-4 overflow-y-auto pb-4">
          {messages.map((msg) =>
            msg.type === 'question' ? (
              /* Question bubble — right-aligned */
              <div key={msg.id} className="flex justify-end">
                <div className="max-w-xl rounded-2xl bg-blue-600 px-4 py-2.5 text-sm text-white shadow-sm">
                  {msg.text}
                </div>
              </div>
            ) : (
              /* Answer — left-aligned */
              <div key={msg.id} className="flex justify-start">
                <div className="max-w-3xl w-full">
                  {msg.errorText ? (
                    <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
                      {msg.errorText}
                    </div>
                  ) : (
                    <div className="rounded-2xl border border-gray-100 bg-white p-5 shadow-sm">
                      {/* Answer text */}
                      <p className="whitespace-pre-wrap text-sm leading-relaxed text-gray-800">
                        {msg.text}
                      </p>

                      {/* Sources */}
                      {msg.response && msg.response.sources.length > 0 && (
                        <div className="mt-4 border-t border-gray-100 pt-4">
                          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
                            Sources ({msg.response.sources.length})
                          </p>
                          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                            {msg.response.sources.map((src) => (
                              <div
                                key={src.document_id}
                                className="flex items-start gap-2 rounded-lg border border-gray-100 bg-gray-50 p-2.5 text-xs"
                                title={src.excerpt}
                              >
                                <FileText className="mt-0.5 h-3.5 w-3.5 shrink-0 text-blue-400" />
                                <div className="min-w-0">
                                  <p className="truncate font-semibold text-gray-700">
                                    {src.title}
                                  </p>
                                  <p className="mt-0.5 line-clamp-2 text-gray-500">
                                    {src.excerpt.slice(0, 110)}…
                                  </p>
                                  <p className="mt-1 text-blue-400">
                                    Score: {src.score.toFixed(3)}
                                  </p>
                                </div>
                              </div>
                            ))}
                          </div>
                          <p className="mt-2 text-right text-xs text-gray-400">
                            {msg.response.latency_ms} ms
                          </p>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ),
          )}

          {/* Loading bubble */}
          {isLoading && (
            <div className="flex justify-start">
              <div className="rounded-2xl border border-gray-100 bg-white px-5 py-4 shadow-sm">
                <LoadingSpinner size="sm" label="Searching knowledge base and generating answer…" />
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      )}

      {/* Input bar — always at bottom */}
      <div className="mt-4 border-t border-gray-200 bg-gray-50 pt-4">
        <div className="flex items-end gap-3">
          <textarea
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about policies, reports, compliance, HR guidelines… (Enter to send, Shift+Enter for new line)"
            rows={2}
            disabled={isLoading}
            className="flex-1 resize-none rounded-xl border border-gray-200 bg-white px-4 py-3 text-sm shadow-sm placeholder:text-gray-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-50"
          />
          <button
            onClick={() => void submit()}
            disabled={isLoading || !query.trim()}
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-blue-600 text-white shadow-sm transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
            aria-label="Send"
          >
            <Send className="h-4 w-4" />
          </button>
        </div>
        <p className="mt-1.5 text-center text-xs text-gray-400">
          Powered by Azure AI Search + GPT-4o · Shift+Enter for new line
        </p>
      </div>
    </div>
  )
}
