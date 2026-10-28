/**
 * AuthProvider component.
 *
 * Responsibilities:
 * - Restore session from localStorage on app start
 * - Re-validate the stored token against GET /auth/me on startup
 *   (catches expired tokens and deactivated accounts)
 * - Expose login, register, logout, hasRole to the component tree
 * - Persist token + user to localStorage on change
 */
import { useState, useEffect, useCallback, type ReactNode } from 'react'
import type { User, UserRole, LoginCredentials, RegisterPayload } from '../types'
import { authApi } from '../services/api'
import { AuthContext } from './authContextValue'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [token, setToken] = useState<string | null>(null)
  // isLoading=true while we verify the stored token on startup
  const [isLoading, setIsLoading] = useState(true)

  // ── Startup: restore + validate stored session ──────────────────────────
  useEffect(() => {
    async function restoreSession() {
      const storedToken = localStorage.getItem('bt_token')
      const storedUser = localStorage.getItem('bt_user')

      if (!storedToken) {
        setIsLoading(false)
        return
      }

      // Optimistic restore so the UI doesn't flash a login redirect
      if (storedUser) {
        try {
          setUser(JSON.parse(storedUser) as User)
          setToken(storedToken)
        } catch {
          // corrupted — clear below
        }
      }

      // Re-validate against the backend (catches expired/revoked tokens)
      try {
        const fresh = await authApi.me()
        setUser(fresh)
        setToken(storedToken)
        localStorage.setItem('bt_user', JSON.stringify(fresh))
      } catch {
        // Token is invalid or expired — clear everything
        localStorage.removeItem('bt_token')
        localStorage.removeItem('bt_user')
        setUser(null)
        setToken(null)
      } finally {
        setIsLoading(false)
      }
    }
    void restoreSession()
  }, []) // run once on mount

  // ── Persist to localStorage whenever state changes ───────────────────────
  useEffect(() => {
    if (user) localStorage.setItem('bt_user', JSON.stringify(user))
    else localStorage.removeItem('bt_user')
  }, [user])

  useEffect(() => {
    if (token) localStorage.setItem('bt_token', token)
    else localStorage.removeItem('bt_token')
  }, [token])

  // ── Auth actions ──────────────────────────────────────────────────────────
  const login = useCallback(async (creds: LoginCredentials) => {
    setIsLoading(true)
    try {
      const res = await authApi.login(creds)
      setToken(res.access_token)
      setUser(res.user)
    } finally {
      setIsLoading(false)
    }
  }, [])

  const register = useCallback(async (payload: RegisterPayload) => {
    setIsLoading(true)
    try {
      const res = await authApi.register(payload)
      setToken(res.access_token)
      setUser(res.user)
    } finally {
      setIsLoading(false)
    }
  }, [])

  const logout = useCallback(() => {
    authApi.logout()
    setUser(null)
    setToken(null)
  }, [])

  const hasRole = useCallback(
    (...roles: UserRole[]) => !!user && roles.includes(user.role),
    [user],
  )

  return (
    <AuthContext.Provider
      value={{ user, token, isAuthenticated: !!user, isLoading, login, register, logout, hasRole }}
    >
      {children}
    </AuthContext.Provider>
  )
}
