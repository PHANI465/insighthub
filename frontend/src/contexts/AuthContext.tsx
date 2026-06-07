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

interface AuthContextValue {
  user: AuthUser | null
  isAuthenticated: boolean
  isLoading: boolean
  login: (credentials: LoginRequest) => Promise<void>
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

  return (
    <AuthContext.Provider
      value={{ user, isAuthenticated: user !== null, isLoading, login, logout, hasRole }}
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
