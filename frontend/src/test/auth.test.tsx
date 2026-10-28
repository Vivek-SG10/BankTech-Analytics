/**
 * Frontend auth integration tests — Vitest + Testing Library
 *
 * These tests render components with a mocked API layer so no live backend
 * is required. They verify:
 *   1. Login form validation and error states
 *   2. Successful login → localStorage + navigation
 *   3. Register form validation and role restriction
 *   4. ProtectedRoute redirects unauthenticated users
 *   5. ProtectedRoute blocks wrong roles
 *   6. PublicOnlyRoute redirects authenticated users
 *   7. Auth persistence: /me re-validated on mount
 *   8. Logout clears state
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { AuthProvider } from '../context/AuthContext'
import { ProtectedRoute, PublicOnlyRoute } from '../components/RouteGuards'
import LoginPage from '../pages/LoginPage'
import RegisterPage from '../pages/RegisterPage'

// ── Mock the API service ───────────────────────────────────────────────────
vi.mock('../services/api', () => ({
  authApi: {
    login: vi.fn(),
    register: vi.fn(),
    me: vi.fn(),
    logout: vi.fn(),
  },
  adminApi: {},
  healthApi: { get: vi.fn() },
  surveyApi: {},
  analyticsApi: {},
  ragApi: {},
}))

import { authApi } from '../services/api'

const MOCK_EMPLOYEE: import('../types').User = {
  id: 'user-1',
  name: 'Alice',
  email: 'alice@ex.com',
  role: 'employee',
  department: 'Operations',
  is_active: true,
}

const MOCK_ADMIN: import('../types').User = {
  id: 'admin-1',
  name: 'Admin',
  email: 'admin@banktech.dev',
  role: 'admin',
  department: 'IT',
  is_active: true,
}

const MOCK_TOKEN = 'eyJhbGciOiJIUzI1NiJ9.test.test'

function renderWithAuth(ui: React.ReactNode, initialPath = '/') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <AuthProvider>
        {ui}
      </AuthProvider>
    </MemoryRouter>
  )
}

// ── Setup / teardown ───────────────────────────────────────────────────────
beforeEach(() => {
  localStorage.clear()
  vi.clearAllMocks()
  // Default: /me returns 401 (no stored session)
  vi.mocked(authApi.me).mockRejectedValue(new Error('Unauthorized'))
})

afterEach(() => {
  localStorage.clear()
})

// ── 1. Login form validation ───────────────────────────────────────────────
describe('LoginPage — form validation', () => {
  it('shows email required error on empty submit', async () => {
    renderWithAuth(<LoginPage />, '/login')
    await waitFor(() => screen.getByRole('button', { name: /sign in/i }))
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))
    expect(await screen.findByText(/email is required/i)).toBeInTheDocument()
  })

  it('shows invalid email error', async () => {
    renderWithAuth(<LoginPage />, '/login')
    await waitFor(() => screen.getByLabelText(/email address/i))
    await userEvent.type(screen.getByLabelText(/email address/i), 'not-an-email')
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))
    expect(await screen.findByText(/valid email/i)).toBeInTheDocument()
  })

  it('shows password required error', async () => {
    renderWithAuth(<LoginPage />, '/login')
    await waitFor(() => screen.getByLabelText(/email address/i))
    await userEvent.type(screen.getByLabelText(/email address/i), 'a@b.com')
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))
    expect(await screen.findByText(/password is required/i)).toBeInTheDocument()
  })
})

// ── 2. Login success ───────────────────────────────────────────────────────
describe('LoginPage — success', () => {
  it('stores token and user in localStorage on successful login', async () => {
    vi.mocked(authApi.login).mockResolvedValueOnce({
      access_token: MOCK_TOKEN,
      token_type: 'bearer',
      user: MOCK_EMPLOYEE,
    })

    renderWithAuth(
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/dashboard" element={<div>Dashboard</div>} />
      </Routes>,
      '/login'
    )

    await waitFor(() => screen.getByLabelText(/email address/i))
    await userEvent.type(screen.getByLabelText(/email address/i), 'alice@ex.com')
    await userEvent.type(screen.getByLabelText(/password/i), 'SecurePass1!')
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(localStorage.getItem('bt_token')).toBe(MOCK_TOKEN)
    })
    expect(JSON.parse(localStorage.getItem('bt_user') ?? '{}')).toMatchObject({ role: 'employee' })
  })

  it('shows API error message on 401', async () => {
    vi.mocked(authApi.login).mockRejectedValueOnce(new Error('Incorrect email or password.'))

    renderWithAuth(<LoginPage />, '/login')
    await waitFor(() => screen.getByLabelText(/email address/i))
    await userEvent.type(screen.getByLabelText(/email address/i), 'a@b.com')
    await userEvent.type(screen.getByLabelText(/password/i), 'WrongPass!')
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))

    expect(await screen.findByText(/incorrect email or password/i)).toBeInTheDocument()
  })
})

// ── 3. Register form validation ────────────────────────────────────────────
describe('RegisterPage — form validation', () => {
  it('renders without admin or researcher in the role dropdown', async () => {
    renderWithAuth(<RegisterPage />, '/register')
    await waitFor(() => screen.getByLabelText(/role/i))
    const select = screen.getByLabelText(/role/i) as HTMLSelectElement
    const options = Array.from(select.options).map(o => o.value)
    expect(options).not.toContain('admin')
    expect(options).not.toContain('researcher')
    expect(options).toContain('employee')
    expect(options).toContain('manager')
    expect(options).toContain('customer')
  })

  it('shows password mismatch error', async () => {
    renderWithAuth(<RegisterPage />, '/register')
    await waitFor(() => screen.getByLabelText(/full name/i))

    await userEvent.type(screen.getByLabelText(/full name/i), 'Test User')
    await userEvent.type(screen.getByLabelText(/email address/i), 'test@ex.com')
    await userEvent.selectOptions(screen.getByLabelText(/your role/i), 'employee')
    await userEvent.type(screen.getByPlaceholderText(/minimum 8 characters/i), 'SecurePass1!')
    // confirmPassword field — type directly then mistype
    const confirmInput = screen.getByPlaceholderText(/repeat your password/i)
    await userEvent.type(confirmInput, 'Different!')

    // Submit — validation fires before consent check
    fireEvent.submit(screen.getByRole('button', { name: /create account/i }).closest('form')!)

    expect(await screen.findByText(/passwords do not match/i)).toBeInTheDocument()
  })
})

// ── 4. ProtectedRoute — unauthenticated ───────────────────────────────────
describe('ProtectedRoute', () => {
  it('redirects unauthenticated users to /login', async () => {
    renderWithAuth(
      <Routes>
        <Route path="/login" element={<div>Login page</div>} />
        <Route
          path="/dashboard"
          element={<ProtectedRoute><div>Protected content</div></ProtectedRoute>}
        />
      </Routes>,
      '/dashboard'
    )
    // Wait for /me to settle (it rejects → unauthenticated)
    expect(await screen.findByText(/login page/i)).toBeInTheDocument()
    expect(screen.queryByText(/protected content/i)).not.toBeInTheDocument()
  })

  it('renders children when authenticated', async () => {
    vi.mocked(authApi.me).mockResolvedValueOnce(MOCK_EMPLOYEE)
    localStorage.setItem('bt_token', MOCK_TOKEN)
    localStorage.setItem('bt_user', JSON.stringify(MOCK_EMPLOYEE))

    renderWithAuth(
      <Routes>
        <Route path="/login" element={<div>Login page</div>} />
        <Route
          path="/dashboard"
          element={<ProtectedRoute><div>Protected content</div></ProtectedRoute>}
        />
      </Routes>,
      '/dashboard'
    )
    expect(await screen.findByText(/protected content/i)).toBeInTheDocument()
  })
})

// ── 5. ProtectedRoute — role guard ─────────────────────────────────────────
describe('ProtectedRoute — role enforcement', () => {
  it('blocks employee from admin-only route → /forbidden', async () => {
    vi.mocked(authApi.me).mockResolvedValueOnce(MOCK_EMPLOYEE)
    localStorage.setItem('bt_token', MOCK_TOKEN)
    localStorage.setItem('bt_user', JSON.stringify(MOCK_EMPLOYEE))

    renderWithAuth(
      <Routes>
        <Route path="/forbidden" element={<div>Forbidden page</div>} />
        <Route
          path="/analytics"
          element={
            <ProtectedRoute roles={['admin', 'researcher']}>
              <div>Analytics</div>
            </ProtectedRoute>
          }
        />
      </Routes>,
      '/analytics'
    )
    expect(await screen.findByText(/forbidden page/i)).toBeInTheDocument()
  })

  it('allows admin to access admin-only route', async () => {
    vi.mocked(authApi.me).mockResolvedValueOnce(MOCK_ADMIN)
    localStorage.setItem('bt_token', MOCK_TOKEN)
    localStorage.setItem('bt_user', JSON.stringify(MOCK_ADMIN))

    renderWithAuth(
      <Routes>
        <Route path="/forbidden" element={<div>Forbidden page</div>} />
        <Route
          path="/analytics"
          element={
            <ProtectedRoute roles={['admin', 'researcher']}>
              <div>Analytics</div>
            </ProtectedRoute>
          }
        />
      </Routes>,
      '/analytics'
    )
    expect(await screen.findByText(/analytics/i)).toBeInTheDocument()
  })
})

// ── 6. PublicOnlyRoute ──────────────────────────────────────────────────────
describe('PublicOnlyRoute', () => {
  it('redirects authenticated users away from login', async () => {
    vi.mocked(authApi.me).mockResolvedValueOnce(MOCK_EMPLOYEE)
    localStorage.setItem('bt_token', MOCK_TOKEN)
    localStorage.setItem('bt_user', JSON.stringify(MOCK_EMPLOYEE))

    renderWithAuth(
      <Routes>
        <Route path="/dashboard" element={<div>Dashboard</div>} />
        <Route
          path="/login"
          element={<PublicOnlyRoute><div>Login page</div></PublicOnlyRoute>}
        />
      </Routes>,
      '/login'
    )
    expect(await screen.findByText(/dashboard/i)).toBeInTheDocument()
  })
})

// ── 7. Auth persistence ────────────────────────────────────────────────────
describe('Auth persistence', () => {
  it('clears state when /me returns 401 (expired token)', async () => {
    // Expired token stored
    localStorage.setItem('bt_token', 'expired-token')
    localStorage.setItem('bt_user', JSON.stringify(MOCK_EMPLOYEE))
    vi.mocked(authApi.me).mockRejectedValueOnce(new Error('Unauthorized'))

    renderWithAuth(
      <Routes>
        <Route path="/login" element={<div>Login page</div>} />
        <Route
          path="/dashboard"
          element={<ProtectedRoute><div>Protected</div></ProtectedRoute>}
        />
      </Routes>,
      '/dashboard'
    )
    expect(await screen.findByText(/login page/i)).toBeInTheDocument()
    await waitFor(() => {
      expect(localStorage.getItem('bt_token')).toBeNull()
    })
  })
})

// ── 8. Logout ──────────────────────────────────────────────────────────────
describe('Logout', () => {
  it('removes token and user from localStorage', async () => {
    localStorage.setItem('bt_token', MOCK_TOKEN)
    localStorage.setItem('bt_user', JSON.stringify(MOCK_EMPLOYEE))
    vi.mocked(authApi.me).mockResolvedValueOnce(MOCK_EMPLOYEE)
    vi.mocked(authApi.logout).mockImplementation(() => {
      localStorage.removeItem('bt_token')
      localStorage.removeItem('bt_user')
    })

    // Import useAuth and call logout
    const { useAuth } = await import('../context/useAuth')
    function LogoutButton() {
      const { logout } = useAuth()
      return <button onClick={logout}>Logout</button>
    }

    renderWithAuth(
      <Routes>
        <Route path="/login" element={<div>Login page</div>} />
        <Route path="/dashboard" element={
          <ProtectedRoute>
            <LogoutButton />
          </ProtectedRoute>
        } />
      </Routes>,
      '/dashboard'
    )

    const btn = await screen.findByRole('button', { name: /logout/i })
    fireEvent.click(btn)

    await waitFor(() => {
      expect(localStorage.getItem('bt_token')).toBeNull()
      expect(localStorage.getItem('bt_user')).toBeNull()
    })
  })
})
