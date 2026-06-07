import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import type { Role } from '../../contexts/AuthContext'
import Sidebar from './Sidebar'
import TopBar from './TopBar'
import LoadingSpinner from '../ui/LoadingSpinner'

interface Props {
  minRole?: Role
}

export default function AppLayout({ minRole = 'Viewer' }: Props) {
  const { isAuthenticated, isLoading, hasRole } = useAuth()

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-gray-50">
        <LoadingSpinner size="lg" label="Loading…" />
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  if (!hasRole(minRole)) {
    return (
      <div className="flex h-screen items-center justify-center bg-gray-50">
        <div className="max-w-sm text-center">
          <p className="text-5xl">🔒</p>
          <p className="mt-4 text-2xl font-bold text-gray-800">Access Denied</p>
          <p className="mt-2 text-sm text-gray-500">
            You need the <strong>{minRole}</strong> role (or higher) to access this page.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-screen overflow-hidden bg-gray-50">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <TopBar />
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
