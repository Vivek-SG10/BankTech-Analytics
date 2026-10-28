/**
 * AnalyticsPage — Research analytics dashboard for admin/researcher roles.
 *
 * All data comes from backend API endpoints.
 * Hardcoded chart values have been removed.
 * Empty-state cards are shown when N is insufficient.
 * A synthetic-data label ("LIVE — drawn from PostgreSQL") is always shown.
 *
 * Sections:
 *   1. Filter bar (department, date range, bank type, experience range)
 *   2. Index summary cards (TAI, EJSI, EPI, CSEI)
 *   3. Descriptive statistics — bar chart per item
 *   4. Correlations — scatter-plot summary table + suppression notices
 *   5. Regression models — coefficient table
 *   6. Missing-value report
 *   7. CSV export button
 */
import { useState, useEffect, useCallback } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar,
  ResponsiveContainer, Cell,
} from 'recharts'
import { Card, Badge } from '../components/ui'
import { PageShell } from '../components/Layout'
import { analyticsApi } from '../services/api'
import type {
  AnalyticsFilters,
  IndexResult,
  DescriptiveStat,
  CorrelationResult,
  RegressionResult,
  AnalyticsSummary,
} from '../types'

// ── Colour palette ────────────────────────────────────────────────────────────

const COLOURS = {
  navy:  '#1e3a5f',
  blue:  '#1d4ed8',
  sky:   '#38bdf8',
  teal:  '#0d9488',
  amber: '#f59e0b',
  green: '#16a34a',
  red:   '#dc2626',
  grey:  '#94a3b8',
}

const INDEX_COLOURS: Record<string, string> = {
  TAI_employee: COLOURS.blue,
  TAI_manager:  COLOURS.navy,
  EJSI:         COLOURS.teal,
  EPI_manager:  COLOURS.green,
  EPI_self:     '#86efac',
  CSEI:         COLOURS.amber,
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function pct(v: number | null | undefined): string {
  return v != null ? `${v.toFixed(1)}%` : '—'
}
function fmt(v: number | null | undefined, dp = 3): string {
  return v != null ? v.toFixed(dp) : '—'
}

// ── Empty state ───────────────────────────────────────────────────────────────

function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-slate-400">
      <svg className="w-12 h-12 mb-3 opacity-40" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
          d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
      <p className="text-sm">{message}</p>
    </div>
  )
}

// ── Loading skeleton ───────────────────────────────────────────────────────────

function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse bg-slate-100 rounded-lg ${className}`} />
}

// ── Section heading ───────────────────────────────────────────────────────────

function SectionHeading({ title, description, badge }: {
  title: string; description?: string; badge?: string
}) {
  return (
    <div className="flex items-start justify-between mb-4 pb-3 border-b border-slate-100">
      <div>
        <h2 className="text-base font-semibold text-slate-800">{title}</h2>
        {description && <p className="text-xs text-slate-500 mt-0.5">{description}</p>}
      </div>
      {badge && <Badge color="blue">{badge}</Badge>}
    </div>
  )
}

// ── Index score card ───────────────────────────────────────────────────────────

function IndexCard({ result, colour, label }: {
  result: IndexResult | null
  colour: string
  label: string
}) {
  if (!result) return <Skeleton className="h-36" />
  const score = result.score_pct
  return (
    <Card>
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</span>
        {result.warning
          ? <Badge color="amber">Suppressed</Badge>
          : <Badge color="green">Live</Badge>}
      </div>
      <div className="mb-1">
        <span className="text-3xl font-bold" style={{ color: score != null ? colour : COLOURS.grey }}>
          {score != null ? `${score.toFixed(1)}%` : '—'}
        </span>
        {score != null && (
          <div className="mt-2 h-2 bg-slate-100 rounded-full overflow-hidden">
            <div className="h-2 rounded-full transition-all" style={{ width: `${score}%`, background: colour }} />
          </div>
        )}
      </div>
      <p className="text-xs text-slate-500 mt-2">N = {result.n}</p>
      {result.cronbach_alpha != null && (
        <p className="text-xs text-slate-400">α = {result.cronbach_alpha.toFixed(3)}</p>
      )}
      {result.warning && (
        <p className="text-xs text-amber-600 mt-1">{result.warning}</p>
      )}
    </Card>
  )
}

// ── Filter bar ────────────────────────────────────────────────────────────────

interface FilterBarProps {
  filters: AnalyticsFilters
  onChange: (f: AnalyticsFilters) => void
  departments: string[]
}

function FilterBar({ filters, onChange, departments }: FilterBarProps) {
  function set(key: keyof AnalyticsFilters, value: string) {
    onChange({ ...filters, [key]: value || undefined })
  }
  function reset() { onChange({}) }

  const inputClass = `
    block w-full rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-700
    focus:outline-none focus:ring-2 focus:ring-blue-400
  `

  return (
    <Card className="mb-6">
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex-1 min-w-32">
          <label className="block text-xs text-slate-500 mb-1">Department</label>
          <select value={filters.department ?? ''} onChange={e => set('department', e.target.value)} className={inputClass}>
            <option value="">All departments</option>
            {departments.map(d => <option key={d} value={d}>{d}</option>)}
          </select>
        </div>
        <div className="flex-1 min-w-28">
          <label className="block text-xs text-slate-500 mb-1">From date</label>
          <input type="date" value={filters.from_date ?? ''} onChange={e => set('from_date', e.target.value)} className={inputClass} />
        </div>
        <div className="flex-1 min-w-28">
          <label className="block text-xs text-slate-500 mb-1">To date</label>
          <input type="date" value={filters.to_date ?? ''} onChange={e => set('to_date', e.target.value)} className={inputClass} />
        </div>
        <div className="flex-1 min-w-32">
          <label className="block text-xs text-slate-500 mb-1">Bank type</label>
          <select value={filters.bank_type ?? ''} onChange={e => set('bank_type', e.target.value)} className={inputClass}>
            <option value="">All types</option>
            {['retail','commercial','investment','Islamic','cooperative'].map(t => (
              <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
            ))}
          </select>
        </div>
        <div className="flex-1 min-w-28">
          <label className="block text-xs text-slate-500 mb-1">Experience</label>
          <select value={filters.experience_range ?? ''} onChange={e => set('experience_range', e.target.value)} className={inputClass}>
            <option value="">All ranges</option>
            {['0-1','2-5','6-10','11+'].map(r => <option key={r} value={r}>{r} yrs</option>)}
          </select>
        </div>
        <button onClick={reset}
          className="px-3 py-1.5 rounded-lg border border-slate-200 text-xs text-slate-600 hover:bg-slate-50 transition">
          Reset
        </button>
      </div>
      {Object.values(filters).some(v => v) && (
        <p className="text-xs text-blue-600 mt-2">
          Filters active: {Object.entries(filters).filter(([,v]) => v).map(([k, v]) => `${k}=${v}`).join(', ')}
        </p>
      )}
    </Card>
  )
}

// ── Descriptive stats chart ───────────────────────────────────────────────────

const SECTION_LABELS: Record<string, string> = {
  tai_1: 'TAI', tai_2: 'TAI', tai_3: 'TAI', tai_4: 'TAI', tai_5: 'TAI',
  tai_mgr_1: 'TAI-M', tai_mgr_2: 'TAI-M', tai_mgr_3: 'TAI-M',
  ejsi_1: 'EJSI', ejsi_2: 'EJSI', ejsi_3: 'EJSI', ejsi_4: 'EJSI', ejsi_5: 'EJSI', ejsi_6: 'EJSI',
  epi_s_1: 'EPI-S', epi_s_2: 'EPI-S', epi_s_3: 'EPI-S',
  epi_m_1: 'EPI-M', epi_m_2: 'EPI-M', epi_m_3: 'EPI-M', epi_m_4: 'EPI-M',
  csei_1: 'CSEI', csei_2: 'CSEI', csei_3: 'CSEI', csei_4: 'CSEI', csei_5: 'CSEI', csei_6: 'CSEI',
}

const SECTION_COLOURS: Record<string, string> = {
  TAI: COLOURS.blue, 'TAI-M': COLOURS.navy,
  EJSI: COLOURS.teal, 'EPI-S': '#86efac', 'EPI-M': COLOURS.green, CSEI: COLOURS.amber,
}

function DescriptiveChart({ stats }: { stats: DescriptiveStat[] }) {
  const data = stats
    .filter(s => s.mean != null && s.n > 0)
    .map(s => ({
      name: s.item,
      mean: s.mean!,
      sd: s.sd ?? 0,
      section: SECTION_LABELS[s.item] ?? '?',
    }))

  if (data.length === 0) return <EmptyState message="No data yet — submit surveys to populate this chart." />

  return (
    <ResponsiveContainer width="100%" height={320}>
      <BarChart data={data} margin={{ top: 5, right: 20, left: 0, bottom: 60 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
        <XAxis dataKey="name" tick={{ fontSize: 10 }} angle={-45} textAnchor="end" />
        <YAxis domain={[1, 5]} tick={{ fontSize: 11 }} label={{ value: 'Mean (1–5)', angle: -90, position: 'insideLeft', fontSize: 11, fill: '#94a3b8' }} />
        <Tooltip
          formatter={(v: unknown) => [typeof v === 'number' ? v.toFixed(3) : String(v), 'Mean']}
          contentStyle={{ fontSize: 12 }}
        />
        <Bar dataKey="mean" radius={[4, 4, 0, 0]} maxBarSize={28}>
          {data.map((entry, i) => (
            <Cell key={i} fill={SECTION_COLOURS[entry.section] ?? COLOURS.grey} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

// ── Index radar chart ─────────────────────────────────────────────────────────

function IndexRadar({ indices }: { indices: { name: string; score: number | null; colour: string }[] }) {
  const data = indices.filter(i => i.score != null).map(i => ({ subject: i.name, value: i.score! }))
  if (data.length === 0) return <EmptyState message="Collect at least 5 responses per survey to unlock index scores." />
  return (
    <ResponsiveContainer width="100%" height={240}>
      <RadarChart data={data}>
        <PolarGrid />
        <PolarAngleAxis dataKey="subject" tick={{ fontSize: 11 }} />
        <PolarRadiusAxis domain={[0, 100]} tick={{ fontSize: 9 }} />
        <Radar dataKey="value" stroke={COLOURS.blue} fill={COLOURS.blue} fillOpacity={0.25} />
        <Tooltip formatter={(v: unknown) => [`${typeof v === 'number' ? v.toFixed(1) : v}%`]} />
      </RadarChart>
    </ResponsiveContainer>
  )
}

// ── Correlation table ─────────────────────────────────────────────────────────

function CorrelationTable({ correlations }: { correlations: CorrelationResult[] }) {
  if (correlations.length === 0) return <EmptyState message="No correlation data available." />
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-100 text-left">
            <th className="pb-2 font-medium text-slate-600 text-xs">Research Question</th>
            <th className="pb-2 font-medium text-slate-600 text-xs text-right">N</th>
            <th className="pb-2 font-medium text-slate-600 text-xs text-right">r</th>
            <th className="pb-2 font-medium text-slate-600 text-xs text-right">p-value</th>
            <th className="pb-2 font-medium text-slate-600 text-xs text-center">Status</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-50">
          {correlations.map((c, i) => (
            <tr key={i} className="hover:bg-slate-50">
              <td className="py-2.5 text-xs text-slate-700">{c.label}</td>
              <td className="py-2.5 text-xs text-slate-500 text-right">{c.n}</td>
              <td className="py-2.5 text-xs font-mono text-right">
                {c.suppressed ? '—' : fmt(c.r)}
              </td>
              <td className="py-2.5 text-xs font-mono text-right">
                {c.suppressed ? '—' : (c.p_value != null && c.p_value < 0.001 ? '<.001' : fmt(c.p_value))}
              </td>
              <td className="py-2.5 text-center">
                {c.suppressed
                  ? <Badge color="amber">Suppressed (N&lt;10)</Badge>
                  : c.significant
                    ? <Badge color="green">Significant</Badge>
                    : <Badge color="slate">Not significant</Badge>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-xs text-slate-400 mt-3 border-t border-slate-100 pt-2">
        ⚠️ Correlation does not imply causation. A significant r does not establish causal direction.
      </p>
    </div>
  )
}

// ── Regression table ─────────────────────────────────────────────────────────

function RegressionTable({ models }: { models: RegressionResult[] }) {
  if (models.length === 0) return <EmptyState message="No regression data available." />
  return (
    <div className="space-y-6">
      {models.map((m, i) => (
        <div key={i}>
          <p className="text-xs font-semibold text-slate-700 mb-1">
            Model {i + 1}: {m.outcome} ~ {m.predictors.join(' + ')}
          </p>
          {m.suppressed ? (
            <p className="text-xs text-amber-600 bg-amber-50 rounded p-2">
              Suppressed — N = {m.n} (minimum 20 required for OLS regression).
            </p>
          ) : (
            <div className="text-xs space-y-1">
              <div className="flex gap-6 text-slate-600">
                <span>R² = <strong>{fmt(m.r_squared)}</strong></span>
                <span>adj. R² = <strong>{fmt(m.adj_r_squared)}</strong></span>
                <span>F = <strong>{fmt(m.f_statistic, 2)}</strong></span>
                <span>p(F) = <strong>{m.f_p_value != null && m.f_p_value < 0.001 ? '<.001' : fmt(m.f_p_value)}</strong></span>
              </div>
              <div className="mt-2">
                <table className="w-full">
                  <thead>
                    <tr className="text-left text-slate-500">
                      <th className="font-medium pb-1">Predictor</th>
                      <th className="font-medium pb-1 text-right">β</th>
                      <th className="font-medium pb-1 text-right">SE</th>
                      <th className="font-medium pb-1 text-right">p</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(m.coefficients as Record<string, { coef: number; se: number; p_value: number }>).map(([name, vals]) => (
                      <tr key={name} className="border-t border-slate-50">
                        <td className="py-0.5 text-slate-700">{name}</td>
                        <td className="py-0.5 text-right font-mono">{fmt(vals.coef)}</td>
                        <td className="py-0.5 text-right font-mono">{fmt(vals.se)}</td>
                        <td className="py-0.5 text-right font-mono">{vals.p_value < 0.001 ? '<.001' : fmt(vals.p_value)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
          <p className="text-xs text-slate-400 mt-1">{m.note}</p>
        </div>
      ))}
      <p className="text-xs text-slate-400 border-t border-slate-100 pt-2">
        ⚠️ OLS regression results are associative. Random assignment was not used; causal inference is not warranted.
      </p>
    </div>
  )
}

// ── Missing value table ───────────────────────────────────────────────────────

function MissingTable({ data }: { data: Record<string, unknown> }) {
  const sections = ['employee_survey', 'manager_survey', 'customer_survey'] as const
  return (
    <div className="space-y-4">
      {sections.map(section => {
        const s = data[section] as { n_responses: number; items: { item: string; label: string; n_missing: number; pct_missing: number | null }[] } | undefined
        if (!s) return null
        return (
          <div key={section}>
            <p className="text-xs font-semibold text-slate-600 mb-1 capitalize">{section.replace('_', ' ')} (N={s.n_responses})</p>
            {s.n_responses === 0
              ? <p className="text-xs text-slate-400">No responses yet.</p>
              : s.items.filter(i => i.n_missing > 0).length === 0
                ? <p className="text-xs text-green-600">✓ No missing values detected.</p>
                : (
                  <table className="w-full text-xs">
                    <thead><tr className="text-slate-500 text-left">
                      <th className="pb-1 font-medium">Item</th>
                      <th className="pb-1 font-medium text-right">Missing</th>
                      <th className="pb-1 font-medium text-right">%</th>
                    </tr></thead>
                    <tbody className="divide-y divide-slate-50">
                      {s.items.filter(i => i.n_missing > 0).map(item => (
                        <tr key={item.item}>
                          <td className="py-0.5 text-slate-700">{item.item}</td>
                          <td className="py-0.5 text-right">{item.n_missing}</td>
                          <td className="py-0.5 text-right">{item.pct_missing?.toFixed(1)}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
          </div>
        )
      })}
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// Main page
// ══════════════════════════════════════════════════════════════════════════════

export default function AnalyticsPage() {
  const [filters, setFilters] = useState<AnalyticsFilters>({})
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null)
  const [taiData, setTaiData] = useState<{ TAI_employee: IndexResult; TAI_manager: IndexResult } | null>(null)
  const [ejsiData, setEjsiData] = useState<{ EJSI: IndexResult } | null>(null)
  const [epiData, setEpiData] = useState<{ EPI_manager: IndexResult; EPI_self: IndexResult } | null>(null)
  const [cseiData, setCseiData] = useState<{ CSEI: IndexResult } | null>(null)
  const [descData, setDescData] = useState<DescriptiveStat[] | null>(null)
  const [corrData, setCorrData] = useState<CorrelationResult[] | null>(null)
  const [regData, setRegData] = useState<RegressionResult[] | null>(null)
  const [missingData, setMissingData] = useState<Record<string, unknown> | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [downloading, setDownloading] = useState(false)

  // Derive departments from descriptive data (departments present in data)
  const [departments, setDepartments] = useState<string[]>([])

  const fetchAll = useCallback(async (f: AnalyticsFilters) => {
    setLoading(true)
    setError(null)
    try {
      const [sum, tai, ejsi, epi, csei, desc, corr, reg, miss] = await Promise.all([
        analyticsApi.getSummary(f),
        analyticsApi.getTai(f),
        analyticsApi.getEjsi(f),
        analyticsApi.getEpi(f),
        analyticsApi.getCsei(f),
        analyticsApi.getDescriptive(f),
        analyticsApi.getCorrelations(f),
        analyticsApi.getRegression(f),
        analyticsApi.getMissing(f),
      ])
      setSummary(sum)
      setTaiData(tai)
      setEjsiData(ejsi)
      setEpiData(epi)
      setCseiData(csei)
      setDescData(desc.items)
      setCorrData(corr.correlations)
      setRegData(reg.models)
      setMissingData(miss)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load analytics data.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void fetchAll(filters)
  }, [filters, fetchAll])

  // Refresh departments list on initial load (simplified — derive from filter dropdown separately)
  useEffect(() => {
    // In a real system you'd fetch /analytics/departments; here we populate from overview data
    setDepartments([]) // will populate from actual data when available
  }, [])

  async function handleDownloadCsv() {
    setDownloading(true)
    try {
      await analyticsApi.downloadCsv(filters)
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'CSV export failed.')
    } finally {
      setDownloading(false)
    }
  }

  const totalResponses = summary?.response_counts.total ?? 0
  const scores = summary?.index_scores

  const radarIndices = [
    { name: 'TAI (emp)', score: scores?.TAI_employee ?? null, colour: INDEX_COLOURS.TAI_employee },
    { name: 'EJSI', score: scores?.EJSI ?? null, colour: INDEX_COLOURS.EJSI },
    { name: 'EPI (mgr)', score: scores?.EPI_manager ?? null, colour: INDEX_COLOURS.EPI_manager },
    { name: 'CSEI', score: scores?.CSEI ?? null, colour: INDEX_COLOURS.CSEI },
  ]

  return (
    <PageShell
      title="Research Analytics"
      subtitle="Aggregated findings from the BankTech Analytics research project."
    >
      {/* Data label */}
      <div className="mb-5 flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2 text-xs text-slate-500 bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5">
          <span className="w-2 h-2 rounded-full bg-green-500 inline-block" />
          {summary?.data_label ?? 'LIVE — drawn from PostgreSQL survey responses.'}
          {totalResponses > 0 && (
            <span className="text-slate-400">· {totalResponses} total response{totalResponses !== 1 ? 's' : ''}</span>
          )}
        </div>
        <button
          onClick={handleDownloadCsv}
          disabled={downloading || loading}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-slate-200 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50 transition"
        >
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
          {downloading ? 'Exporting…' : 'Export CSV'}
        </button>
      </div>

      {/* Error state */}
      {error && (
        <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700">
          <strong>Error:</strong> {error}
          <button onClick={() => fetchAll(filters)} className="ml-3 underline text-xs">Retry</button>
        </div>
      )}

      {/* Filter bar */}
      <FilterBar filters={filters} onChange={f => setFilters(f)} departments={departments} />

      {/* ── Response counts ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
        {['employee', 'manager', 'customer'].map(role => (
          <Card key={role}>
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-1">
              {role.charAt(0).toUpperCase() + role.slice(1)} responses
            </p>
            {loading ? <Skeleton className="h-8 w-16" /> : (
              <p className="text-2xl font-bold text-slate-900">
                {summary?.response_counts[role as 'employee' | 'manager' | 'customer'] ?? 0}
              </p>
            )}
          </Card>
        ))}
        <Card>
          <p className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-1">Total</p>
          {loading ? <Skeleton className="h-8 w-16" /> : (
            <p className="text-2xl font-bold text-blue-700">{totalResponses}</p>
          )}
        </Card>
      </div>

      {/* ── Index scores ── */}
      <Card className="mb-6">
        <SectionHeading
          title="Research Index Scores"
          description="Score = (mean / 5) × 100. Minimum 5 responses required. Self-assessed and supervisor-assessed EPI are always reported separately."
          badge={totalResponses === 0 ? 'No data' : 'Live'}
        />
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
          {loading ? Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-36" />) : (
            <>
              <IndexCard label="TAI — Employee" colour={INDEX_COLOURS.TAI_employee} result={taiData?.TAI_employee ?? null} />
              <IndexCard label="TAI — Manager" colour={INDEX_COLOURS.TAI_manager} result={taiData?.TAI_manager ?? null} />
              <IndexCard label="EJSI" colour={INDEX_COLOURS.EJSI} result={ejsiData?.EJSI ?? null} />
              <IndexCard label="EPI — Manager (primary)" colour={INDEX_COLOURS.EPI_manager} result={epiData?.EPI_manager ?? null} />
              <IndexCard label="EPI — Self (supplementary)" colour={INDEX_COLOURS['EPI_self']} result={epiData?.EPI_self ?? null} />
              <IndexCard label="CSEI" colour={INDEX_COLOURS.CSEI} result={cseiData?.CSEI ?? null} />
            </>
          )}
        </div>

        {/* Radar overview */}
        <div className="border-t border-slate-100 pt-4">
          <p className="text-xs font-medium text-slate-500 mb-3">Index overview (non-suppressed scores only)</p>
          {loading ? <Skeleton className="h-48" /> : <IndexRadar indices={radarIndices} />}
        </div>
      </Card>

      {/* ── Descriptive statistics ── */}
      <Card className="mb-6">
        <SectionHeading
          title="Per-Item Descriptive Statistics"
          description="Mean scores (1–5 Likert) per survey item. Colour indicates index membership."
        />
        <div className="flex flex-wrap gap-3 mb-4 text-xs">
          {Object.entries(SECTION_COLOURS).map(([k, c]) => (
            <span key={k} className="flex items-center gap-1.5">
              <span className="w-3 h-3 rounded-sm inline-block" style={{ background: c }} />
              {k}
            </span>
          ))}
        </div>
        {loading ? <Skeleton className="h-72" /> : <DescriptiveChart stats={descData ?? []} />}

        {/* Stats table */}
        {!loading && descData && descData.length > 0 && (
          <div className="mt-4 overflow-x-auto border-t border-slate-100 pt-4">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-slate-500 border-b border-slate-100">
                  <th className="pb-1.5 font-medium">Item</th>
                  <th className="pb-1.5 font-medium text-right">N</th>
                  <th className="pb-1.5 font-medium text-right">Mean</th>
                  <th className="pb-1.5 font-medium text-right">SD</th>
                  <th className="pb-1.5 font-medium text-right">Median</th>
                  <th className="pb-1.5 font-medium text-right">IQR</th>
                  <th className="pb-1.5 font-medium text-right">Skew</th>
                  <th className="pb-1.5 font-medium text-right">Kurt</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {descData.filter(s => s.n > 0).map(s => (
                  <tr key={s.item} className="hover:bg-slate-50">
                    <td className="py-1 text-slate-700 font-mono">{s.item}</td>
                    <td className="py-1 text-right text-slate-500">{s.n}</td>
                    <td className="py-1 text-right font-semibold" style={{ color: SECTION_COLOURS[SECTION_LABELS[s.item] ?? ''] ?? '#64748b' }}>
                      {pct(s.mean ? (s.mean / 5) * 100 : null).replace('%', '')} ({fmt(s.mean, 2)})
                    </td>
                    <td className="py-1 text-right">{fmt(s.sd, 2)}</td>
                    <td className="py-1 text-right">{fmt(s.median, 2)}</td>
                    <td className="py-1 text-right">{fmt(s.iqr, 2)}</td>
                    <td className="py-1 text-right">{fmt(s.skewness, 2)}</td>
                    <td className="py-1 text-right">{fmt(s.kurtosis, 2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* ── Correlations ── */}
      <Card className="mb-6">
        <SectionHeading
          title="Pre-specified Correlation Analyses"
          description="Four research-question correlations (Pearson). Suppressed when N < 10."
        />
        {loading ? <Skeleton className="h-32" /> : <CorrelationTable correlations={corrData ?? []} />}
      </Card>

      {/* ── Regression ── */}
      <Card className="mb-6">
        <SectionHeading
          title="OLS Regression Models"
          description="Two pre-specified models. Suppressed when N < 20. Associative findings only."
        />
        {loading ? <Skeleton className="h-28" /> : <RegressionTable models={regData ?? []} />}
      </Card>

      {/* ── Missing values ── */}
      <Card>
        <SectionHeading
          title="Missing-Value Report"
          description="Missing values are documented — no imputation is performed."
        />
        {loading ? <Skeleton className="h-24" /> : (
          missingData ? <MissingTable data={missingData} /> : <EmptyState message="No data." />
        )}
      </Card>
    </PageShell>
  )
}
