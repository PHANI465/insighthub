import { Link, useLocation } from 'react-router-dom'
import {
  LayoutDashboard,
  Users,
  Headphones,
  Search,
  Lightbulb,
  LogOut,
} from 'lucide-react'
import { useAuth } from '../../contexts/AuthContext'
import type { Role } from '../../contexts/AuthContext'

interface NavItem {
  to: string
  label: string
  icon: React.ElementType
  minRole: Role
}

const NAV: NavItem[] = [
  { to: '/dashboard', label: 'Dashboard',         icon: LayoutDashboard, minRole: 'Viewer'  },
  { to: '/customers', label: 'Customer Analytics', icon: Users,           minRole: 'Analyst' },
  { to: '/support',   label: 'Support Ops',        icon: Headphones,      minRole: 'Analyst' },
  { to: '/search',    label: 'Knowledge Search',   icon: Search,          minRole: 'Analyst' },
  { to: '/insights',  label: 'AI Insights',        icon: Lightbulb,       minRole: 'Viewer'  },
]

export default function Sidebar() {
  const { pathname } = useLocation()
  const { hasRole, logout, user } = useAuth()

  return (
    <aside className="flex h-full w-60 shrink-0 flex-col bg-slate-900 text-white">
      {/* Brand */}
      <div className="flex h-16 items-center gap-2.5 border-b border-slate-700/60 px-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 text-sm font-bold tracking-tight">
          IH
        </div>
        <span className="text-base font-semibold tracking-tight">InsightHub</span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-4">
        {NAV.map(({ to, label, icon: Icon, minRole }) => {
          if (!hasRole(minRole)) return null
          const active = pathname === to || pathname.startsWith(`${to}/`)
          return (
            <Link
              key={to}
              to={to}
              className={`mx-2 mb-0.5 flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                active
                  ? 'bg-blue-600 text-white'
                  : 'text-slate-300 hover:bg-slate-800 hover:text-white'
              }`}
            >
              <Icon className="h-4 w-4 shrink-0" />
              {label}
            </Link>
          )
        })}
      </nav>

      {/* User strip */}
      <div className="border-t border-slate-700/60 p-4">
        <div className="mb-3 flex items-center gap-2.5">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-700 text-xs font-bold uppercase">
            {(user?.username ?? '?')[0]}
          </div>
          <div className="min-w-0">
            <p className="truncate text-sm font-medium leading-tight">{user?.username}</p>
            <p className="text-xs leading-tight text-slate-400">{user?.role}</p>
          </div>
        </div>
        <button
          onClick={logout}
          className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-slate-400 transition-colors hover:bg-slate-800 hover:text-white"
        >
          <LogOut className="h-4 w-4 shrink-0" />
          Sign out
        </button>
      </div>
    </aside>
  )
}
