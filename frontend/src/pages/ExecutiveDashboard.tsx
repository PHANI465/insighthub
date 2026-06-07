import { useEffect, useState } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  BarChart,
  Bar,
} from 'recharts'
import { DollarSign, ShoppingCart, Users, Star, TrendingUp } from 'lucide-react'
import KPICard from '../components/ui/KPICard'
import LoadingSpinner from '../components/ui/LoadingSpinner'
import ErrorBanner from '../components/ui/ErrorBanner'
import { getKPISummary, getRevenueTrend, getCampaignROI } from '../api/metrics'
import { useAuth } from '../contexts/AuthContext'
import { GUEST_KPI, GUEST_REVENUE_TREND, GUEST_CAMPAIGNS } from '../lib/guestData'
import type { KPISummary, RevenueTrend, CampaignROIRow } from '../types/api'
import { formatCurrency, formatInt, formatPct } from '../utils/format'
import axios from 'axios'

export default function ExecutiveDashboard() {
  const { isGuest } = useAuth()

  const [kpi, setKpi] = useState<KPISummary | null>(null)
  const [trend, setTrend] = useState<RevenueTrend[]>([])
  const [campaigns, setCampaigns] = useState<CampaignROIRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    // Guest mode: load static data instantly, no network calls
    if (isGuest) {
      setKpi(GUEST_KPI)
      setTrend(GUEST_REVENUE_TREND)
      setCampaigns(GUEST_CAMPAIGNS)
      setLoading(false)
      return
    }

    setLoading(true)
    Promise.all([getKPISummary(), getRevenueTrend('month'), getCampaignROI(10)])
      .then(([kpiData, trendData, campData]) => {
        setKpi(kpiData)
        setTrend(trendData)
        setCampaigns(campData)
      })
      .catch((err: unknown) => {
        if (axios.isAxiosError(err)) {
          const detail = (err.response?.data as { detail?: string } | undefined)?.detail
          setError(detail ?? 'Failed to load dashboard data.')
        } else {
          setError('Failed to load dashboard data.')
        }
      })
      .finally(() => setLoading(false))
  }, [isGuest])

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <LoadingSpinner size="lg" label="Loading dashboard…" />
      </div>
    )
  }

  if (error) return <ErrorBanner message={error} />
  if (!kpi) return null

  // Last 24 months for chart
  const chartData = trend.slice(-24).map((r) => ({
    period: r.period,
    Revenue: Math.round(r.revenue),
    Profit: Math.round(r.gross_profit),
  }))

  // Top 8 campaigns for horizontal bar
  const campaignData = campaigns.slice(0, 8).map((c) => ({
    name: c.campaign_name.length > 22 ? `${c.campaign_name.slice(0, 22)}…` : c.campaign_name,
    ROI: Math.round(c.roi_pct),
  }))

  return (
    <div className="space-y-6">
      {/* KPI cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 xl:grid-cols-5">
        <KPICard
          title="Total Revenue"
          value={formatCurrency(kpi.total_revenue)}
          subtitle={kpi.period_label}
          icon={<DollarSign className="h-5 w-5 text-blue-600" />}
          accent="bg-blue-50"
        />
        <KPICard
          title="Total Orders"
          value={formatInt(kpi.total_orders)}
          subtitle={`AOV ${formatCurrency(kpi.avg_order_value)}`}
          icon={<ShoppingCart className="h-5 w-5 text-violet-600" />}
          accent="bg-violet-50"
        />
        <KPICard
          title="Customers"
          value={formatInt(kpi.total_customers)}
          icon={<Users className="h-5 w-5 text-emerald-600" />}
          accent="bg-emerald-50"
        />
        <KPICard
          title="Avg CSAT"
          value={kpi.avg_csat !== null ? `${kpi.avg_csat.toFixed(1)} / 5` : '—'}
          subtitle={`${formatInt(kpi.open_tickets)} open tickets`}
          icon={<Star className="h-5 w-5 text-amber-500" />}
          accent="bg-amber-50"
        />
        <KPICard
          title="Gross Margin"
          value={formatPct(kpi.gross_margin_pct)}
          subtitle={`Profit ${formatCurrency(kpi.gross_profit)}`}
          icon={<TrendingUp className="h-5 w-5 text-teal-600" />}
          accent="bg-teal-50"
        />
      </div>

      {/* Revenue trend + campaign ROI */}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        {/* Revenue line chart (spans 2/3 width on xl) */}
        <div className="col-span-1 rounded-xl border border-gray-100 bg-white p-5 shadow-sm xl:col-span-2">
          <h2 className="mb-4 text-base font-semibold text-gray-900">Revenue & Profit Trend</h2>
          {chartData.length > 0 ? (
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis
                  dataKey="period"
                  tick={{ fontSize: 11, fill: '#9ca3af' }}
                  tickLine={false}
                  interval="preserveStartEnd"
                />
                <YAxis
                  tick={{ fontSize: 11, fill: '#9ca3af' }}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v: number) => `$${(v / 1_000).toFixed(0)}K`}
                />
                <Tooltip
                  formatter={(value: number) => [formatCurrency(value)]}
                  contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e5e7eb' }}
                />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Line
                  type="monotone"
                  dataKey="Revenue"
                  stroke="#3b82f6"
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 4 }}
                />
                <Line
                  type="monotone"
                  dataKey="Profit"
                  stroke="#10b981"
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 4 }}
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <p className="flex h-64 items-center justify-center text-sm text-gray-400">
              No trend data available.
            </p>
          )}
        </div>

        {/* Campaign ROI horizontal bar */}
        <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
          <h2 className="mb-4 text-base font-semibold text-gray-900">Top Campaign ROI</h2>
          {campaignData.length > 0 ? (
            <ResponsiveContainer width="100%" height={280}>
              <BarChart
                data={campaignData}
                layout="vertical"
                margin={{ top: 0, right: 16, left: 0, bottom: 0 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" horizontal={false} />
                <XAxis
                  type="number"
                  tick={{ fontSize: 10, fill: '#9ca3af' }}
                  tickLine={false}
                  tickFormatter={(v: number) => `${v}%`}
                />
                <YAxis
                  type="category"
                  dataKey="name"
                  tick={{ fontSize: 10, fill: '#6b7280' }}
                  tickLine={false}
                  axisLine={false}
                  width={90}
                />
                <Tooltip
                  formatter={(v: number) => [`${v}%`, 'ROI']}
                  contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e5e7eb' }}
                />
                <Bar dataKey="ROI" fill="#3b82f6" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="flex h-64 items-center justify-center text-sm text-gray-400">
              No campaign data.
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
