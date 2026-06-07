import { useEffect, useState } from 'react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ComposedChart,
  Line,
} from 'recharts'
import { Headphones, CheckCircle, Star, AlertTriangle } from 'lucide-react'
import KPICard from '../components/ui/KPICard'
import LoadingSpinner from '../components/ui/LoadingSpinner'
import ErrorBanner from '../components/ui/ErrorBanner'
import { getSupportMetrics } from '../api/metrics'
import { useAuth } from '../contexts/AuthContext'
import { GUEST_SUPPORT_METRICS } from '../lib/guestData'
import type { SupportMetricsRow } from '../types/api'
import { formatInt, formatPct } from '../utils/format'
import axios from 'axios'

interface CategoryRollup {
  category: string
  tickets: number
  resolved: number
  escalated: number
  resRate: number
  csat: number | null
}

function buildCategoryRollups(data: SupportMetricsRow[]): CategoryRollup[] {
  const map = new Map<
    string,
    { tickets: number; resolved: number; escalated: number; csats: number[] }
  >()

  for (const row of data) {
    const prev = map.get(row.category) ?? { tickets: 0, resolved: 0, escalated: 0, csats: [] }
    prev.tickets += row.total_tickets
    prev.resolved += row.resolved_tickets
    prev.escalated += row.escalated_tickets
    if (row.avg_csat !== null) prev.csats.push(row.avg_csat)
    map.set(row.category, prev)
  }

  return Array.from(map.entries()).map(([category, d]) => ({
    category,
    tickets: d.tickets,
    resolved: d.resolved,
    escalated: d.escalated,
    resRate: Math.round((d.resolved / Math.max(d.tickets, 1)) * 100),
    csat:
      d.csats.length > 0
        ? parseFloat((d.csats.reduce((a, b) => a + b, 0) / d.csats.length).toFixed(2))
        : null,
  }))
}

export default function SupportOperations() {
  const { isGuest } = useAuth()
  const [data, setData] = useState<SupportMetricsRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    if (isGuest) {
      setData(GUEST_SUPPORT_METRICS)
      setLoading(false)
      return
    }
    getSupportMetrics()
      .then(setData)
      .catch((err: unknown) => {
        if (axios.isAxiosError(err)) {
          const detail = (err.response?.data as { detail?: string } | undefined)?.detail
          setError(detail ?? 'Failed to load support data.')
        } else {
          setError('Failed to load support data.')
        }
      })
      .finally(() => setLoading(false))
  }, [isGuest])

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <LoadingSpinner size="lg" label="Loading support data…" />
      </div>
    )
  }

  if (error) return <ErrorBanner message={error} />

  // Aggregate totals
  let totalTickets = 0
  let totalResolved = 0
  let totalEscalated = 0
  const allCsats: number[] = []
  for (const row of data) {
    totalTickets += row.total_tickets
    totalResolved += row.resolved_tickets
    totalEscalated += row.escalated_tickets
    if (row.avg_csat !== null) allCsats.push(row.avg_csat)
  }
  const avgCSAT =
    allCsats.length > 0
      ? allCsats.reduce((a, b) => a + b, 0) / allCsats.length
      : null
  const resolutionRate = totalTickets > 0 ? (totalResolved / totalTickets) * 100 : 0
  const escalationRate = totalTickets > 0 ? (totalEscalated / totalTickets) * 100 : 0

  const catRollups = buildCategoryRollups(data)

  return (
    <div className="space-y-6">
      {/* KPI cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <KPICard
          title="Total Tickets"
          value={formatInt(totalTickets)}
          icon={<Headphones className="h-5 w-5 text-blue-600" />}
          accent="bg-blue-50"
        />
        <KPICard
          title="Resolution Rate"
          value={formatPct(resolutionRate)}
          subtitle={`${formatInt(totalResolved)} resolved`}
          icon={<CheckCircle className="h-5 w-5 text-emerald-600" />}
          accent="bg-emerald-50"
        />
        <KPICard
          title="Avg CSAT"
          value={avgCSAT !== null ? `${avgCSAT.toFixed(2)} / 5` : '—'}
          icon={<Star className="h-5 w-5 text-amber-500" />}
          accent="bg-amber-50"
        />
        <KPICard
          title="Escalation Rate"
          value={formatPct(escalationRate)}
          subtitle={`${formatInt(totalEscalated)} escalated`}
          icon={<AlertTriangle className="h-5 w-5 text-red-500" />}
          accent="bg-red-50"
        />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        {/* Ticket volume by category */}
        <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
          <h2 className="mb-4 text-base font-semibold text-gray-900">Tickets by Category</h2>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart
              data={catRollups}
              margin={{ top: 5, right: 10, left: 0, bottom: 50 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis
                dataKey="category"
                tick={{ fontSize: 11, fill: '#6b7280' }}
                tickLine={false}
                angle={-30}
                textAnchor="end"
              />
              <YAxis
                tick={{ fontSize: 11, fill: '#9ca3af' }}
                tickLine={false}
                axisLine={false}
              />
              <Tooltip
                contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e5e7eb' }}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="tickets"  name="Total"    fill="#3b82f6" radius={[4, 4, 0, 0]} />
              <Bar dataKey="resolved" name="Resolved" fill="#10b981" radius={[4, 4, 0, 0]} />
              <Bar dataKey="escalated" name="Escalated" fill="#ef4444" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Resolution rate + CSAT overlay */}
        <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
          <h2 className="mb-4 text-base font-semibold text-gray-900">
            Resolution Rate & CSAT by Category
          </h2>
          <ResponsiveContainer width="100%" height={280}>
            <ComposedChart
              data={catRollups}
              margin={{ top: 5, right: 10, left: 0, bottom: 50 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis
                dataKey="category"
                tick={{ fontSize: 11, fill: '#6b7280' }}
                tickLine={false}
                angle={-30}
                textAnchor="end"
              />
              <YAxis
                yAxisId="left"
                tick={{ fontSize: 11, fill: '#9ca3af' }}
                tickLine={false}
                axisLine={false}
                unit="%"
                domain={[0, 100]}
              />
              <YAxis
                yAxisId="right"
                orientation="right"
                tick={{ fontSize: 11, fill: '#9ca3af' }}
                tickLine={false}
                axisLine={false}
                domain={[0, 5]}
                tickFormatter={(v: number) => v.toFixed(1)}
              />
              <Tooltip
                contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e5e7eb' }}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar
                yAxisId="left"
                dataKey="resRate"
                name="Resolution %"
                fill="#6366f1"
                radius={[4, 4, 0, 0]}
              />
              <Line
                yAxisId="right"
                type="monotone"
                dataKey="csat"
                name="CSAT (0–5)"
                stroke="#f59e0b"
                strokeWidth={2}
                dot={{ r: 4, fill: '#f59e0b' }}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Detail table */}
      <div className="overflow-hidden rounded-xl border border-gray-100 bg-white shadow-sm">
        <div className="border-b border-gray-100 px-5 py-4">
          <h2 className="text-base font-semibold text-gray-900">Category Detail</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 text-left text-xs font-semibold uppercase tracking-wide text-gray-400">
                <th className="px-5 py-3">Category</th>
                <th className="px-5 py-3 text-right">Tickets</th>
                <th className="px-5 py-3 text-right">Resolved</th>
                <th className="px-5 py-3 text-right">Res Rate</th>
                <th className="px-5 py-3 text-right">Escalated</th>
                <th className="px-5 py-3 text-right">Avg CSAT</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {catRollups.map((r) => (
                <tr key={r.category} className="hover:bg-gray-50">
                  <td className="px-5 py-3 font-medium text-gray-900">{r.category}</td>
                  <td className="px-5 py-3 text-right text-gray-700">{formatInt(r.tickets)}</td>
                  <td className="px-5 py-3 text-right text-emerald-600">
                    {formatInt(r.resolved)}
                  </td>
                  <td className="px-5 py-3 text-right">
                    <span
                      className={
                        r.resRate >= 80
                          ? 'font-semibold text-emerald-600'
                          : r.resRate >= 60
                          ? 'font-semibold text-amber-500'
                          : 'font-semibold text-red-500'
                      }
                    >
                      {formatPct(r.resRate)}
                    </span>
                  </td>
                  <td className="px-5 py-3 text-right text-red-400">
                    {formatInt(r.escalated)}
                  </td>
                  <td className="px-5 py-3 text-right text-gray-700">
                    {r.csat !== null ? r.csat.toFixed(2) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
