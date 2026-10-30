/**
 * AnalyticsPage — Research analytics dashboard for admin/researcher roles.
 *
 * All data comes dynamically from backend API endpoints and PostgreSQL survey tables.
 * Empty-state cards are shown when N is 0.
 * A live-data label ("LIVE — drawn from PostgreSQL survey responses") is shown.
 *
 * Sections:
 *   1. Filter bar (department, date range, bank type, experience range)
 *   2. Stakeholder response counts & survey volume breakdown
 *   3. Research Index summary cards (TAI, EJSI, EPI, CSEI) & Radar Overview
 *   4. Survey rating distribution graph (1–5 Likert answers across questions)
 *   5. Per-Item Descriptive statistics — bar chart & data table
 *   6. Submitted Surveys Explorer & Detailed Inspection Modal (Admin audit)
 *   7. Correlations — scatter-plot summary table + suppression notices
 *   8. Regression models — coefficient table
 *   9. Missing-value report
 *   10. CSV export
 */
import { useState, useEffect, useCallback } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar,
  ResponsiveContainer, Cell,
} from 'recharts'
import { Card, Badge, Button } from '../components/ui'
import { PageShell } from '../components/Layout'
import { analyticsApi, surveyApi } from '../services/api'
import type {
  AnalyticsFilters,
  IndexResult,
  DescriptiveStat,
  CorrelationResult,
  RegressionResult,
  AnalyticsSummary,
  SubmittedSurveyDetail,
  SurveySubmissionsReport,
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

// ── Question Code to Readable Question Text Mapping ──────────────────────────

const SURVEY_QUESTIONS: Record<string, { label: string; question: string; category: string }> = {
  tai_1: { label: 'TAI 1', question: 'The digital banking tools I use daily are easy to operate.', category: 'Tech Adoption (Employee)' },
  tai_2: { label: 'TAI 2', question: 'Using digital tools makes my daily tasks more efficient.', category: 'Tech Adoption (Employee)' },
  tai_3: { label: 'TAI 3', question: 'I receive sufficient training to use banking technology confidently.', category: 'Tech Adoption (Employee)' },
  tai_4: { label: 'TAI 4', question: 'I regularly use digital tools for customer-facing tasks.', category: 'Tech Adoption (Employee)' },
  tai_5: { label: 'TAI 5', question: 'Technology enables me to resolve customer queries more quickly.', category: 'Tech Adoption (Employee)' },
  ejsi_1: { label: 'EJSI 1', question: 'Overall, I am satisfied with my current role.', category: 'Job Satisfaction' },
  ejsi_2: { label: 'EJSI 2', question: 'I feel valued as an employee of this organisation.', category: 'Job Satisfaction' },
  ejsi_3: { label: 'EJSI 3', question: 'I am satisfied with the support I receive from my manager.', category: 'Job Satisfaction' },
  ejsi_4: { label: 'EJSI 4', question: 'My workload is manageable within normal working hours.', category: 'Job Satisfaction' },
  ejsi_5: { label: 'EJSI 5', question: 'My work is meaningful and contributes to organisational goals.', category: 'Job Satisfaction' },
  ejsi_6: { label: 'EJSI 6', question: 'I would recommend this organisation as a good place to work.', category: 'Job Satisfaction' },
  epi_s_1: { label: 'EPI-S 1', question: 'I consistently meet my individual performance targets.', category: 'Self-Performance' },
  epi_s_2: { label: 'EPI-S 2', question: 'I handle customer queries and complaints effectively.', category: 'Self-Performance' },
  epi_s_3: { label: 'EPI-S 3', question: 'I collaborate effectively with colleagues to achieve team goals.', category: 'Self-Performance' },
  tai_mgr_1: { label: 'TAI-M 1', question: 'My team effectively uses the digital banking tools available.', category: 'Tech Assessment (Manager)' },
  tai_mgr_2: { label: 'TAI-M 2', question: 'Technology adoption has improved my team\'s overall productivity.', category: 'Tech Assessment (Manager)' },
  tai_mgr_3: { label: 'TAI-M 3', question: 'The technology training provided is adequate for my team\'s needs.', category: 'Tech Assessment (Manager)' },
  epi_m_1: { label: 'EPI-M 1', question: 'My team members consistently meet their individual targets.', category: 'Manager Performance' },
  epi_m_2: { label: 'EPI-M 2', question: 'My team handles customer queries and complaints effectively.', category: 'Manager Performance' },
  epi_m_3: { label: 'EPI-M 3', question: 'My team adapts well to changes introduced by new technology.', category: 'Manager Performance' },
  epi_m_4: { label: 'EPI-M 4', question: 'Overall, I rate my team\'s performance as high.', category: 'Manager Performance' },
  csei_1: { label: 'CSEI 1', question: 'The staff member who assisted me was knowledgeable about digital services.', category: 'Customer Service' },
  csei_2: { label: 'CSEI 2', question: 'My query was resolved efficiently without unnecessary delays.', category: 'Customer Service' },
  csei_3: { label: 'CSEI 3', question: 'I am satisfied with the overall quality of service I received.', category: 'Customer Service' },
  csei_4: { label: 'CSEI 4', question: 'The staff member helped me understand or use digital banking channels.', category: 'Customer Service' },
  csei_5: { label: 'CSEI 5', question: 'The service met my expectations.', category: 'Customer Service' },
  csei_6: { label: 'CSEI 6', question: 'I would recommend this branch to friends or family.', category: 'Customer Service' },
}

const LIKERT_TEXT: Record<number, string> = {
  1: 'Strongly Disagree (1)',
  2: 'Disagree (2)',
  3: 'Neutral (3)',
  4: 'Agree (4)',
  5: 'Strongly Agree (5)',
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
        {result.warning && score == null
          ? <Badge color="amber">Pending</Badge>
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
          className="px-3 py-1.5 rounded-lg border border-slate-200 text-xs text-slate-600 hover:bg-slate-50 transition cursor-pointer">
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
      label: s.label,
      mean: s.mean!,
      sd: s.sd ?? 0,
      section: SECTION_LABELS[s.item] ?? '?',
    }))

  if (data.length === 0) return <EmptyState message="No survey data yet — submit a survey to populate this chart." />

  return (
    <ResponsiveContainer width="100%" height={320}>
      <BarChart data={data} margin={{ top: 5, right: 20, left: 0, bottom: 60 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
        <XAxis dataKey="name" tick={{ fontSize: 10 }} angle={-45} textAnchor="end" />
        <YAxis domain={[1, 5]} tick={{ fontSize: 11 }} label={{ value: 'Mean (1–5)', angle: -90, position: 'insideLeft', fontSize: 11, fill: '#94a3b8' }} />
        <Tooltip
          formatter={(v: unknown, _n, item) => [
            `${typeof v === 'number' ? v.toFixed(3) : String(v)} / 5.0`,
            item?.payload?.label ?? 'Mean',
          ]}
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
  if (data.length === 0) return <EmptyState message="Submit a survey to unlock and visualize live index radar charts." />
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

// ── Live Likert Distribution Chart ───────────────────────────────────────────

function LikertDistributionChart({ submissions }: { submissions: SubmittedSurveyDetail[] }) {
  const counts: Record<number, number> = { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 }
  let totalRatings = 0

  submissions.forEach(s => {
    if (s.scores) {
      Object.values(s.scores).forEach(val => {
        if (val >= 1 && val <= 5) {
          counts[val] = (counts[val] || 0) + 1
          totalRatings++
        }
      })
    }
  })

  if (totalRatings === 0) {
    return <EmptyState message="No Likert ratings submitted yet." />
  }

  const chartData = [
    { rating: 'Strongly Disagree (1)', count: counts[1], fill: '#ef4444' },
    { rating: 'Disagree (2)', count: counts[2], fill: '#f97316' },
    { rating: 'Neutral (3)', count: counts[3], fill: '#eab308' },
    { rating: 'Agree (4)', count: counts[4], fill: '#3b82f6' },
    { rating: 'Strongly Agree (5)', count: counts[5], fill: '#10b981' },
  ]

  return (
    <div>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 20 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
          <XAxis dataKey="rating" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
          <Tooltip formatter={(v: unknown) => [String(v), 'Total Responses']} />
          <Bar dataKey="count" radius={[4, 4, 0, 0]} maxBarSize={48}>
            {chartData.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.fill} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <p className="text-xs text-slate-500 text-center mt-1">
        Aggregated from {totalRatings} question ratings across {submissions.length} submitted survey(s).
      </p>
    </div>
  )
}

// ── Stakeholder Volume Chart ──────────────────────────────────────────────────

function StakeholderVolumeChart({ counts }: { counts: { employee: number; manager: number; customer: number } }) {
  const data = [
    { name: 'Employees', count: counts.employee, fill: COLOURS.blue },
    { name: 'Managers', count: counts.manager, fill: COLOURS.navy },
    { name: 'Customers', count: counts.customer, fill: COLOURS.amber },
  ]

  const total = counts.employee + counts.manager + counts.customer
  if (total === 0) return <EmptyState message="No survey submissions recorded yet." />

  return (
    <div>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} layout="vertical" margin={{ top: 10, right: 30, left: 30, bottom: 10 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" horizontal={false} />
          <XAxis type="number" tick={{ fontSize: 11 }} allowDecimals={false} />
          <YAxis dataKey="name" type="category" tick={{ fontSize: 11 }} />
          <Tooltip formatter={(v: unknown) => [String(v), 'Submissions']} />
          <Bar dataKey="count" radius={[0, 4, 4, 0]} maxBarSize={32}>
            {data.map((entry, index) => (
              <Cell key={`cell-vol-${index}`} fill={entry.fill} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <p className="text-xs text-slate-500 text-center mt-1">
        Total {total} verified submission(s) across all 3 stakeholder categories.
      </p>
    </div>
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
                  ? <Badge color="amber">Suppressed (N&lt;2)</Badge>
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
              Suppressed — N = {m.n} (minimum 2 required for preliminary regression).
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
  const [submissionsReport, setSubmissionsReport] = useState<SurveySubmissionsReport | null>(null)
  const [selectedSubmission, setSelectedSubmission] = useState<SubmittedSurveyDetail | null>(null)
  const [submissionFilter, setSubmissionFilter] = useState<'all' | 'employee' | 'manager' | 'customer'>('all')

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [downloading, setDownloading] = useState(false)
  const [departments, setDepartments] = useState<string[]>([])

  const fetchAll = useCallback(async (f: AnalyticsFilters) => {
    setLoading(true)
    setError(null)
    try {
      const [sum, tai, ejsi, epi, csei, desc, corr, reg, miss, subs] = await Promise.all([
        analyticsApi.getSummary(f),
        analyticsApi.getTai(f),
        analyticsApi.getEjsi(f),
        analyticsApi.getEpi(f),
        analyticsApi.getCsei(f),
        analyticsApi.getDescriptive(f),
        analyticsApi.getCorrelations(f),
        analyticsApi.getRegression(f),
        analyticsApi.getMissing(f),
        surveyApi.getAllSubmissions().catch(() => null),
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
      setSubmissionsReport(subs)

      if (subs?.all) {
        const depts = Array.from(new Set(subs.all.map(s => s.department).filter(Boolean))) as string[]
        setDepartments(depts)
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load analytics data.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void fetchAll(filters)
  }, [filters, fetchAll])

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

  const filteredSubmissions = submissionsReport?.all.filter(s => {
    if (submissionFilter === 'all') return true
    return s.survey_type === submissionFilter
  }) ?? []

  return (
    <PageShell
      title="Research Analytics & Survey Audit"
      subtitle="Dynamic findings computed directly from PostgreSQL survey submissions."
    >
      {/* Top Banner / Data Status */}
      <div className="mb-5 flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2 text-xs text-slate-600 bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 shadow-xs">
          <span className="w-2.5 h-2.5 rounded-full bg-green-500 animate-pulse inline-block" />
          <span className="font-semibold">{summary?.data_label ?? 'LIVE — drawn from PostgreSQL survey responses.'}</span>
          <span className="text-slate-400">· {totalResponses} total response{totalResponses !== 1 ? 's' : ''} recorded</span>
        </div>
        <button
          onClick={handleDownloadCsv}
          disabled={downloading || loading}
          className="flex items-center gap-2 px-3.5 py-1.5 rounded-lg border border-slate-200 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-50 disabled:opacity-50 transition shadow-xs cursor-pointer"
        >
          <svg className="w-4 h-4 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
          {downloading ? 'Exporting…' : 'Export Aggregated CSV'}
        </button>
      </div>

      {/* Error Notice */}
      {error && (
        <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700 flex justify-between items-center">
          <div><strong>Error:</strong> {error}</div>
          <button onClick={() => fetchAll(filters)} className="ml-3 underline text-xs font-semibold cursor-pointer">Retry</button>
        </div>
      )}

      {/* Filter bar */}
      <FilterBar filters={filters} onChange={f => setFilters(f)} departments={departments} />

      {/* ── Key Metrics Cards ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
        {['employee', 'manager', 'customer'].map(role => (
          <Card key={role}>
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">
              {role.charAt(0).toUpperCase() + role.slice(1)} Submissions
            </p>
            {loading ? <Skeleton className="h-8 w-16" /> : (
              <p className="text-2xl font-bold text-slate-900">
                {summary?.response_counts[role as 'employee' | 'manager' | 'customer'] ?? 0}
              </p>
            )}
            <p className="text-xs text-slate-400 mt-1">Verified records</p>
          </Card>
        ))}
        <Card>
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Total Submissions</p>
          {loading ? <Skeleton className="h-8 w-16" /> : (
            <p className="text-2xl font-bold text-blue-700">{totalResponses}</p>
          )}
          <p className="text-xs text-slate-400 mt-1">Active in analysis</p>
        </Card>
      </div>

      {/* ── Visual Survey Graphs (Directly from Survey Responses) ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        <Card>
          <SectionHeading
            title="Survey Likert Rating Distribution"
            description="Overall distribution of rating answers (1 to 5 Stars) submitted across all survey questions."
            badge="Survey Graph"
          />
          {loading ? <Skeleton className="h-56" /> : (
            <LikertDistributionChart submissions={submissionsReport?.all ?? []} />
          )}
        </Card>

        <Card>
          <SectionHeading
            title="Stakeholder Participation Volume"
            description="Real-time volume comparison of completed surveys across Employee, Manager, and Customer groups."
            badge="Survey Graph"
          />
          {loading ? <Skeleton className="h-56" /> : (
            <StakeholderVolumeChart counts={summary?.response_counts ?? { employee: 0, manager: 0, customer: 0 }} />
          )}
        </Card>
      </div>

      {/* ── Research Index Scores & Radar ── */}
      <Card className="mb-6">
        <SectionHeading
          title="Research Composite Index Scores"
          description="Scale: 0–100% (computed from Likert means). Dynamically generated from submitted survey records."
          badge={totalResponses === 0 ? 'No submissions' : 'Live Data'}
        />
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
          {loading ? Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-36" />) : (
            <>
              <IndexCard label="TAI — Employee Perception" colour={INDEX_COLOURS.TAI_employee} result={taiData?.TAI_employee ?? null} />
              <IndexCard label="TAI — Manager Team Assessment" colour={INDEX_COLOURS.TAI_manager} result={taiData?.TAI_manager ?? null} />
              <IndexCard label="EJSI — Employee Job Satisfaction" colour={INDEX_COLOURS.EJSI} result={ejsiData?.EJSI ?? null} />
              <IndexCard label="EPI — Manager Assessment (Primary)" colour={INDEX_COLOURS.EPI_manager} result={epiData?.EPI_manager ?? null} />
              <IndexCard label="EPI — Self-Assessed (Supplementary)" colour={INDEX_COLOURS['EPI_self']} result={epiData?.EPI_self ?? null} />
              <IndexCard label="CSEI — Customer Service Effectiveness" colour={INDEX_COLOURS.CSEI} result={cseiData?.CSEI ?? null} />
            </>
          )}
        </div>

        {/* Radar overview */}
        <div className="border-t border-slate-100 pt-4">
          <p className="text-xs font-semibold text-slate-600 mb-3">Multi-Dimensional Index Comparison Radar</p>
          {loading ? <Skeleton className="h-48" /> : <IndexRadar indices={radarIndices} />}
        </div>
      </Card>

      {/* ── Per-Item Descriptive Statistics ── */}
      <Card className="mb-6">
        <SectionHeading
          title="Per-Item Survey Question Averages (1–5 Likert Scale)"
          description="Mean Likert rating calculated for each specific survey question. Hover over bars to see the full question."
          badge="Live Means"
        />
        <div className="flex flex-wrap gap-3 mb-4 text-xs">
          {Object.entries(SECTION_COLOURS).map(([k, c]) => (
            <span key={k} className="flex items-center gap-1.5 font-medium text-slate-700">
              <span className="w-3 h-3 rounded-sm inline-block shadow-2xs" style={{ background: c }} />
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
                  <th className="pb-1.5 font-medium">Question Code</th>
                  <th className="pb-1.5 font-medium">Survey Question Text</th>
                  <th className="pb-1.5 font-medium text-right">N</th>
                  <th className="pb-1.5 font-medium text-right">Mean</th>
                  <th className="pb-1.5 font-medium text-right">SD</th>
                  <th className="pb-1.5 font-medium text-right">Median</th>
                  <th className="pb-1.5 font-medium text-right">IQR</th>
                  <th className="pb-1.5 font-medium text-right">Skewness</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {descData.filter(s => s.n > 0).map(s => (
                  <tr key={s.item} className="hover:bg-slate-50">
                    <td className="py-1 text-slate-800 font-mono font-semibold">{s.item}</td>
                    <td className="py-1 text-slate-600 max-w-xs truncate">{SURVEY_QUESTIONS[s.item]?.question || s.label}</td>
                    <td className="py-1 text-right text-slate-500">{s.n}</td>
                    <td className="py-1 text-right font-bold" style={{ color: SECTION_COLOURS[SECTION_LABELS[s.item] ?? ''] ?? '#64748b' }}>
                      {pct(s.mean ? (s.mean / 5) * 100 : null).replace('%', '')}% ({fmt(s.mean, 2)})
                    </td>
                    <td className="py-1 text-right">{fmt(s.sd, 2)}</td>
                    <td className="py-1 text-right">{fmt(s.median, 2)}</td>
                    <td className="py-1 text-right">{fmt(s.iqr, 2)}</td>
                    <td className="py-1 text-right">{fmt(s.skewness, 2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* ── SUBMITTED SURVEYS EXPLORER (ADMIN AUDIT & INSPECTION) ── */}
      <Card className="mb-6">
        <SectionHeading
          title="📋 Submitted Survey Responses (Admin Audit & Record Viewer)"
          description="View and inspect all individual survey submissions saved in PostgreSQL. Click 'Inspect Answers' to examine the exact answers submitted."
          badge={`${submissionsReport?.total ?? 0} Submissions`}
        />

        {/* Filter Tabs */}
        <div className="flex gap-2 mb-4 border-b border-slate-100 pb-3">
          {(['all', 'employee', 'manager', 'customer'] as const).map(tab => (
            <button
              key={tab}
              onClick={() => setSubmissionFilter(tab)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold capitalize transition cursor-pointer ${
                submissionFilter === tab
                  ? 'bg-blue-600 text-white shadow-xs'
                  : 'bg-slate-50 text-slate-600 hover:bg-slate-100'
              }`}
            >
              {tab === 'all' ? `All Surveys (${submissionsReport?.total ?? 0})` : `${tab} (${submissionsReport?.counts[tab] ?? 0})`}
            </button>
          ))}
        </div>

        {/* Submissions Table */}
        {filteredSubmissions.length === 0 ? (
          <EmptyState message="No submitted surveys found for this filter category." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-slate-500 border-b border-slate-200 pb-2">
                  <th className="pb-2 font-semibold">Survey ID</th>
                  <th className="pb-2 font-semibold">Stakeholder Type</th>
                  <th className="pb-2 font-semibold">Branch / Department</th>
                  <th className="pb-2 font-semibold">Submitted At</th>
                  <th className="pb-2 font-semibold text-right">Avg Rating</th>
                  <th className="pb-2 font-semibold text-center">Status</th>
                  <th className="pb-2 font-semibold text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredSubmissions.map(sub => (
                  <tr key={sub.id} className="hover:bg-blue-50/40 transition">
                    <td className="py-2.5 font-mono text-slate-700">{sub.id.substring(0, 8)}…</td>
                    <td className="py-2.5">
                      <span className={`px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wider ${
                        sub.survey_type === 'employee' ? 'bg-blue-100 text-blue-700' :
                        sub.survey_type === 'manager' ? 'bg-indigo-100 text-indigo-800' :
                        'bg-amber-100 text-amber-800'
                      }`}>
                        {sub.survey_type}
                      </span>
                    </td>
                    <td className="py-2.5 text-slate-700 font-medium">{sub.department || 'General'}</td>
                    <td className="py-2.5 text-slate-500">
                      {sub.submitted_at ? new Date(sub.submitted_at).toLocaleString('en-GB', {
                        day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
                      }) : '—'}
                    </td>
                    <td className="py-2.5 text-right font-bold text-slate-900">
                      {sub.avg_score.toFixed(1)} / 5.0 <span className="text-[10px] text-slate-500 font-normal">({(sub.avg_score / 5 * 100).toFixed(0)}%)</span>
                    </td>
                    <td className="py-2.5 text-center">
                      <Badge color={sub.is_voided ? 'slate' : 'green'}>{sub.is_voided ? 'Superseded' : 'Active'}</Badge>
                    </td>
                    <td className="py-2.5 text-right">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setSelectedSubmission(sub)}
                        className="text-xs py-1 px-2.5 text-blue-700 border-blue-200 hover:bg-blue-50"
                      >
                        Inspect Answers →
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* ── Inspection Modal ── */}
      {selectedSubmission && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-xs">
          <div className="bg-white rounded-2xl shadow-xl max-w-2xl w-full max-h-[90vh] flex flex-col overflow-hidden animate-in fade-in duration-150">
            {/* Modal Header */}
            <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50">
              <div>
                <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                  <span>Inspection:</span>
                  <span className="capitalize">{selectedSubmission.survey_type} Survey</span>
                  <Badge color="blue">{selectedSubmission.id.substring(0, 8)}</Badge>
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  Department: <strong className="text-slate-700">{selectedSubmission.department}</strong> ·
                  Submitted on {new Date(selectedSubmission.submitted_at).toLocaleString()}
                </p>
              </div>
              <button
                onClick={() => setSelectedSubmission(null)}
                className="text-slate-400 hover:text-slate-600 text-xl font-bold p-1 cursor-pointer"
              >
                ✕
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-6 overflow-y-auto space-y-5 text-xs">
              {/* Overall Score Banner */}
              <div className="p-3 bg-blue-50 border border-blue-100 rounded-xl flex items-center justify-between">
                <div>
                  <p className="font-semibold text-blue-900">Calculated Response Mean</p>
                  <p className="text-blue-700">Average rating across all Likert items in this survey</p>
                </div>
                <div className="text-2xl font-black text-blue-700">
                  {selectedSubmission.avg_score.toFixed(2)} <span className="text-xs font-normal">/ 5.0</span>
                </div>
              </div>

              {/* Categorical Metadata */}
              {(selectedSubmission.experience_range || selectedSubmission.bank_type || selectedSubmission.interaction_type || selectedSubmission.service_type) && (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 p-3 bg-slate-50 rounded-xl border border-slate-200">
                  {selectedSubmission.experience_range && (
                    <div><span className="text-slate-400 block">Experience:</span><strong>{selectedSubmission.experience_range} yrs</strong></div>
                  )}
                  {selectedSubmission.bank_type && (
                    <div><span className="text-slate-400 block">Bank Type:</span><strong className="capitalize">{selectedSubmission.bank_type}</strong></div>
                  )}
                  {selectedSubmission.interaction_type && (
                    <div><span className="text-slate-400 block">Channel:</span><strong className="capitalize">{selectedSubmission.interaction_type.replace('_', ' ')}</strong></div>
                  )}
                  {selectedSubmission.service_type && (
                    <div><span className="text-slate-400 block">Service:</span><strong className="capitalize">{selectedSubmission.service_type.replace('_', ' ')}</strong></div>
                  )}
                </div>
              )}

              {/* Questions & Submitted Answers */}
              <div>
                <h4 className="font-bold text-slate-800 text-sm mb-2.5">Detailed Answers Submitted</h4>
                <div className="space-y-2">
                  {Object.entries(selectedSubmission.scores || {}).map(([key, val]) => {
                    const qInfo = SURVEY_QUESTIONS[key]
                    return (
                      <div key={key} className="p-2.5 rounded-lg border border-slate-100 bg-slate-50 flex items-center justify-between gap-3">
                        <div className="flex-1">
                          <span className="font-mono font-bold text-slate-700 mr-2">{key.toUpperCase()}:</span>
                          <span className="text-slate-600">{qInfo?.question || key}</span>
                        </div>
                        <div className="shrink-0 text-right">
                          <span className={`inline-block px-2.5 py-1 rounded-md font-bold text-xs ${
                            val >= 4 ? 'bg-green-100 text-green-800' :
                            val === 3 ? 'bg-amber-100 text-amber-800' :
                            'bg-red-100 text-red-800'
                          }`}>
                            {LIKERT_TEXT[val] || val}
                          </span>
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>

              {/* Open Feedback / Text Responses */}
              {selectedSubmission.open_feedback && (
                <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl">
                  <h4 className="font-semibold text-slate-800 mb-1">Qualitative Feedback / Reported Metrics</h4>
                  <p className="text-slate-700 italic">&ldquo;{selectedSubmission.open_feedback}&rdquo;</p>
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-3 border-t border-slate-100 bg-slate-50 flex justify-end">
              <Button size="sm" variant="secondary" onClick={() => setSelectedSubmission(null)}>
                Close Audit View
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* ── Correlation Analysis ── */}
      <Card className="mb-6">
        <SectionHeading
          title="Pre-specified Correlation Analyses"
          description="Pairwise correlation analyses testing technology adoption against satisfaction and performance."
        />
        {loading ? <Skeleton className="h-32" /> : <CorrelationTable correlations={corrData ?? []} />}
      </Card>

      {/* ── OLS Regression Models ── */}
      <Card className="mb-6">
        <SectionHeading
          title="OLS Regression Models"
          description="Ordinary Least Squares regression models. Associative findings derived from stakeholder survey scores."
        />
        {loading ? <Skeleton className="h-28" /> : <RegressionTable models={regData ?? []} />}
      </Card>

      {/* ── Missing values report ── */}
      <Card>
        <SectionHeading
          title="Missing-Value Analysis Report"
          description="Documentation of survey question completeness. No artificial imputation is applied."
        />
        {loading ? <Skeleton className="h-24" /> : (
          missingData ? <MissingTable data={missingData} /> : <EmptyState message="No data." />
        )}
      </Card>
    </PageShell>
  )
}
