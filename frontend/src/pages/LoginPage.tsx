import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import axios from 'axios'

export default function LoginPage() {
  const { login, loginAsGuest, isAuthenticated } = useAuth()
  const navigate = useNavigate()

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  if (isAuthenticated) {
    navigate('/dashboard', { replace: true })
    return null
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!username.trim() || !password) {
      setError('Username and password are required.')
      return
    }
    setError('')
    setLoading(true)
    try {
      await login({ username: username.trim(), password })
      navigate('/dashboard', { replace: true })
    } catch (err: unknown) {
      if (axios.isAxiosError(err)) {
        if (err.response?.status === 401) {
          setError('Invalid username or password.')
        } else if (err.code === 'ERR_NETWORK' || err.code === 'ECONNREFUSED') {
          setError('Cannot reach the backend. Is the FastAPI server running on port 8000?')
        } else {
          const detail = (err.response?.data as { detail?: string } | undefined)?.detail
          setError(detail ?? 'Login failed. Please try again.')
        }
      } else {
        setError('An unexpected error occurred.')
      }
    } finally {
      setLoading(false)
    }
  }

  function handleGuestLogin() {
    loginAsGuest()
    navigate('/dashboard', { replace: true })
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-slate-900 via-blue-950 to-slate-900">
      <div className="w-full max-w-md px-4">
        {/* Logo */}
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-blue-600 text-2xl font-bold text-white shadow-lg">
            IH
          </div>
          <h1 className="text-3xl font-bold text-white">InsightHub</h1>
          <p className="mt-1 text-sm text-slate-400">Business Analytics Platform</p>
        </div>

        {/* Demo Banner */}
        <div className="mb-4 rounded-xl border border-blue-400/30 bg-blue-500/10 px-4 py-3 text-center backdrop-blur-sm">
          <p className="text-sm text-blue-200">
            <span className="font-semibold">Portfolio demo.</span> The backend may be temporarily
            offline.{' '}
            <a
              href="https://github.com/Phani465/insighthub#screenshots"
              target="_blank"
              rel="noopener noreferrer"
              className="underline underline-offset-2 hover:text-white"
            >
              Screenshots of all features
            </a>{' '}
            are available in the README.
          </p>
        </div>

        {/* Card */}
        <div className="rounded-2xl bg-white p-8 shadow-2xl">
          <h2 className="mb-6 text-xl font-semibold text-gray-900">Sign in</h2>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="username" className="block text-sm font-medium text-gray-700">
                Username
              </label>
              <input
                id="username"
                type="text"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                disabled={loading}
                placeholder="admin"
                className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm shadow-sm placeholder:text-gray-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-60"
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-sm font-medium text-gray-700">
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={loading}
                placeholder="••••••••"
                className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-60"
              />
            </div>

            {error && (
              <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="mt-2 w-full rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {loading ? 'Signing in…' : 'Sign in'}
            </button>
          </form>

          {/* Demo credentials hint */}
          <div className="mt-6 rounded-lg bg-gray-50 p-3">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
              Demo credentials
            </p>
            <div className="space-y-1.5 text-xs text-gray-600">
              <div className="flex items-center justify-between">
                <span>
                  <code className="font-semibold text-gray-800">admin</code> /
                  InsightHub@Admin2024!
                </span>
                <span className="rounded bg-blue-100 px-1.5 py-0.5 text-blue-600">Admin</span>
              </div>
              <div className="flex items-center justify-between">
                <span>
                  <code className="font-semibold text-gray-800">analyst</code> /
                  InsightHub@Analyst2024!
                </span>
                <span className="rounded bg-violet-100 px-1.5 py-0.5 text-violet-600">
                  Analyst
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span>
                  <code className="font-semibold text-gray-800">viewer</code> /
                  InsightHub@Viewer2024!
                </span>
                <span className="rounded bg-gray-100 px-1.5 py-0.5 text-gray-500">Viewer</span>
              </div>
            </div>
          </div>
        </div>

        {/* Guest / offline access — lives outside the white card */}
        <div className="mt-4 text-center">
          <div className="mb-3 flex items-center gap-3">
            <hr className="flex-1 border-slate-600/50" />
            <span className="text-xs text-slate-500">or</span>
            <hr className="flex-1 border-slate-600/50" />
          </div>
          <button
            type="button"
            onClick={handleGuestLogin}
            className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm font-medium text-slate-300 backdrop-blur-sm transition-colors hover:bg-white/10 hover:text-white"
          >
            Explore as Guest
            <span className="ml-2 text-xs font-normal opacity-60">(sample data · no backend needed)</span>
          </button>
        </div>
      </div>
    </div>
  )
}
