import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext'
import { AppLayout } from './components/Layout'
import { ProtectedRoute, PublicOnlyRoute } from './components/RouteGuards'

// Pages — public
import LandingPage     from './pages/LandingPage'
import LoginPage       from './pages/LoginPage'
import RegisterPage    from './pages/RegisterPage'
import MethodologyPage from './pages/MethodologyPage'
import PrivacyPage     from './pages/PrivacyPage'
import AboutPage       from './pages/AboutPage'
import NotFoundPage    from './pages/NotFoundPage'
import ForbiddenPage   from './pages/ForbiddenPage'

// Pages — authenticated
import DashboardPage from './pages/DashboardPage'
import SurveyPage    from './pages/SurveyPage'
import AnalyticsPage from './pages/AnalyticsPage'
import FaqPage       from './pages/FaqPage'

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppLayout>
          <Routes>
            {/* ── Public ─────────────────────────────────────────────── */}
            <Route path="/"            element={<LandingPage />} />
            <Route path="/methodology" element={<MethodologyPage />} />
            <Route path="/privacy"     element={<PrivacyPage />} />
            <Route path="/about"       element={<AboutPage />} />
            <Route path="/forbidden"   element={<ForbiddenPage />} />

            {/* ── Auth pages (redirect away when already logged in) ──── */}
            <Route
              path="/login"
              element={
                <PublicOnlyRoute>
                  <LoginPage />
                </PublicOnlyRoute>
              }
            />
            <Route
              path="/register"
              element={
                <PublicOnlyRoute>
                  <RegisterPage />
                </PublicOnlyRoute>
              }
            />

            {/* ── Protected: any authenticated user ─────────────────── */}
            <Route
              path="/dashboard"
              element={
                <ProtectedRoute>
                  <DashboardPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/faq"
              element={
                <ProtectedRoute>
                  <FaqPage />
                </ProtectedRoute>
              }
            />

            {/* ── Protected: employees, managers, customers only ─────── */}
            <Route
              path="/survey"
              element={
                <ProtectedRoute roles={['employee', 'manager', 'customer']}>
                  <SurveyPage />
                </ProtectedRoute>
              }
            />

            {/* ── Protected: admin and researcher only ────────────────── */}
            <Route
              path="/analytics"
              element={
                <ProtectedRoute roles={['admin', 'researcher']}>
                  <AnalyticsPage />
                </ProtectedRoute>
              }
            />

            {/* ── Catch-all ──────────────────────────────────────────── */}
            <Route path="/404" element={<NotFoundPage />} />
            <Route path="*"    element={<Navigate to="/404" replace />} />
          </Routes>
        </AppLayout>
      </AuthProvider>
    </BrowserRouter>
  )
}
