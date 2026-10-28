/**
 * Route guards for client-side navigation.
 *
 * IMPORTANT: These are UX guards only — they redirect unauthenticated or
 * unauthorised users to the right page. Real security is enforced by the
 * backend API (Bearer JWT + role checks). Never treat these as a security
 * boundary.
 */
import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/useAuth'
import type { UserRole } from '../types'
import { Spinner } from './ui'

interface ProtectedRouteProps {
  children: ReactNode
  /** If provided, only these roles may access the route. Others see 403 page. */
  roles?: UserRole[]
}

/**
 * Wraps a route that requires authentication.
 * - Not authenticated → /login (preserves intended destination in state)
 * - Authenticated but wrong role → /forbidden
 */
export function ProtectedRoute({ children, roles }: ProtectedRouteProps) {
  const { isAuthenticated, user, isLoading } = useAuth()
  const location = useLocation()

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Spinner size="lg" />
      </div>
    )
  }

  if (!isAuthenticated || !user) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  if (roles && !roles.includes(user.role)) {
    return <Navigate to="/forbidden" replace />
  }

  return <>{children}</>
}

/**
 * Wraps a route that should be inaccessible once authenticated.
 * - Authenticated → /dashboard
 */
export function PublicOnlyRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth()

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Spinner size="lg" />
      </div>
    )
  }

  if (isAuthenticated) {
    return <Navigate to="/dashboard" replace />
  }

  return <>{children}</>
}
