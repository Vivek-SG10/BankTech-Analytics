/**
 * SurveyPage — role-aware survey form connected to the backend.
 *
 * Employees   → POST /api/v1/surveys/employee
 * Managers    → POST /api/v1/surveys/manager  (+ optional operational metrics)
 * Customers   → POST /api/v1/surveys/customer
 *
 * Re-submission is allowed; the backend voids the previous response and records
 * the latest one. The UI shows a "previous submission detected" notice when
 * /surveys/mine reports an existing non-voided entry.
 *
 * Likert scale:  1 = Strongly Disagree … 5 = Strongly Agree
 * Required items are validated client-side before submission.
 * Server-side validation errors (422) surface as field-level messages.
 */
import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/useAuth'
import { surveyApi } from '../services/api'
import { Card, Alert, Button } from '../components/ui'
import { PageShell } from '../components/Layout'
import type {
  EmployeeSurveyPayload,
  ManagerSurveyPayload,
  CustomerSurveyPayload,
  LikertScale,
  ExperienceRange,
  BankType,
  InteractionType,
  ServiceType,
  SubmissionSummary,
} from '../types'

// ── Likert scale component ────────────────────────────────────────────────────

const LIKERT_LABELS: Record<number, string> = {
  1: 'Strongly\nDisagree',
  2: 'Disagree',
  3: 'Neutral',
  4: 'Agree',
  5: 'Strongly\nAgree',
}

function LikertField({
  label,
  value,
  onChange,
  required = true,
  hasError = false,
}: {
  name: string
  label: string
  value: number | null
  onChange: (v: LikertScale) => void
  required?: boolean
  hasError?: boolean
}) {
  return (
    <div className={`${hasError ? 'pl-3 border-l-4 border-red-400' : ''}`}>
      <p className="text-sm font-medium text-slate-700 mb-3">
        {label}
        {required && <span className="text-red-500 ml-1">*</span>}
      </p>
      <div className="flex gap-2">
        {([1, 2, 3, 4, 5] as LikertScale[]).map(v => (
          <button
            key={v}
            type="button"
            onClick={() => onChange(v)}
            className={`
              flex-1 py-2.5 rounded-lg border text-xs font-medium transition-all
              ${value === v
                ? 'bg-blue-600 border-blue-600 text-white shadow-sm'
                : 'bg-white border-slate-200 text-slate-600 hover:border-blue-300 hover:bg-blue-50'}
            `}
          >
            <div className="text-base font-bold mb-0.5">{v}</div>
            <div className="whitespace-pre-line leading-tight hidden sm:block">{LIKERT_LABELS[v]}</div>
          </button>
        ))}
      </div>
      {hasError && <p className="text-xs text-red-500 mt-1">This question is required.</p>}
    </div>
  )
}

// ── Select field ─────────────────────────────────────────────────────────────

function SelectField<T extends string>({
  label,
  value,
  onChange,
  options,
  required = false,
  hasError = false,
}: {
  label: string
  value: T | ''
  onChange: (v: T) => void
  options: { value: T; label: string }[]
  required?: boolean
  hasError?: boolean
}) {
  return (
    <div>
      <label className="block text-sm font-medium text-slate-700 mb-1.5">
        {label}
        {required && <span className="text-red-500 ml-1">*</span>}
      </label>
      <select
        value={value}
        onChange={e => onChange(e.target.value as T)}
        className={`
          w-full rounded-lg border px-3 py-2 text-sm text-slate-700 bg-white
          focus:outline-none focus:ring-2 focus:ring-blue-500
          ${hasError ? 'border-red-400' : 'border-slate-300'}
        `}
      >
        <option value="">Select…</option>
        {options.map(o => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
      {hasError && <p className="text-xs text-red-500 mt-1">This field is required.</p>}
    </div>
  )
}

// ── Number field (optional metrics) ──────────────────────────────────────────

function NumberField({
  label,
  hint,
  value,
  onChange,
  min,
  max,
  step = 1,
}: {
  label: string
  hint?: string
  value: number | ''
  onChange: (v: number | '') => void
  min?: number
  max?: number
  step?: number
}) {
  return (
    <div>
      <label className="block text-sm font-medium text-slate-700 mb-1">
        {label}
        <span className="text-slate-400 font-normal ml-1">(optional)</span>
      </label>
      {hint && <p className="text-xs text-slate-500 mb-1.5">{hint}</p>}
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={e => onChange(e.target.value === '' ? '' : Number(e.target.value))}
        className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-700
                   focus:outline-none focus:ring-2 focus:ring-blue-500"
        placeholder="—"
      />
    </div>
  )
}

// ── Text area ─────────────────────────────────────────────────────────────────

function TextArea({
  label,
  value,
  onChange,
  maxLength,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  maxLength?: number
}) {
  return (
    <div>
      <label className="block text-sm font-medium text-slate-700 mb-1">
        {label}
        <span className="text-slate-400 font-normal ml-1">(optional)</span>
      </label>
      <textarea
        value={value}
        onChange={e => onChange(e.target.value)}
        maxLength={maxLength}
        rows={3}
        className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-700
                   focus:outline-none focus:ring-2 focus:ring-blue-500 resize-y"
        placeholder="Your response…"
      />
      {maxLength && (
        <p className="text-xs text-slate-400 mt-0.5 text-right">{value.length}/{maxLength}</p>
      )}
    </div>
  )
}

// ── Section heading ───────────────────────────────────────────────────────────

function SectionHeading({ letter, title, description }: { letter: string; title: string; description: string }) {
  return (
    <div className="flex items-start gap-3 pb-2 border-b border-slate-100 mb-4">
      <span className="flex-shrink-0 w-8 h-8 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-sm font-bold">
        {letter}
      </span>
      <div>
        <h3 className="text-sm font-semibold text-slate-800">{title}</h3>
        <p className="text-xs text-slate-500">{description}</p>
      </div>
    </div>
  )
}

// ── Previous submission notice ─────────────────────────────────────────────────

function PreviousSubmissionNotice({ submission }: { submission: SubmissionSummary }) {
  const d = new Date(submission.submitted_at).toLocaleDateString('en-GB', {
    day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  })
  return (
    <Alert type="info">
      <strong>Previous submission detected</strong> — submitted on {d}.
      You may submit again; your previous response will be replaced for research purposes.
    </Alert>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// Employee Survey
// ══════════════════════════════════════════════════════════════════════════════

function EmployeeSurveyForm({ onSuccess }: { onSuccess: () => void }) {
  const [tai, setTai] = useState<Partial<Record<string, LikertScale>>>({})
  const [ejsi, setEjsi] = useState<Partial<Record<string, LikertScale>>>({})
  const [epi, setEpi] = useState<Partial<Record<string, LikertScale>>>({})
  const [openText, setOpenText] = useState('')
  const [expRange, setExpRange] = useState<ExperienceRange | ''>('')
  const [bankType, setBankType] = useState<BankType | ''>('')
  const [errors, setErrors] = useState<Set<string>>(new Set())
  const [isLoading, setIsLoading] = useState(false)
  const [apiError, setApiError] = useState<string | null>(null)

  const TAI_ITEMS: { key: string; text: string }[] = [
    { key: 'tai_1', text: 'The digital banking tools I use daily are easy to operate.' },
    { key: 'tai_2', text: 'Using digital tools makes my daily tasks more efficient.' },
    { key: 'tai_3', text: 'I receive sufficient training to use banking technology confidently.' },
    { key: 'tai_4', text: 'I regularly use digital tools for customer-facing tasks.' },
    { key: 'tai_5', text: 'Technology enables me to resolve customer queries more quickly.' },
  ]
  const EJSI_ITEMS = [
    { key: 'ejsi_1', text: 'Overall, I am satisfied with my current role.' },
    { key: 'ejsi_2', text: 'I feel valued as an employee of this organisation.' },
    { key: 'ejsi_3', text: 'I am satisfied with the support I receive from my manager.' },
    { key: 'ejsi_4', text: 'My workload is manageable within normal working hours.' },
    { key: 'ejsi_5', text: 'My work is meaningful and contributes to organisational goals.' },
    { key: 'ejsi_6', text: 'I would recommend this organisation as a good place to work.' },
  ]
  const EPI_ITEMS = [
    { key: 'epi_s_1', text: 'I consistently meet my individual performance targets.' },
    { key: 'epi_s_2', text: 'I handle customer queries and complaints effectively.' },
    { key: 'epi_s_3', text: 'I collaborate effectively with colleagues to achieve team goals.' },
  ]

  const allRequired = [...TAI_ITEMS, ...EJSI_ITEMS, ...EPI_ITEMS]

  function validate(): boolean {
    const missing = new Set<string>()
    for (const item of TAI_ITEMS)  if (!tai[item.key])  missing.add(item.key)
    for (const item of EJSI_ITEMS) if (!ejsi[item.key]) missing.add(item.key)
    for (const item of EPI_ITEMS)  if (!epi[item.key])  missing.add(item.key)
    setErrors(missing)
    return missing.size === 0
  }

  const progress = Math.round(
    (Object.keys({ ...tai, ...ejsi, ...epi }).filter(k =>
      allRequired.some(i => i.key === k)
    ).length / allRequired.length) * 100
  )

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setApiError(null)
    if (!validate()) { setApiError('Please answer all required questions.'); return }
    setIsLoading(true)
    try {
      const payload: EmployeeSurveyPayload = {
        tai_1: tai.tai_1!, tai_2: tai.tai_2!, tai_3: tai.tai_3!,
        tai_4: tai.tai_4!, tai_5: tai.tai_5!,
        ejsi_1: ejsi.ejsi_1!, ejsi_2: ejsi.ejsi_2!, ejsi_3: ejsi.ejsi_3!,
        ejsi_4: ejsi.ejsi_4!, ejsi_5: ejsi.ejsi_5!, ejsi_6: ejsi.ejsi_6!,
        epi_s_1: epi.epi_s_1!, epi_s_2: epi.epi_s_2!, epi_s_3: epi.epi_s_3!,
        open_challenges: openText || undefined,
        experience_range: expRange || undefined,
        bank_type: bankType || undefined,
      }
      await surveyApi.submitEmployee(payload)
      onSuccess()
    } catch (err: unknown) {
      setApiError(err instanceof Error ? err.message : 'Submission failed.')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <Card>
        <SectionHeading letter="A" title="Technology Adoption"
          description="How do you experience digital banking tools in your daily work? (TAI — Technology Adoption Index)" />
        <div className="space-y-6">
          {TAI_ITEMS.map(item => (
            <LikertField key={item.key} name={item.key} label={item.text}
              value={tai[item.key] ?? null}
              onChange={v => { setTai(p => ({ ...p, [item.key]: v })); setErrors(p => { const s = new Set(p); s.delete(item.key); return s }) }}
              hasError={errors.has(item.key)} />
          ))}
        </div>
      </Card>

      <Card>
        <SectionHeading letter="B" title="Job Satisfaction"
          description="How satisfied are you with your role? (EJSI — Employee Job Satisfaction Index)" />
        <div className="space-y-6">
          {EJSI_ITEMS.map(item => (
            <LikertField key={item.key} name={item.key} label={item.text}
              value={ejsi[item.key] ?? null}
              onChange={v => { setEjsi(p => ({ ...p, [item.key]: v })); setErrors(p => { const s = new Set(p); s.delete(item.key); return s }) }}
              hasError={errors.has(item.key)} />
          ))}
        </div>
      </Card>

      <Card>
        <SectionHeading letter="C" title="Self-assessed Performance"
          description="How do you rate your own performance? (EPI — Employee Performance Index, self-report)" />
        <div className="space-y-6">
          {EPI_ITEMS.map(item => (
            <LikertField key={item.key} name={item.key} label={item.text}
              value={epi[item.key] ?? null}
              onChange={v => { setEpi(p => ({ ...p, [item.key]: v })); setErrors(p => { const s = new Set(p); s.delete(item.key); return s }) }}
              hasError={errors.has(item.key)} />
          ))}
        </div>
        <p className="text-xs text-slate-400 mt-4 border-t border-slate-100 pt-3">
          Note: Self-assessed performance is reported separately from supervisor assessments and is never aggregated with manager ratings in the research analysis.
        </p>
      </Card>

      <Card>
        <SectionHeading letter="D" title="About You"
          description="Optional background information to help with research analysis (does not identify you)." />
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
          <SelectField<ExperienceRange>
            label="Years of banking experience"
            value={expRange}
            onChange={setExpRange}
            options={[
              { value: '0-1', label: 'Less than 1 year' },
              { value: '2-5', label: '2–5 years' },
              { value: '6-10', label: '6–10 years' },
              { value: '11+', label: '11+ years' },
            ]}
          />
          <SelectField<BankType>
            label="Type of institution"
            value={bankType}
            onChange={setBankType}
            options={[
              { value: 'retail', label: 'Retail bank' },
              { value: 'commercial', label: 'Commercial bank' },
              { value: 'investment', label: 'Investment bank' },
              { value: 'Islamic', label: 'Islamic bank' },
              { value: 'cooperative', label: 'Cooperative / credit union' },
            ]}
          />
        </div>
        <TextArea
          label="Biggest technology challenges in your role"
          value={openText}
          onChange={setOpenText}
          maxLength={1000}
        />
      </Card>

      {apiError && <Alert type="error">{apiError}</Alert>}

      <ProgressBar progress={progress} answered={Object.values({ ...tai, ...ejsi, ...epi }).filter(Boolean).length} total={allRequired.length} />

      <div className="flex justify-end">
        <Button type="submit" isLoading={isLoading}
          className="bg-blue-600 hover:bg-blue-700 border-blue-600 text-white px-8">
          Submit Survey
        </Button>
      </div>
    </form>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// Manager Survey
// ══════════════════════════════════════════════════════════════════════════════

function ManagerSurveyForm({ onSuccess }: { onSuccess: () => void }) {
  const [tai, setTai] = useState<Partial<Record<string, LikertScale>>>({})
  const [epi, setEpi] = useState<Partial<Record<string, LikertScale>>>({})
  const [resolutionMin, setResolutionMin] = useState<number | ''>('')
  const [digitalPct, setDigitalPct] = useState<number | ''>('')
  const [teamSize, setTeamSize] = useState<number | ''>('')
  const [expRange, setExpRange] = useState<ExperienceRange | ''>('')
  const [bankType, setBankType] = useState<BankType | ''>('')
  const [errors, setErrors] = useState<Set<string>>(new Set())
  const [isLoading, setIsLoading] = useState(false)
  const [apiError, setApiError] = useState<string | null>(null)

  const TAI_ITEMS = [
    { key: 'tai_mgr_1', text: 'My team effectively uses the digital banking tools available.' },
    { key: 'tai_mgr_2', text: 'Technology adoption has improved my team\'s overall productivity.' },
    { key: 'tai_mgr_3', text: 'The technology training provided is adequate for my team\'s needs.' },
  ]
  const EPI_ITEMS = [
    { key: 'epi_m_1', text: 'My team members consistently meet their individual targets.' },
    { key: 'epi_m_2', text: 'My team handles customer queries and complaints effectively.' },
    { key: 'epi_m_3', text: 'My team adapts well to changes introduced by new technology.' },
    { key: 'epi_m_4', text: 'Overall, I rate my team\'s performance as:' },
  ]
  const allRequired = [...TAI_ITEMS, ...EPI_ITEMS]

  function validate(): boolean {
    const missing = new Set<string>()
    for (const item of TAI_ITEMS) if (!tai[item.key]) missing.add(item.key)
    for (const item of EPI_ITEMS) if (!epi[item.key]) missing.add(item.key)
    setErrors(missing)
    return missing.size === 0
  }

  const answered = Object.keys({ ...tai, ...epi }).filter(k => allRequired.some(i => i.key === k)).length
  const progress = Math.round((answered / allRequired.length) * 100)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setApiError(null)
    if (!validate()) { setApiError('Please answer all required questions.'); return }
    setIsLoading(true)
    try {
      const payload: ManagerSurveyPayload = {
        tai_mgr_1: tai.tai_mgr_1!, tai_mgr_2: tai.tai_mgr_2!, tai_mgr_3: tai.tai_mgr_3!,
        epi_m_1: epi.epi_m_1!, epi_m_2: epi.epi_m_2!,
        epi_m_3: epi.epi_m_3!, epi_m_4: epi.epi_m_4!,
        avg_resolution_min: resolutionMin !== '' ? resolutionMin : undefined,
        digital_adoption_pct: digitalPct !== '' ? digitalPct : undefined,
        team_size: teamSize !== '' ? teamSize : undefined,
        experience_range: expRange || undefined,
        bank_type: bankType || undefined,
      }
      await surveyApi.submitManager(payload)
      onSuccess()
    } catch (err: unknown) {
      setApiError(err instanceof Error ? err.message : 'Submission failed.')
    } finally {
      setIsLoading(false)
    }
  }

  const setL = (setter: typeof setTai, key: string) =>
    (v: LikertScale) => { setter(p => ({ ...p, [key]: v })); setErrors(p => { const s = new Set(p); s.delete(key); return s }) }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <Card>
        <SectionHeading letter="A" title="Technology Assessment"
          description="How does your team experience digital banking tools? (Contributes to TAI — Technology Adoption Index)" />
        <div className="space-y-6">
          {TAI_ITEMS.map(item => (
            <LikertField key={item.key} name={item.key} label={item.text}
              value={tai[item.key] ?? null} onChange={setL(setTai, item.key)}
              hasError={errors.has(item.key)} />
          ))}
        </div>
      </Card>

      <Card>
        <SectionHeading letter="B" title="Team Performance Assessment"
          description="How would you rate your team's performance? (Contributes to EPI — Employee Performance Index)" />
        <div className="space-y-6">
          {EPI_ITEMS.map(item => (
            <LikertField key={item.key} name={item.key} label={item.text}
              value={epi[item.key] ?? null} onChange={setL(setEpi, item.key)}
              hasError={errors.has(item.key)} />
          ))}
        </div>
        <p className="text-xs text-slate-400 mt-4 border-t border-slate-100 pt-3">
          ⚠️ Please rate your <strong>team as a whole</strong>, not any individual employee.
          Individual staff member data must not be entered here.
        </p>
      </Card>

      <Card>
        <SectionHeading letter="C" title="Aggregated Operational Metrics"
          description="Optional branch-level figures only — not individual employee data." />
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <NumberField label="Mean resolution time (min)"
            hint="Average customer query resolution time for your team"
            value={resolutionMin} onChange={setResolutionMin} min={0} step={0.5} />
          <NumberField label="Digital adoption (%)"
            hint="% of transactions via digital channels this month"
            value={digitalPct} onChange={setDigitalPct} min={0} max={100} />
          <NumberField label="Team size"
            hint="Number of direct reports"
            value={teamSize} onChange={setTeamSize} min={1} max={500} />
        </div>
        <p className="text-xs text-slate-400 mt-3">
          These fields are optional. Only enter branch-level aggregates you have on hand.
        </p>
      </Card>

      <Card>
        <SectionHeading letter="D" title="About You"
          description="Optional — helps with research analysis without identifying you." />
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <SelectField<ExperienceRange>
            label="Years of managerial experience"
            value={expRange} onChange={setExpRange}
            options={[
              { value: '0-1', label: 'Less than 1 year' },
              { value: '2-5', label: '2–5 years' },
              { value: '6-10', label: '6–10 years' },
              { value: '11+', label: '11+ years' },
            ]}
          />
          <SelectField<BankType>
            label="Type of institution"
            value={bankType} onChange={setBankType}
            options={[
              { value: 'retail', label: 'Retail bank' },
              { value: 'commercial', label: 'Commercial bank' },
              { value: 'investment', label: 'Investment bank' },
              { value: 'Islamic', label: 'Islamic bank' },
              { value: 'cooperative', label: 'Cooperative / credit union' },
            ]}
          />
        </div>
      </Card>

      {apiError && <Alert type="error">{apiError}</Alert>}
      <ProgressBar progress={progress} answered={answered} total={allRequired.length} />
      <div className="flex justify-end">
        <Button type="submit" isLoading={isLoading}
          className="bg-blue-600 hover:bg-blue-700 border-blue-600 text-white px-8">
          Submit Survey
        </Button>
      </div>
    </form>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// Customer Survey
// ══════════════════════════════════════════════════════════════════════════════

function CustomerSurveyForm({ onSuccess }: { onSuccess: () => void }) {
  const [interactionType, setInteractionType] = useState<InteractionType | ''>('')
  const [serviceType, setServiceType] = useState<ServiceType | ''>('')
  const [csei, setCsei] = useState<Partial<Record<string, LikertScale>>>({})
  const [openFeedback, setOpenFeedback] = useState('')
  const [errors, setErrors] = useState<Set<string>>(new Set())
  const [isLoading, setIsLoading] = useState(false)
  const [apiError, setApiError] = useState<string | null>(null)

  const CSEI_ITEMS = [
    { key: 'csei_1', text: 'The staff member who assisted me was knowledgeable about digital services.' },
    { key: 'csei_2', text: 'My query was resolved efficiently without unnecessary delays.' },
    { key: 'csei_3', text: 'I am satisfied with the overall quality of service I received.' },
    { key: 'csei_4', text: 'The staff member helped me understand or use digital banking channels.' },
    { key: 'csei_5', text: 'The service met my expectations.' },
    { key: 'csei_6', text: 'I would recommend this branch to friends or family.' },
  ]

  function validate(): boolean {
    const missing = new Set<string>()
    if (!interactionType) missing.add('interaction_type')
    if (!serviceType) missing.add('service_type')
    for (const item of CSEI_ITEMS) if (!csei[item.key]) missing.add(item.key)
    setErrors(missing)
    return missing.size === 0
  }

  const answered = CSEI_ITEMS.filter(i => csei[i.key]).length
  const progress = Math.round(((answered + (interactionType ? 1 : 0) + (serviceType ? 1 : 0)) / (CSEI_ITEMS.length + 2)) * 100)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setApiError(null)
    if (!validate()) { setApiError('Please answer all required questions.'); return }
    setIsLoading(true)
    try {
      const payload: CustomerSurveyPayload = {
        interaction_type: interactionType as InteractionType,
        service_type: serviceType as ServiceType,
        csei_1: csei.csei_1!, csei_2: csei.csei_2!, csei_3: csei.csei_3!,
        csei_4: csei.csei_4!, csei_5: csei.csei_5!, csei_6: csei.csei_6!,
        open_feedback: openFeedback || undefined,
      }
      await surveyApi.submitCustomer(payload)
      onSuccess()
    } catch (err: unknown) {
      setApiError(err instanceof Error ? err.message : 'Submission failed.')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <Card>
        <SectionHeading letter="A" title="Your Visit"
          description="Tell us about today's interaction." />
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <SelectField<InteractionType>
            label="How did you interact with us today?" required
            value={interactionType} onChange={setInteractionType}
            hasError={errors.has('interaction_type')}
            options={[
              { value: 'branch_visit', label: 'Branch visit' },
              { value: 'phone', label: 'Phone call' },
              { value: 'digital_channel', label: 'Digital channel (app/web)' },
              { value: 'other', label: 'Other' },
            ]}
          />
          <SelectField<ServiceType>
            label="What was the purpose of your visit?" required
            value={serviceType} onChange={setServiceType}
            hasError={errors.has('service_type')}
            options={[
              { value: 'account_enquiry', label: 'Account enquiry' },
              { value: 'transaction', label: 'Transaction' },
              { value: 'complaint', label: 'Complaint' },
              { value: 'digital_onboarding', label: 'Digital onboarding' },
              { value: 'other', label: 'Other' },
            ]}
          />
        </div>
      </Card>

      <Card>
        <SectionHeading letter="B" title="Service Quality"
          description="How was the service you received? (Contributes to CSEI — Customer Service Effectiveness Index)" />
        <p className="text-xs text-amber-600 bg-amber-50 rounded p-2 mb-4">
          ℹ️ Please rate the <strong>overall service quality</strong>, not any individual staff member.
          Staff member names should not be entered anywhere in this survey.
        </p>
        <div className="space-y-6">
          {CSEI_ITEMS.map(item => (
            <LikertField key={item.key} name={item.key} label={item.text}
              value={csei[item.key] ?? null}
              onChange={v => { setCsei(p => ({ ...p, [item.key]: v })); setErrors(p => { const s = new Set(p); s.delete(item.key); return s }) }}
              hasError={errors.has(item.key)} />
          ))}
        </div>
      </Card>

      <Card>
        <SectionHeading letter="C" title="Your Feedback"
          description="Optional comments — do not include names of staff members." />
        <TextArea
          label="Additional feedback"
          value={openFeedback}
          onChange={setOpenFeedback}
          maxLength={500}
        />
      </Card>

      {apiError && <Alert type="error">{apiError}</Alert>}
      <ProgressBar progress={progress} answered={answered} total={CSEI_ITEMS.length} />
      <div className="flex justify-end">
        <Button type="submit" isLoading={isLoading}
          className="bg-blue-600 hover:bg-blue-700 border-blue-600 text-white px-8">
          Submit Survey
        </Button>
      </div>
    </form>
  )
}

// ── Progress bar ──────────────────────────────────────────────────────────────

function ProgressBar({ progress, answered, total }: { progress: number; answered: number; total: number }) {
  return (
    <Card className="!py-3">
      <div className="flex justify-between text-xs text-slate-500 mb-2">
        <span>Progress</span>
        <span>{answered} / {total} required questions answered</span>
      </div>
      <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
        <div
          className="h-2 bg-blue-600 rounded-full transition-all duration-300"
          style={{ width: `${progress}%` }}
        />
      </div>
    </Card>
  )
}

// ── Confirmation screen ───────────────────────────────────────────────────────

function SubmissionConfirmed() {
  const navigate = useNavigate()
  return (
    <div className="max-w-xl mx-auto text-center py-16">
      <div className="w-20 h-20 rounded-full bg-green-100 flex items-center justify-center mx-auto mb-6">
        <svg className="w-10 h-10 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
        </svg>
      </div>
      <h2 className="text-2xl font-bold text-slate-900 mb-3">Thank you for participating!</h2>
      <p className="text-slate-600 mb-2">
        Your responses have been recorded and will be analysed anonymously alongside other participants.
      </p>
      <p className="text-sm text-slate-400 mb-8">
        All data is aggregated — your individual responses will not be published or attributed to you.
        Results will be published as part of the BankTech Analytics research project.
      </p>
      <div className="flex flex-col sm:flex-row justify-center gap-3">
        <button
          onClick={() => navigate('/dashboard')}
          className="px-6 py-2.5 rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700 transition"
        >
          Return to Dashboard
        </button>
        <button
          onClick={() => navigate('/faq')}
          className="px-6 py-2.5 rounded-lg border border-slate-300 text-slate-700 font-medium hover:bg-slate-50 transition"
        >
          Try the FAQ Assistant
        </button>
      </div>
    </div>
  )
}

// ── Root component ────────────────────────────────────────────────────────────

export default function SurveyPage() {
  const { user } = useAuth()
  const [submitted, setSubmitted] = useState(false)
  const [previousSubmission, setPreviousSubmission] = useState<SubmissionSummary | null>(null)
  const [loadingPrevious, setLoadingPrevious] = useState(true)

  const checkPreviousSubmission = useCallback(async () => {
    try {
      const submissions = await surveyApi.listMine()
      const active = submissions.find(s => !s.is_voided && s.survey_type === user?.role)
      setPreviousSubmission(active ?? null)
    } catch {
      // Not critical — survey can still be submitted
    } finally {
      setLoadingPrevious(false)
    }
  }, [user?.role])

  useEffect(() => {
    if (user) checkPreviousSubmission()
  }, [user, checkPreviousSubmission])

  if (submitted) {
    return (
      <PageShell title="Survey Complete">
        <SubmissionConfirmed />
      </PageShell>
    )
  }

  const TITLES: Record<string, string> = {
    employee: 'Employee Technology & Wellbeing Survey',
    manager:  'Manager Technology & Team Assessment Survey',
    customer: 'Customer Service Experience Survey',
  }
  const DESCRIPTIONS: Record<string, string> = {
    employee: 'Your responses help us understand how technology adoption affects employee performance and job satisfaction.',
    manager:  'Share your assessment of your team\'s technology adoption and performance. Rate your team as a whole — not individuals.',
    customer: 'Help us understand how technology affects your banking experience. No staff names are collected.',
  }

  const role = user?.role ?? 'employee'

  return (
    <PageShell
      title={TITLES[role] ?? 'Research Survey'}
      subtitle={DESCRIPTIONS[role]}
    >
      {/* Privacy notice */}
      <div className="mb-6 p-4 bg-blue-50 rounded-xl border border-blue-100 text-sm text-blue-800">
        <strong>🔒 Privacy:</strong> Your responses are anonymous and linked only to your respondent ID, not your name or email.
        All results are reported as aggregated statistics. Minimum group sizes are enforced before any results are published.
      </div>

      {loadingPrevious ? null : previousSubmission && (
        <div className="mb-6">
          <PreviousSubmissionNotice submission={previousSubmission} />
        </div>
      )}

      {role === 'employee' && <EmployeeSurveyForm onSuccess={() => setSubmitted(true)} />}
      {role === 'manager'  && <ManagerSurveyForm  onSuccess={() => setSubmitted(true)} />}
      {role === 'customer' && <CustomerSurveyForm onSuccess={() => setSubmitted(true)} />}

      {role !== 'employee' && role !== 'manager' && role !== 'customer' && (
        <Card>
          <p className="text-slate-500 text-sm">
            Survey submissions are available for employee, manager, and customer accounts.
            Your current role (<strong>{role}</strong>) does not have a survey assigned.
          </p>
        </Card>
      )}

      <p className="text-xs text-slate-400 text-center mt-8">
        * Required questions. BankTech Analytics Research Project.
      </p>
    </PageShell>
  )
}
