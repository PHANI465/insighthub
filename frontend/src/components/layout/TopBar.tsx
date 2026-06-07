import { useLocation } from 'react-router-dom'

const PAGE_TITLES: Record<string, string> = {
  '/dashboard': 'Executive Dashboard',
  '/customers': 'Customer Analytics',
  '/support':   'Support Operations',
  '/search':    'Knowledge Search',
  '/insights':  'AI Insights',
}

export default function TopBar() {
  const { pathname } = useLocation()
  const title = PAGE_TITLES[pathname] ?? 'InsightHub'

  return (
    <header className="flex h-16 shrink-0 items-center border-b border-gray-200 bg-white px-6">
      <h1 className="text-lg font-semibold text-gray-900">{title}</h1>
    </header>
  )
}
