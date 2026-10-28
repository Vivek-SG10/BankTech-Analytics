import { Link } from 'react-router-dom'
import { useAuth } from '../context/useAuth'

export default function ForbiddenPage() {
  const { user, isAuthenticated } = useAuth()

  return (
    <div className="min-h-[calc(100vh-4rem)] flex items-center justify-center bg-slate-50 px-4">
      <div className="text-center max-w-md">
        <div className="text-6xl mb-6">🔒</div>
        <h1 className="text-3xl font-bold text-slate-900 mb-3">Access Denied</h1>
        <p className="text-slate-600 mb-2">
          You don&apos;t have permission to view this page.
        </p>
        {user && (
          <p className="text-sm text-slate-500 mb-8">
            Your role is <span className="font-semibold text-slate-700">{user.role}</span>.
            Contact an administrator if you believe this is an error.
          </p>
        )}
        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          {isAuthenticated ? (
            <Link
              to="/dashboard"
              className="px-6 py-2.5 rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700 transition"
            >
              Go to Dashboard
            </Link>
          ) : (
            <Link
              to="/login"
              className="px-6 py-2.5 rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700 transition"
            >
              Sign in
            </Link>
          )}
          <Link
            to="/"
            className="px-6 py-2.5 rounded-lg border border-slate-300 text-slate-700 font-medium hover:bg-slate-50 transition"
          >
            Home
          </Link>
        </div>
      </div>
    </div>
  )
}
