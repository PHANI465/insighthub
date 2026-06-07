import React, { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { login as apiLogin, logout as apiLogout } from '../api/auth'
import type { LoginRequest } from '../types/api'

export type Role = 'Admin' | 'Analyst' | 'Viewer'

const ROLE_LEVELS: Record<Role, number> = {
  Viewer: 1,
  Analyst: 2,
  Admin: 3,
}

export interface AuthUser {
  username: string
  role: Role
  access_token: string
}

// Sentinel token used to identify the guest / demo-mode session.
// No actual network requests are made when this token is active.
export const GUEST_TOKEN = 'demo-mode'

interface AuthContextValue {
  user: AuthUser | null
  isAuthenticated: boolean
  /** True when the session is a guest demo (no live backend calls). */
  isGuest: boolean
  isLoading: boolean
  login: (credentials: LoginRequest) => Promise<void>
  /** Skip the backend entirely and enter guest demo mode. */
  loginAsGuest: () => void
  logout: () => void
  hasRole: (minimum: Role) => boolean
}

const AuthContext = createContext<AuthContextValue | null>(null)

const STORAGE_KEY = 'insighthub_user'

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  // Restore session from localStorage on mount
  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY)
      if (stored) {
        const parsed = JSON.parse(stored) as AuthUser
        setUser(parsed)
        localStorage.setItem('insighthub_token', parsed.access_token)
      }
    } catch {
      localStorage.removeItem(STORAGE_KEY)
      localStorage.removeItem('insighthub_token')
    } finally {
      setIsLoading(false)
    }
  }, [])

  const login = useCallback(async (credentials: LoginRequest) => {
    const tokenResponse = await apiLogin(credentials)
    const authUser: AuthUser = {
      username: credentials.username,
      role: tokenResponse.role as Role,
      access_token: tokenResponse.access_token,
    }
    setUser(authUser)
    localStorage.setItem('insighthub_token', tokenResponse.access_token)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(authUser))
  }, [])

  /**
   * Enter guest / demo mode without contacting the backend.
   * Grants Analyst role so all pages are navigable (Search, Customers, Support).
   * Pages detect the demo-mode token and render static sample data instead.
   */
  const loginAsGuest = useCallback(() => {
    const guestUser: AuthUser = {
      username: 'guest',
      role: 'Analyst',
      access_token: GUEST_TOKEN,
    }
    setUser(guestUser)
    localStorage.setItem('insighthub_token', GUEST_TOKEN)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(guestUser))
  }, [])

  const logout = useCallback(() => {
    apiLogout()
    setUser(null)
  }, [])

  const hasRole = useCallback(
    (minimum: Role): boolean => {
      if (!user) return false
      return (ROLE_LEVELS[user.role] ?? 0) >= (ROLE_LEVELS[minimum] ?? 99)
    },
    [user],
  )

  const isGuest = user?.access_token === GUEST_TOKEN

  return (
    <AuthContext.Provider
      value={{ user, isAuthenticated: user !== null, isGuest, isLoading, login, loginAsGuest, logout, hasRole }}
    >
      {children}
    </AuthContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
