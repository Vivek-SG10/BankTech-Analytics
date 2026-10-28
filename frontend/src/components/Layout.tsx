import { useState } from 'react'
import { NavLink, Link, useNavigate } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useAuth } from '../context/useAuth'
import type { UserRole } from '../types'

// ── Navigation config ─────────────────────────────────────────────────────

interface NavItem {
  label: string
  to: string
  roles: UserRole[] | 'all' | 'public'
}

const NAV_ITEMS: NavItem[] = [
  { label: 'Dashboard',  to: '/dashboard',   roles: ['admin','researcher','manager','employee','customer'] },
  { label: 'Survey',     to: '/survey',       roles: ['employee','manager','customer'] },
  { label: 'Analytics',  to: '/analytics',    roles: ['admin','researcher','manager'] },
  { label: 'FAQ Assistant', to: '/faq',       roles: ['admin','researcher','manager','employee','customer'] },
  { label: 'Methodology',to: '/methodology',  roles: 'all' },
  { label: 'Privacy',    to: '/privacy',      roles: 'all' },
  { label: 'About',      to: '/about',        roles: 'all' },
]

const ROLE_LABELS: Record<UserRole, string> = {
  admin: 'Admin',
  researcher: 'Researcher',
  manager: 'Manager',
  employee: 'Employee',
  customer: 'Customer',
}

// ── App Layout ────────────────────────────────────────────────────────────

interface AppLayoutProps {
  children: ReactNode
}

export function AppLayout({ children }: AppLayoutProps) {
  const { user, logout, isAuthenticated } = useAuth()
  const navigate = useNavigate()
  const [mobileOpen, setMobileOpen] = useState(false)

  const visibleItems = NAV_ITEMS.filter(item => {
    if (item.roles === 'all') return true
    if (item.roles === 'public') return !isAuthenticated
    if (!user) return false
    return (item.roles as UserRole[]).includes(user.role)
  })

  function handleLogout() {
    logout()
    navigate('/')
  }

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      {/* Top Nav */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-50 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex h-16 items-center justify-between">
            {/* Logo */}
            <Link to={isAuthenticated ? '/dashboard' : '/'} className="flex items-center gap-3">
              <div className="h-9 w-9 rounded-lg bg-gradient-to-br from-blue-700 to-blue-500 flex items-center justify-center text-white font-bold text-lg select-none shadow">
                B
              </div>
              <div className="hidden sm:block">
                <p className="text-sm font-bold text-slate-900 leading-tight">BankTech Analytics</p>
                <p className="text-xs text-slate-500">Research Platform</p>
              </div>
            </Link>

            {/* Desktop Nav */}
            <nav className="hidden md:flex items-center gap-1">
              {visibleItems.map(item => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    `px-3 py-2 rounded-md text-sm font-medium transition-colors
                    ${isActive
                      ? 'bg-blue-50 text-blue-700'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                    }`
                  }
                >
                  {item.label}
                </NavLink>
              ))}
            </nav>

            {/* User menu */}
            <div className="flex items-center gap-3">
              {isAuthenticated && user ? (
                <>
                  <div className="hidden sm:flex flex-col items-end">
                    <span className="text-sm font-medium text-slate-800">{user.name}</span>
                    <span className="text-xs text-slate-500">{ROLE_LABELS[user.role]}</span>
                  </div>
                  <button
                    onClick={handleLogout}
                    className="px-3 py-1.5 rounded-md text-sm font-medium border border-slate-300 text-slate-700 hover:bg-slate-100 transition"
                  >
                    Sign out
                  </button>
                </>
              ) : (
                <>
                  <Link to="/login" className="text-sm text-slate-600 hover:text-slate-900 font-medium">Sign in</Link>
                  <Link to="/register" className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition shadow-sm">
                    Register
                  </Link>
                </>
              )}
              {/* Mobile hamburger */}
              <button
                className="md:hidden p-2 rounded-md text-slate-500 hover:bg-slate-100"
                onClick={() => setMobileOpen(v => !v)}
                aria-label="Toggle menu"
              >
                {mobileOpen ? '✕' : '☰'}
              </button>
            </div>
          </div>
        </div>

        {/* Mobile drawer */}
        {mobileOpen && (
          <div className="md:hidden border-t border-slate-200 bg-white px-4 py-3 space-y-1">
            {visibleItems.map(item => (
              <NavLink
                key={item.to}
                to={item.to}
                onClick={() => setMobileOpen(false)}
                className={({ isActive }) =>
                  `block px-3 py-2 rounded-md text-sm font-medium transition
                  ${isActive ? 'bg-blue-50 text-blue-700' : 'text-slate-700 hover:bg-slate-100'}`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </div>
        )}
      </header>

      {/* Page Content */}
      <main className="flex-1">
        {children}
      </main>

      {/* Footer */}
      <footer className="bg-white border-t border-slate-200 py-6 mt-auto">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row justify-between items-center gap-3 text-xs text-slate-500">
          <p>© 2024 BankTech Analytics Research Project. Academic use only.</p>
          <div className="flex gap-4">
            <Link to="/methodology" className="hover:text-slate-700">Methodology</Link>
            <Link to="/privacy" className="hover:text-slate-700">Privacy</Link>
            <Link to="/about" className="hover:text-slate-700">About</Link>
          </div>
        </div>
      </footer>
    </div>
  )
}

// ── Page Shell ────────────────────────────────────────────────────────────

interface PageShellProps {
  title: string
  subtitle?: string
  children: ReactNode
  actions?: ReactNode
}

export function PageShell({ title, subtitle, children, actions }: PageShellProps) {
  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">{title}</h1>
          {subtitle && <p className="text-sm text-slate-500 mt-1">{subtitle}</p>}
        </div>
        {actions && <div className="flex gap-3">{actions}</div>}
      </div>
      {children}
    </div>
  )
}
