import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/useAuth'
import { Button, Input, Select, Alert } from '../components/ui'
import type { SelfRegisterRole } from '../types'


const ROLE_OPTIONS = [
  { value: 'employee', label: 'Bank Employee' },
  { value: 'manager', label: 'Branch Manager / Team Lead' },
  { value: 'customer', label: 'Bank Customer' },
]

interface FormValues {
  name: string
  email: string
  password: string
  confirmPassword: string
  role: SelfRegisterRole | ''
  department: string
}


interface FormErrors {
  name?: string
  email?: string
  password?: string
  confirmPassword?: string
  role?: string
}

export default function RegisterPage() {
  const { register, isLoading } = useAuth()
  const navigate = useNavigate()

  const [values, setValues] = useState<FormValues>({
    name: '', email: '', password: '', confirmPassword: '', role: '', department: '',
  })
  const [errors, setErrors] = useState<FormErrors>({})
  const [apiError, setApiError] = useState<string | null>(null)
  const [consented, setConsented] = useState(false)

  function set(field: keyof FormValues) {
    return (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
      setValues(v => ({ ...v, [field]: e.target.value }))
  }

  function validate(): boolean {
    const e: FormErrors = {}
    if (!values.name.trim()) e.name = 'Full name is required.'
    if (!values.email) e.email = 'Email is required.'
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(values.email)) e.email = 'Enter a valid email.'
    if (!values.password) e.password = 'Password is required.'
    else if (values.password.length < 8) e.password = 'Password must be at least 8 characters.'
    if (values.confirmPassword !== values.password) e.confirmPassword = 'Passwords do not match.'
    if (!values.role) e.role = 'Please select your role.'
    setErrors(e)
    return Object.keys(e).length === 0
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setApiError(null)
    if (!validate()) return
    if (!consented) { setApiError('You must agree to the research participation terms.'); return }
    try {
      await register({
        name: values.name,
        email: values.email,
        password: values.password,
        role: values.role as SelfRegisterRole,
        department: values.department || undefined,
      })
      // Role-based redirect: employees/managers → dashboard, customers → survey
      const dest = values.role === 'customer' ? '/survey' : '/dashboard'
      navigate(dest, { replace: true })
    } catch (err) {
      setApiError(err instanceof Error ? err.message : 'Registration failed.')
    }
  }

  return (
    <div className="min-h-[calc(100vh-4rem)] flex items-center justify-center bg-slate-50 px-4 py-12">
      <div className="w-full max-w-lg">
        <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-8">
          {/* Header */}
          <div className="text-center mb-8">
            <div className="mx-auto mb-4 h-12 w-12 rounded-xl bg-gradient-to-br from-blue-700 to-blue-500 flex items-center justify-center text-white font-bold text-xl shadow">
              B
            </div>
            <h1 className="text-2xl font-bold text-slate-900">Create your account</h1>
            <p className="text-sm text-slate-500 mt-1">Register to participate in the BankTech Analytics study</p>
          </div>

          {apiError && (
            <div className="mb-6">
              <Alert type="error">{apiError}</Alert>
            </div>
          )}

          <form onSubmit={handleSubmit} noValidate className="space-y-5">
            <Input
              label="Full name"
              type="text"
              value={values.name}
              onChange={set('name')}
              placeholder="Jane Smith"
              error={errors.name}
              autoComplete="name"
              required
            />
            <Input
              label="Email address"
              type="email"
              value={values.email}
              onChange={set('email')}
              placeholder="you@example.com"
              error={errors.email}
              autoComplete="email"
              required
            />
            <Select
              label="Your role"
              value={values.role}
              onChange={set('role')}
              options={ROLE_OPTIONS}
              placeholder="Select your role…"
              error={errors.role}
              required
            />
            <Input
              label="Department (optional)"
              type="text"
              value={values.department}
              onChange={set('department')}
              placeholder="e.g. Retail Banking, Operations"
              hint="Helps us contextualise your responses."
            />
            <Input
              label="Password"
              type="password"
              value={values.password}
              onChange={set('password')}
              placeholder="Minimum 8 characters"
              error={errors.password}
              autoComplete="new-password"
              required
            />
            <Input
              label="Confirm password"
              type="password"
              value={values.confirmPassword}
              onChange={set('confirmPassword')}
              placeholder="Repeat your password"
              error={errors.confirmPassword}
              autoComplete="new-password"
              required
            />

            {/* Consent checkbox */}
            <label className="flex items-start gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={consented}
                onChange={e => setConsented(e.target.checked)}
                className="mt-0.5 h-4 w-4 rounded border-slate-300 text-blue-600 accent-blue-600"
              />
              <span className="text-xs text-slate-600 leading-relaxed">
                I agree to participate in this academic research project and understand my
                responses will be stored anonymously and used only for research purposes.{' '}
                <Link to="/privacy" className="text-blue-600 hover:underline" target="_blank">Privacy policy</Link>.
              </span>
            </label>

            <Button
              type="submit"
              variant="primary"
              size="lg"
              isLoading={isLoading}
              disabled={!consented}
              className="w-full bg-blue-600 hover:bg-blue-700 border-blue-600 hover:border-blue-700"
            >
              Create account
            </Button>
          </form>

          <p className="mt-6 text-center text-sm text-slate-600">
            Already have an account?{' '}
            <Link to="/login" className="font-medium text-blue-600 hover:text-blue-700">Sign in</Link>
          </p>
        </div>
      </div>
    </div>
  )
}
