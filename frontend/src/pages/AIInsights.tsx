import { useEffect, useState, useCallback } from 'react'
import {
  Lightbulb,
  RefreshCw,
  TrendingUp,
  Users,
  Headphones,
  Megaphone,
  CheckCircle,
  ChevronDown,
  ChevronUp,
} from 'lucide-react'
import { getInsights, getInsightDetail, generateInsights } from '../api/insights'
import type { InsightRow, InsightDetail, GenerateInsightResponse } from '../types/api'
import LoadingSpinner from '../components/ui/LoadingSpinner'
import ErrorBanner from '../components/ui/ErrorBanner'
import Badge from '../components/ui/Badge'
import { useAuth } from '../contexts/AuthContext'
import { formatDate } from '../utils/format'
import axios from 'axios'

type BadgeVariant = 'blue' | 'green' | 'amber' | 'red' | 'gray' | 'violet'

interface CategoryMeta {
  icon: React.ElementType
  borderColor: string
  bgColor: string
  badge: BadgeVariant
}

const CATEGORY_META: Record<string, CategoryMeta> = {
  Sales:     { icon: TrendingUp, borderColor: 'border-blue-200',   bgColor: 'bg-blue-50',    badge: 'blue'   },
  Customers: { icon: Users,      borderColor: 'border-violet-200', bgColor: 'bg-violet-50',  badge: 'violet' },
  Support:   { icon: Headphones, borderColor: 'border-amber-200',  bgColor: 'bg-amber-50',   badge: 'amber'  },
  Campaigns: { icon: Megaphone,  borderColor: 'border-emerald-200', bgColor: 'bg-emerald-50', badge: 'green'  },
}

const CATEGORIES = ['Sales', 'Customers', 'Support', 'Campaigns']

// ── Single insight card with lazy-loaded detail ───────────────────────────────

interface InsightCardProps {
  insight: InsightRow
}

function InsightCard({ insight }: InsightCardProps) {
  const meta = CATEGORY_META[insight.category] ?? {
    icon: Lightbulb,
    borderColor: 'border-gray-200',
    bgColor: 'bg-gray-50',
    badge: 'gray' as BadgeVariant,
  }
  const Icon = meta.icon

  const [expanded, setExpanded] = useState(false)
  const [detail, setDetail] = useState<InsightDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const loadDetail = useCallback(async () => {
    if (detail) return
    setDetailLoading(true)
    try {
      const d = await getInsightDetail(insight.insight_id)
      setDetail(d)
    } catch {
      // Silently ignore — user can retry by toggling
    } finally {
      setDetailLoading(false)
    }
  }, [detail, insight.insight_id])

  function toggle() {
    if (!expanded) void loadDetail()
    setExpanded((v) => !v)
  }

  const structured = detail?.structured_json as
    | {
        key_findings?: string[]
        recommendations?: string[]
        risk_flags?: string[]
      }
    | undefined

  const confidencePct =
    insight.confidence_score !== null && insight.confidence_score !== undefined
      ? Math.round(insight.confidence_score * 100)
      : null

  return (
    <div
      className={`rounded-xl border p-5 ${meta.borderColor} ${meta.bgColor} space-y-3`}
    >
      {/* Header row */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <Icon className="h-5 w-5 shrink-0 text-gray-600" />
          <h3 className="text-sm font-semibold leading-snug text-gray-900">{insight.title}</h3>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <Badge label={insight.category} variant={meta.badge} />
          {confidencePct !== null && (
            <span className="text-xs text-gray-400">{confidencePct}% confidence</span>
          )}
        </div>
      </div>

      {/* Period */}
      <p className="text-xs text-gray-400">
        Period: {insight.period_start ?? '—'} – {insight.period_end ?? '—'}
        {' · '}Generated {formatDate(insight.generated_at)}
      </p>

      {/* Narrative */}
      <p className="text-sm leading-relaxed text-gray-700">{insight.narrative}</p>

      {/* Expand/collapse detail */}
      <button
        onClick={toggle}
        className="flex items-center gap-1 text-xs font-medium text-gray-500 hover:text-gray-800"
      >
        {expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
        {expanded ? 'Hide' : 'Show'} key findings & recommendations
      </button>

      {expanded && (
        <div className="space-y-3 border-t border-gray-200/70 pt-3">
          {detailLoading ? (
            <LoadingSpinner size="sm" label="Loading detail…" />
          ) : detail ? (
            <>
              {structured?.key_findings && structured.key_findings.length > 0 && (
                <div>
                  <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-500">
                    Key Findings
                  </p>
                  <ul className="space-y-1">
                    {structured.key_findings.map((f, i) => (
                      <li key={i} className="flex items-start gap-2 text-xs text-gray-700">
                        <span className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-blue-400" />
                        {f}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {structured?.recommendations && structured.recommendations.length > 0 && (
                <div>
                  <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-500">
                    Recommendations
                  </p>
                  <ul className="space-y-1">
                    {structured.recommendations.map((r, i) => (
                      <li key={i} className="flex items-start gap-2 text-xs text-gray-700">
                        <span className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400" />
                        {r}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {structured?.risk_flags && structured.risk_flags.length > 0 && (
                <div>
                  <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-500">
                    Risk Flags
                  </p>
                  <ul className="space-y-1">
                    {structured.risk_flags.map((r, i) => (
                      <li key={i} className="flex items-start gap-2 text-xs text-amber-700">
                        <span className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-400" />
                        {r}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <p className="text-right text-xs text-gray-400">
                {detail.prompt_tokens ?? 0} prompt + {detail.completion_tokens ?? 0} completion
                tokens · {detail.model_version}
              </p>
            </>
          ) : (
            <p className="text-xs text-gray-400">Could not load detail. Try again.</p>
          )}
        </div>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function AIInsights() {
  const { hasRole } = useAuth()
  const isAdmin = hasRole('Admin')

  const [insights, setInsights] = useState<InsightRow[]>([])
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState('')
  const [genResult, setGenResult] = useState<GenerateInsightResponse | null>(null)

  const fetchInsights = useCallback(() => {
    setLoading(true)
    setError('')
    return getInsights(50)
      .then(setInsights)
      .catch((err: unknown) => {
        if (axios.isAxiosError(err)) {
          const detail = (err.response?.data as { detail?: string } | undefined)?.detail
          setError(detail ?? 'Failed to load insights.')
        } else {
          setError('Failed to load insights.')
        }
      })
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    void fetchInsights()
  }, [fetchInsights])

  async function handleGenerate() {
    setGenerating(true)
    setError('')
    setGenResult(null)
    try {
      const result = await generateInsights({ categories: CATEGORIES, force_refresh: true })
      setGenResult(result)
      await getInsights(50).then(setInsights)
    } catch (err: unknown) {
      if (axios.isAxiosError(err)) {
        const detail = (err.response?.data as { detail?: string } | undefined)?.detail
        setError(detail ?? 'Insight generation failed.')
      } else {
        setError('Insight generation failed.')
      }
    } finally {
      setGenerating(false)
    }
  }

  // Pick the most recent insight per category (API returns newest first)
  const latestByCategory = new Map<string, InsightRow>()
  for (const ins of insights) {
    if (!latestByCategory.has(ins.category)) {
      latestByCategory.set(ins.category, ins)
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">AI-Generated Business Insights</h2>
          <p className="mt-0.5 text-sm text-gray-500">
            GPT-4o narratives grounded in live Azure SQL data
          </p>
        </div>
        {isAdmin && (
          <button
            onClick={() => void handleGenerate()}
            disabled={generating}
            className="flex shrink-0 items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {generating ? (
              <>
                <RefreshCw className="h-4 w-4 animate-spin" />
                Generating…
              </>
            ) : (
              <>
                <Lightbulb className="h-4 w-4" />
                Generate Insights
              </>
            )}
          </button>
        )}
      </div>

      {/* Generation progress */}
      {generating && (
        <div className="rounded-xl border border-blue-100 bg-blue-50 p-8 text-center">
          <LoadingSpinner size="lg" label="GPT-4o is analysing your business data…" />
          <p className="mt-4 text-sm text-blue-600">
            Querying Azure SQL → Building prompts → Calling GPT-4o → Storing insights
          </p>
          <p className="mt-1 text-xs text-blue-400">
            All 4 categories may take up to 60 seconds.
          </p>
        </div>
      )}

      {/* Generation result banner */}
      {genResult && !generating && (
        <div className="flex items-start gap-3 rounded-lg border border-emerald-200 bg-emerald-50 p-4">
          <CheckCircle className="mt-0.5 h-5 w-5 shrink-0 text-emerald-600" />
          <div className="text-sm text-emerald-700">
            Generated <strong>{genResult.generated_count}</strong> insight
            {genResult.generated_count !== 1 ? 's' : ''} for{' '}
            <strong>
              {genResult.period_start} → {genResult.period_end}
            </strong>
            . Tokens used:{' '}
            <strong>
              {(genResult.total_prompt_tokens + genResult.total_completion_tokens).toLocaleString()}
            </strong>
            .
            {genResult.failed_categories.length > 0 && (
              <span className="ml-1 text-amber-600">
                Failed: {genResult.failed_categories.join(', ')}.
              </span>
            )}
          </div>
        </div>
      )}

      {error && <ErrorBanner message={error} onDismiss={() => setError('')} />}

      {/* Insight cards */}
      {!generating && !loading && (
        <>
          {latestByCategory.size === 0 ? (
            /* Empty state */
            <div className="rounded-xl border-2 border-dashed border-gray-200 py-20 text-center">
              <Lightbulb className="mx-auto h-10 w-10 text-gray-300" />
              <p className="mt-3 text-sm font-medium text-gray-500">No insights generated yet</p>
              <p className="mt-1 text-xs text-gray-400">
                {isAdmin
                  ? 'Click "Generate Insights" to run the GPT-4o analysis pipeline.'
                  : 'An Admin needs to generate insights first.'}
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
              {CATEGORIES.map((cat) => {
                const insight = latestByCategory.get(cat)
                const meta = CATEGORY_META[cat]

                if (!insight) {
                  const Icon = meta?.icon ?? Lightbulb
                  return (
                    <div
                      key={cat}
                      className={`rounded-xl border p-5 ${meta?.borderColor ?? 'border-gray-200'} ${meta?.bgColor ?? 'bg-gray-50'}`}
                    >
                      <div className="flex items-center gap-2">
                        <Icon className="h-5 w-5 text-gray-400" />
                        <h3 className="text-sm font-semibold text-gray-500">{cat}</h3>
                      </div>
                      <p className="mt-2 text-sm italic text-gray-400">
                        No insight for this category yet.{' '}
                        {isAdmin
                          ? 'Click "Generate Insights".'
                          : 'Ask an Admin to generate.'}
                      </p>
                    </div>
                  )
                }

                return <InsightCard key={cat} insight={insight} />
              })}
            </div>
          )}
        </>
      )}

      {/* Loading skeleton while first fetch */}
      {loading && !generating && (
        <div className="flex h-64 items-center justify-center">
          <LoadingSpinner size="lg" label="Loading insights…" />
        </div>
      )}
    </div>
  )
}
