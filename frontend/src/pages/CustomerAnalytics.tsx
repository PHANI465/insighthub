import { useEffect, useState } from 'react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from 'recharts'
import LoadingSpinner from '../components/ui/LoadingSpinner'
import ErrorBanner from '../components/ui/ErrorBanner'
import { getCustomerSegments } from '../api/metrics'
import { useAuth } from '../contexts/AuthContext'
import { GUEST_CUSTOMER_SEGMENTS } from '../lib/guestData'
import type { CustomerSegmentStat } from '../types/api'
import { formatCurrency, formatInt, formatPct } from '../utils/format'
import axios from 'axios'

const SEGMENT_COLORS: Record<string, string> = {
  Platinum: '#8b5cf6',
  Gold:     '#f59e0b',
  Silver:   '#94a3b8',
  Bronze:   '#d97706',
}
const FALLBACK_COLOR = '#3b82f6'

// Recharts pie label helper
interface PieLabelProps {
  cx: number
  cy: number
  midAngle: number
  innerRadius: number
  outerRadius: number
  percent: number
  name: string
}

const RADIAN = Math.PI / 180
function PieLabel({ cx, cy, midAngle, innerRadius, outerRadius, percent, name }: PieLabelProps) {
  if (percent < 0.05) return null
  const radius = innerRadius + (outerRadius - innerRadius) * 0.5
  const x = cx + radius * Math.cos(-midAngle * RADIAN)
  const y = cy + radius * Math.sin(-midAngle * RADIAN)
  return (
    <text
      x={x}
      y={y}
      fill="white"
      textAnchor="middle"
      dominantBaseline="central"
      fontSize={11}
      fontWeight={600}
    >
      {`${name}\n${(percent * 100).toFixed(0)}%`}
    </text>
  )
}

export default function CustomerAnalytics() {
  const { isGuest } = useAuth()
  const [segments, setSegments] = useState<CustomerSegmentStat[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    if (isGuest) {
      setSegments(GUEST_CUSTOMER_SEGMENTS)
      setLoading(false)
      return
    }
    getCustomerSegments()
      .then(setSegments)
      .catch((err: unknown) => {
        if (axios.isAxiosError(err)) {
          const detail = (err.response?.data as { detail?: string } | undefined)?.detail
          setError(detail ?? 'Failed to load customer data.')
        } else {
          setError('Failed to load customer data.')
        }
      })
      .finally(() => setLoading(false))
  }, [isGuest])

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <LoadingSpinner size="lg" label="Loading customer data…" />
      </div>
    )
  }

  if (error) return <ErrorBanner message={error} />

  const totalCustomers = segments.reduce((s, r) => s + r.customer_count, 0)
  const totalRevenue = segments.reduce((s, r) => s + r.total_revenue, 0)

  const pieData = segments.map((r) => ({
    name: r.segment,
    value: r.customer_count,
    fill: SEGMENT_COLORS[r.segment] ?? FALLBACK_COLOR,
  }))

  const revenueBarData = segments.map((r) => ({
    segment: r.segment,
    Revenue: Math.round(r.total_revenue),
    fill: SEGMENT_COLORS[r.segment] ?? FALLBACK_COLOR,
  }))

  return (
    <div className="space-y-6">
      {/* Summary table */}
      <div className="overflow-hidden rounded-xl border border-gray-100 bg-white shadow-sm">
        <div className="border-b border-gray-100 px-5 py-4">
          <h2 className="text-base font-semibold text-gray-900">
            Customer Segments —{' '}
            <span className="font-normal text-gray-500">{formatInt(totalCustomers)} total</span>
          </h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 text-left text-xs font-semibold uppercase tracking-wide text-gray-400">
                <th className="px-5 py-3">Segment</th>
                <th className="px-5 py-3 text-right">Customers</th>
                <th className="px-5 py-3 text-right">Revenue</th>
                <th className="px-5 py-3 text-right">Rev %</th>
                <th className="px-5 py-3 text-right">Avg LTV</th>
                <th className="px-5 py-3 text-right">Avg Order</th>
                <th className="px-5 py-3 text-right">Inactive</th>
                <th className="px-5 py-3 text-right">Churn %</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {segments.map((r) => (
                <tr key={r.segment} className="hover:bg-gray-50">
                  <td className="px-5 py-3 font-medium text-gray-900">
                    <span
                      className="mr-2 inline-block h-2.5 w-2.5 rounded-full"
                      style={{ background: SEGMENT_COLORS[r.segment] ?? FALLBACK_COLOR }}
                    />
                    {r.segment}
                  </td>
                  <td className="px-5 py-3 text-right text-gray-700">
                    {formatInt(r.customer_count)}
                  </td>
                  <td className="px-5 py-3 text-right text-gray-700">
                    {formatCurrency(r.total_revenue)}
                  </td>
                  <td className="px-5 py-3 text-right text-gray-500">
                    {formatPct((r.total_revenue / Math.max(totalRevenue, 1)) * 100)}
                  </td>
                  <td className="px-5 py-3 text-right text-gray-700">
                    {formatCurrency(r.avg_ltv)}
                  </td>
                  <td className="px-5 py-3 text-right text-gray-700">
                    {formatCurrency(r.avg_order_value)}
                  </td>
                  <td className="px-5 py-3 text-right text-red-400">
                    {formatInt(r.churn_risk_count)}
                  </td>
                  <td className="px-5 py-3 text-right text-red-400">
                    {formatPct((r.churn_risk_count / Math.max(r.customer_count, 1)) * 100)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        {/* Revenue by segment */}
        <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
          <h2 className="mb-4 text-base font-semibold text-gray-900">Revenue by Segment</h2>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart
              data={revenueBarData}
              margin={{ top: 5, right: 10, left: 0, bottom: 5 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis
                dataKey="segment"
                tick={{ fontSize: 12, fill: '#6b7280' }}
                tickLine={false}
              />
              <YAxis
                tick={{ fontSize: 11, fill: '#9ca3af' }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v: number) => `$${(v / 1_000_000).toFixed(1)}M`}
              />
              <Tooltip
                formatter={(v: number) => [formatCurrency(v), 'Revenue']}
                contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e5e7eb' }}
              />
              <Bar dataKey="Revenue" radius={[6, 6, 0, 0]}>
                {revenueBarData.map((entry) => (
                  <Cell key={entry.segment} fill={entry.fill} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Customer distribution pie */}
        <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
          <h2 className="mb-4 text-base font-semibold text-gray-900">Customer Distribution</h2>
          {pieData.length > 0 ? (
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={55}
                  outerRadius={105}
                  paddingAngle={2}
                  dataKey="value"
                  labelLine={false}
                  label={PieLabel}
                >
                  {pieData.map((entry) => (
                    <Cell key={entry.name} fill={entry.fill} />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(v: number) => [formatInt(v), 'Customers']}
                  contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e5e7eb' }}
                />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <p className="flex h-60 items-center justify-center text-sm text-gray-400">
              No segment data.
            </p>
          )}

          {/* Legend */}
          <div className="mt-3 flex flex-wrap justify-center gap-3">
            {pieData.map((d) => (
              <div key={d.name} className="flex items-center gap-1.5 text-xs text-gray-600">
                <span
                  className="inline-block h-2.5 w-2.5 rounded-full"
                  style={{ background: d.fill }}
                />
                {d.name}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
