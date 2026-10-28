/**
 * DashboardPage — role-aware home screen.
 *
 * Admin/Researcher: pulls real summary data from GET /api/v1/analytics/summary
 *   and GET /api/v1/health.
 * Manager: shows survey-submission status (GET /api/v1/surveys/mine).
 * Employee / Customer: survey call-to-action with submission status.
 */
import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/useAuth'
import { Card, Badge } from '../components/ui'
import { PageShell } from '../components/Layout'
import { analyticsApi, surveyApi, healthApi } from '../services/api'
import type { AnalyticsSummary, SubmissionSummary, HealthResponse } from '../types'

// Evaluated once at module load — avoids calling new Date() during render
const _h = new Date(Date.now()).getHours()
const GREETING = _h < 12 ? 'Good morning' : _h < 18 ? 'Good afternoon' : 'Good evening'

// ── Skeleton helpers ──────────────────────────────────────────────────────

function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse bg-slate-100 rounded-lg ${className}`} />
}

// ── Shared stat card ──────────────────────────────────────────────────────

function StatCard({
  label, value, sub, loading = false, colour,
}: {
  label: string
  value: string | number | null
  sub?: string
  loading?: boolean
  colour?: string
}) {
  return (
    <Card>
      <p className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-1">{label}</p>
      {loading
        ? <Skeleton className="h-8 w-16 mb-1" />
        : <p className="text-3xl font-bold" style={{ color: colour ?? '#0f172a' }}>
            {value ?? '—'}
          </p>}
      {sub && <p className="text-xs text-slate-400 mt-1">{sub}</p>}
    </Card>
  )
}

// ── Index score mini-card ─────────────────────────────────────────────────

function IndexMiniCard({ label, score, colour }: { label: string; score: number | null; colour: string }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-slate-50 last:border-0">
      <span className="text-xs text-slate-600">{label}</span>
      {score != null
        ? (
          <div className="flex items-center gap-2">
            <div className="w-24 h-1.5 bg-slate-100 rounded-full overflow-hidden">
              <div className="h-full rounded-full" style={{ width: `${score}%`, background: colour }} />
            </div>
            <span className="text-xs font-semibold" style={{ color: colour }}>
              {score.toFixed(1)}%
            </span>
          </div>
        )
        : <Badge color="amber">N &lt; 5</Badge>}
    </div>
  )
}

// ── Quick action link ─────────────────────────────────────────────────────

function ActionLink({ to, icon, title, subtitle, badge }: {
  to: string; icon: string; title: string; subtitle: string; badge?: React.ReactNode
}) {
  return (
    <Link to={to} className="flex items-center gap-3 p-3 rounded-lg hover:bg-slate-50 border border-slate-100 transition group">
      <span className="text-xl">{icon}</span>
      <div className="flex-1">
        <p className="text-sm font-medium text-slate-800 group-hover:text-blue-700">{title}</p>
        <p className="text-xs text-slate-500">{subtitle}</p>
      </div>
      {badge}
    </Link>
  )
}

// ── Survey status pill ────────────────────────────────────────────────────

function SurveyStatusPill({ submissions, role }: { submissions: SubmissionSummary[]; role: string }) {
  const active = submissions.find(s => !s.is_voided && s.survey_type === role)
  if (!active) return <Badge color="amber">Pending</Badge>
  const d = new Date(active.submitted_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
  return <Badge color="green">Submitted {d}</Badge>
}

// ══════════════════════════════════════════════════════════════════════════════
// Admin / Researcher Dashboard
// ══════════════════════════════════════════════════════════════════════════════

function AdminDashboard() {
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null)
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      analyticsApi.getSummary().catch(() => null),
      healthApi.get().catch(() => null),
    ]).then(([s, h]) => {
      setSummary(s)
      setHealth(h)
      setLoading(false)
    })
  }, [])

  const counts = summary?.response_counts
  const scores = summary?.index_scores

  return (
    <>
      {/* Response counts */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
        <StatCard label="Total Responses" value={counts?.total ?? null}
          loading={loading} colour="#1d4ed8"
          sub={counts ? undefined : loading ? undefined : 'No data yet'} />
        <StatCard label="Employees" value={counts?.employee ?? null} loading={loading} />
        <StatCard label="Managers"  value={counts?.manager  ?? null} loading={loading} />
        <StatCard label="Customers" value={counts?.customer ?? null} loading={loading} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Index scores */}
        <Card className="lg:col-span-1">
          <h2 className="text-base font-semibold text-slate-800 mb-3">Index Scores</h2>
          {loading ? (
            <div className="space-y-3">
              {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-6" />)}
            </div>
          ) : scores ? (
            <div>
              <IndexMiniCard label="TAI (employee)" score={scores.TAI_employee} colour="#1d4ed8" />
              <IndexMiniCard label="EJSI" score={scores.EJSI} colour="#0d9488" />
              <IndexMiniCard label="EPI (manager)" score={scores.EPI_manager} colour="#16a34a" />
              <IndexMiniCard label="CSEI" score={scores.CSEI} colour="#f59e0b" />
              <p className="text-xs text-slate-400 mt-3">
                Min 5 responses required per index. Suppressed indices show badge.
              </p>
            </div>
          ) : (
            <p className="text-xs text-slate-400">No data yet — survey responses needed.</p>
          )}
          <Link to="/analytics" className="mt-4 block text-xs text-blue-600 hover:underline">
            Full analytics dashboard →
          </Link>
        </Card>

        {/* Quick actions */}
        <Card>
          <h2 className="text-base font-semibold text-slate-800 mb-3">Quick Actions</h2>
          <div className="space-y-2">
            <ActionLink to="/analytics" icon="📊" title="Research Analytics"
              subtitle="Index scores, correlations, regression" />
            <ActionLink to="/methodology" icon="📄" title="Methodology"
              subtitle="Research design and instruments" />
            <ActionLink to="/faq" icon="🤖" title="FAQ Assistant"
              subtitle="Banking Q&A chatbot (Phase 4)" />
          </div>
        </Card>

        {/* System status */}
        <Card>
          <h2 className="text-base font-semibold text-slate-800 mb-3">System Status</h2>
          <div className="space-y-3 text-sm">
            <div className="flex justify-between items-center">
              <span className="text-slate-600">API Server</span>
              <Badge color={health ? 'green' : 'amber'}>{health ? 'Online' : loading ? '…' : 'Unreachable'}</Badge>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-slate-600">PostgreSQL</span>
              <Badge color={health?.database === 'ok' ? 'green' : 'red'}>
                {health?.database === 'ok' ? 'Healthy' : loading ? '…' : 'Check'}
              </Badge>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-slate-600">Survey module</span>
              <Badge color="green">Phase 3</Badge>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-slate-600">Analytics engine</span>
              <Badge color="green">Phase 3</Badge>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-slate-600">RAG / ChromaDB</span>
              <Badge color="amber">Phase 4</Badge>
            </div>
          </div>
          {health?.database_latency_ms != null && (
            <p className="text-xs text-slate-400 mt-3">DB latency: {health.database_latency_ms.toFixed(1)} ms</p>
          )}
        </Card>
      </div>
    </>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// Manager Dashboard
// ══════════════════════════════════════════════════════════════════════════════

function ManagerDashboard() {
  const [submissions, setSubmissions] = useState<SubmissionSummary[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    surveyApi.listMine().then(s => { setSubmissions(s); setLoading(false) }).catch(() => setLoading(false))
  }, [])

  const hasSubmitted = submissions.some(s => !s.is_voided && s.survey_type === 'manager')

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <Card>
        <h2 className="text-base font-semibold text-slate-800 mb-1">Your Tasks</h2>
        <p className="text-xs text-slate-500 mb-4">Complete your participation in the study</p>
        <div className="space-y-3">
          <ActionLink to="/survey" icon="📝" title="Manager Survey"
            subtitle="Technology assessment and team performance"
            badge={loading ? <Skeleton className="h-5 w-16" /> : <SurveyStatusPill submissions={submissions} role="manager" />}
          />
          <ActionLink to="/analytics" icon="📊" title="View Analytics"
            subtitle="Aggregated research findings" />
        </div>
        {hasSubmitted && (
          <p className="text-xs text-green-600 mt-3">
            ✓ Survey submitted. You may re-submit at any time to update your responses.
          </p>
        )}
      </Card>

      <Card>
        <h2 className="text-base font-semibold text-slate-800 mb-3">Research Focus</h2>
        <ul className="space-y-2 text-sm text-slate-600">
          {[
            'Adoption of mobile and digital banking platforms',
            'Technology impact on team productivity',
            'Change management in digital transformation',
            'Employee satisfaction with new banking technology',
          ].map(item => (
            <li key={item} className="flex gap-2">
              <span className="text-blue-500 mt-0.5 shrink-0">→</span>
              {item}
            </li>
          ))}
        </ul>
        <Link to="/methodology" className="inline-block mt-4 text-xs text-blue-600 hover:underline">
          Read the methodology →
        </Link>
      </Card>
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// Employee Dashboard
// ══════════════════════════════════════════════════════════════════════════════

function EmployeeDashboard() {
  const [submissions, setSubmissions] = useState<SubmissionSummary[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    surveyApi.listMine().then(s => { setSubmissions(s); setLoading(false) }).catch(() => setLoading(false))
  }, [])

  const hasSubmitted = submissions.some(s => !s.is_voided && s.survey_type === 'employee')

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <Card>
        <h2 className="text-base font-semibold text-slate-800 mb-1">Participate in the Study</h2>
        <p className="text-xs text-slate-500 mb-4">
          Your responses help us understand the real-world impact of banking technology on frontline staff.
        </p>

        {loading ? (
          <Skeleton className="h-12 mb-2" />
        ) : hasSubmitted ? (
          <div>
            <div className="flex items-center gap-2 mb-3 text-sm text-green-700 bg-green-50 rounded-lg p-3">
              <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              Survey submitted — thank you for participating!
            </div>
            <Link
              to="/survey"
              className="block w-full text-center px-4 py-2.5 rounded-lg border border-slate-200 text-slate-700 text-sm font-medium hover:bg-slate-50 transition"
            >
              Update my responses →
            </Link>
          </div>
        ) : (
          <Link
            to="/survey"
            className="block w-full text-center px-4 py-3 rounded-lg bg-blue-600 text-white font-semibold hover:bg-blue-700 transition"
          >
            Start Employee Survey →
          </Link>
        )}

        <p className="text-xs text-slate-400 mt-3 text-center">
          Takes approximately 10–12 minutes. Fully anonymous.
        </p>
      </Card>

      <Card>
        <h2 className="text-base font-semibold text-slate-800 mb-3">About the Research</h2>
        <p className="text-sm text-slate-600 leading-relaxed">
          This study examines how fintech tools—such as digital onboarding, AI-assisted customer
          service, and mobile platforms—affect the daily work and satisfaction of bank employees.
        </p>
        <p className="text-sm text-slate-600 leading-relaxed mt-3">
          Results will be published in aggregate. Your identity will never be linked to individual responses.
        </p>
        <Link to="/methodology" className="inline-block mt-4 text-sm text-blue-600 hover:underline">
          Read the full methodology →
        </Link>
      </Card>
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// Customer Dashboard
// ══════════════════════════════════════════════════════════════════════════════

function CustomerDashboard() {
  const [submissions, setSubmissions] = useState<SubmissionSummary[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    surveyApi.listMine().then(s => { setSubmissions(s); setLoading(false) }).catch(() => setLoading(false))
  }, [])

  const hasSubmitted = submissions.some(s => !s.is_voided && s.survey_type === 'customer')

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <Card>
        <h2 className="text-base font-semibold text-slate-800 mb-1">Share Your Experience</h2>
        <p className="text-xs text-slate-500 mb-4">
          Help us understand what customers really think about digital banking services.
        </p>

        {loading ? (
          <Skeleton className="h-12 mb-2" />
        ) : hasSubmitted ? (
          <div>
            <div className="flex items-center gap-2 mb-3 text-sm text-green-700 bg-green-50 rounded-lg p-3">
              <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              Thank you — your survey is submitted!
            </div>
            <Link
              to="/survey"
              className="block w-full text-center px-4 py-2.5 rounded-lg border border-slate-200 text-slate-700 text-sm font-medium hover:bg-slate-50 transition"
            >
              Update my feedback →
            </Link>
          </div>
        ) : (
          <Link
            to="/survey"
            className="block w-full text-center px-4 py-3 rounded-lg bg-blue-600 text-white font-semibold hover:bg-blue-700 transition"
          >
            Start Customer Survey →
          </Link>
        )}

        <p className="text-xs text-slate-400 mt-3 text-center">
          Takes approximately 8–10 minutes. Your responses are anonymous.
        </p>
      </Card>

      <Card>
        <h2 className="text-base font-semibold text-slate-800 mb-3">Why Your Voice Matters</h2>
        <p className="text-sm text-slate-600 leading-relaxed">
          Banks are rapidly digitising their services. This research helps identify gaps between what
          banks offer and what customers actually need, so future services are better designed.
        </p>
        <Link to="/faq" className="flex items-center gap-2 mt-4 text-sm text-blue-600 hover:underline">
          <span>🤖</span> Try the Banking FAQ Assistant
        </Link>
      </Card>
    </div>
  )
}

// ── Main Dashboard ────────────────────────────────────────────────────────

export default function DashboardPage() {
  const { user } = useAuth()

  if (!user) {
    return (
      <PageShell title="Dashboard">
        <div className="text-center py-20">
          <p className="text-slate-500 mb-4">Please sign in to access your dashboard.</p>
          <Link to="/login" className="text-blue-600 hover:underline font-medium">Sign in →</Link>
        </div>
      </PageShell>
    )
  }

  const subtitle: Record<string, string> = {
    admin:      'System overview and research management',
    researcher: 'Research overview and analytics',
    manager:    'Branch and team overview',
    employee:   'Your study participation',
    customer:   'Your experience survey',
  }

  return (
    <PageShell
      title={`${GREETING}, ${user.name.split(' ')[0]}`}
      subtitle={subtitle[user.role] ?? ''}
    >
      {(user.role === 'admin' || user.role === 'researcher') && <AdminDashboard />}
      {user.role === 'manager'  && <ManagerDashboard />}
      {user.role === 'employee' && <EmployeeDashboard />}
      {user.role === 'customer' && <CustomerDashboard />}
    </PageShell>
  )
}
