import type { ReactNode } from 'react'

interface Props {
  title: string
  value: string
  subtitle?: string
  /** Positive = up, negative = down, undefined = no trend indicator */
  trend?: number
  icon?: ReactNode
  /** Tailwind bg class for the icon chip */
  accent?: string
}

export default function KPICard({ title, value, subtitle, trend, icon, accent = 'bg-blue-50' }: Props) {
  const trendColor = trend === undefined ? '' : trend >= 0 ? 'text-emerald-600' : 'text-red-500'
  const trendArrow = trend === undefined ? '' : trend >= 0 ? '↑' : '↓'

  return (
    <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-gray-500">{title}</p>
          <p className="mt-1 text-2xl font-bold tracking-tight text-gray-900">{value}</p>
          {subtitle && <p className="mt-0.5 text-xs text-gray-400">{subtitle}</p>}
          {trend !== undefined && (
            <p className={`mt-1 text-xs font-semibold ${trendColor}`}>
              {trendArrow} {Math.abs(trend).toFixed(1)}% vs prior period
            </p>
          )}
        </div>
        {icon && (
          <div
            className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${accent}`}
          >
            {icon}
          </div>
        )}
      </div>
    </div>
  )
}
