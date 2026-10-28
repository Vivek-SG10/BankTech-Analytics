import { useState } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/useAuth'
import { Button, Input, Alert } from '../components/ui'
import type { UserRole } from '../types'

/** Role → default landing page after login. */
function dashboardFor(role: UserRole): string {
  switch (role) {
    case 'admin':
    case 'researcher':
      return '/analytics'
    case 'manager':
    case 'employee':
      return '/dashboard'
    case 'customer':
    default:
      return '/survey'
  }
}

export default function LoginPage() {
  const { login, user, isLoading } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const [email, setEmail]       = useState('')
  const [password, setPassword] = useState('')
  const [error, setError]       = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<{ email?: string; password?: string }>({})

  function validate(): boolean {
    const errs: typeof fieldErrors = {}
    if (!email) errs.email = 'Email is required.'
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) errs.email = 'Enter a valid email address.'
    if (!password) errs.password = 'Password is required.'
    setFieldErrors(errs)
    return Object.keys(errs).length === 0
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    if (!validate()) return
    try {
      await login({ email, password })
      // Redirect to intended destination (from ProtectedRoute state) or role default
      const from = (location.state as { from?: Location })?.from?.pathname
      const dest = from && from !== '/login' ? from : dashboardFor(user?.role ?? 'customer')
      navigate(dest, { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed. Please try again.')
    }
  }

  return (
    <div className="min-h-[calc(100vh-4rem)] flex items-center justify-center bg-slate-50 px-4 py-12">
      <div className="w-full max-w-md">
        <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-8">
          <div className="text-center mb-8">
            <div className="mx-auto mb-4 h-12 w-12 rounded-xl bg-gradient-to-br from-blue-700 to-blue-500 flex items-center justify-center text-white font-bold text-xl shadow">
              B
            </div>
            <h1 className="text-2xl font-bold text-slate-900">Welcome back</h1>
            <p className="text-sm text-slate-500 mt-1">Sign in to your research account</p>
          </div>

          {error && (
            <div className="mb-6">
              <Alert type="error">{error}</Alert>
            </div>
          )}

          <form onSubmit={handleSubmit} noValidate className="space-y-5">
            <Input
              label="Email address"
              type="email"
              id="login-email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="you@example.com"
              error={fieldErrors.email}
              autoComplete="email"
              required
            />
            <Input
              label="Password"
              type="password"
              id="login-password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="••••••••"
              error={fieldErrors.password}
              autoComplete="current-password"
              required
            />

            <Button
              type="submit"
              variant="primary"
              size="lg"
              isLoading={isLoading}
              className="w-full bg-blue-600 hover:bg-blue-700 border-blue-600 hover:border-blue-700"
            >
              Sign in
            </Button>
          </form>

          <p className="mt-6 text-center text-sm text-slate-600">
            Don&apos;t have an account?{' '}
            <Link to="/register" className="font-medium text-blue-600 hover:text-blue-700">
              Register to participate
            </Link>
          </p>

          {/* Dev demo accounts hint */}
          <details className="mt-4">
            <summary className="cursor-pointer text-xs text-slate-400 text-center hover:text-slate-600 select-none">
              🔑 Demo accounts (dev only)
            </summary>
            <div className="mt-3 p-3 rounded-lg bg-slate-50 border border-slate-200 space-y-1 text-xs text-slate-600 font-mono">
              {[
                ['admin@banktech.dev',      'Admin'],
                ['researcher@banktech.dev', 'Researcher'],
                ['manager@banktech.dev',    'Manager'],
                ['employee@banktech.dev',   'Employee'],
                ['customer@banktech.dev',   'Customer'],
              ].map(([emailAddr, role]) => (
                <div key={emailAddr} className="flex justify-between items-center gap-3">
                  <button
                    type="button"
                    className="text-blue-600 hover:underline text-left"
                    onClick={() => { setEmail(emailAddr); setPassword('Demo1234!') }}
                  >
                    {emailAddr}
                  </button>
                  <span className="text-slate-400 shrink-0">{role}</span>
                </div>
              ))}
              <p className="text-slate-400 pt-1">Password: Demo1234! — click to fill</p>
            </div>
          </details>

          <div className="mt-4 p-3 rounded-lg bg-amber-50 border border-amber-200">
            <p className="text-xs text-amber-700 text-center">
              <strong>Research participants only.</strong> Do not use real banking passwords here.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
