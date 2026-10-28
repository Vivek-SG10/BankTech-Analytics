// ── User & Auth ───────────────────────────────────────────────────────────

export type UserRole = 'admin' | 'researcher' | 'manager' | 'employee' | 'customer'
/** Roles a user may select during self-registration (admin/researcher require admin grant). */
export type SelfRegisterRole = 'manager' | 'employee' | 'customer'

export interface User {
  id: string
  name: string
  email: string
  role: UserRole
  department?: string | null
  is_active: boolean
}

export interface AuthState {
  user: User | null
  token: string | null
  isAuthenticated: boolean
  isLoading: boolean
}

export interface LoginCredentials {
  email: string
  password: string
}

export interface RegisterPayload {
  name: string
  email: string
  password: string
  role: SelfRegisterRole
  department?: string
}

export interface AuthTokenResponse {
  access_token: string
  token_type: string
  user: User
}

// ── API Helpers ───────────────────────────────────────────────────────────

export interface ApiError {
  detail: string
  status?: number
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  size: number
}

// ── Health ────────────────────────────────────────────────────────────────

export interface HealthResponse {
  status: string
  service: string
  database: 'ok' | 'unreachable'
  database_latency_ms: number | null
  timestamp: string
}

// ── Surveys ───────────────────────────────────────────────────────────────

export type LikertScale = 1 | 2 | 3 | 4 | 5
export type ExperienceRange = '0-1' | '2-5' | '6-10' | '11+'
export type BankType = 'retail' | 'commercial' | 'investment' | 'Islamic' | 'cooperative'
export type InteractionType = 'branch_visit' | 'phone' | 'digital_channel' | 'other'
export type ServiceType = 'account_enquiry' | 'transaction' | 'complaint' | 'digital_onboarding' | 'other'

export interface SurveyQuestion {
  id: string
  text: string
  type: 'likert' | 'text' | 'select'
  options?: string[]
  required: boolean
}

export interface SurveyResponse {
  questionId: string
  answer: string | number
}

/** Legacy shape kept for backward compatibility with RouteGuards */
export interface SurveySubmission {
  surveyType: 'employee' | 'manager' | 'customer'
  responses: SurveyResponse[]
  submittedAt?: string
}

// ── Survey request payloads (matches backend Pydantic schemas exactly) ─────

export interface EmployeeSurveyPayload {
  tai_1: LikertScale; tai_2: LikertScale; tai_3: LikertScale; tai_4: LikertScale; tai_5: LikertScale
  ejsi_1: LikertScale; ejsi_2: LikertScale; ejsi_3: LikertScale
  ejsi_4: LikertScale; ejsi_5: LikertScale; ejsi_6: LikertScale
  epi_s_1: LikertScale; epi_s_2: LikertScale; epi_s_3: LikertScale
  open_challenges?: string
  experience_range?: ExperienceRange
  bank_type?: BankType
}

export interface ManagerSurveyPayload {
  tai_mgr_1: LikertScale; tai_mgr_2: LikertScale; tai_mgr_3: LikertScale
  epi_m_1: LikertScale; epi_m_2: LikertScale; epi_m_3: LikertScale; epi_m_4: LikertScale
  avg_resolution_min?: number
  digital_adoption_pct?: number
  team_size?: number
  experience_range?: ExperienceRange
  bank_type?: BankType
}

export interface CustomerSurveyPayload {
  interaction_type: InteractionType
  service_type: ServiceType
  csei_1: LikertScale; csei_2: LikertScale; csei_3: LikertScale
  csei_4: LikertScale; csei_5: LikertScale; csei_6: LikertScale
  open_feedback?: string
}

export interface SurveySubmitResponse {
  id: string
  respondent_id: string
  submitted_at: string
  message: string
}

export interface SubmissionSummary {
  id: string
  survey_type: 'employee' | 'manager' | 'customer'
  submitted_at: string
  is_voided: boolean
}

// ── Analytics API response types ──────────────────────────────────────────

export interface IndexResult {
  name: string
  n: number
  score_pct: number | null
  mean_raw: number | null
  sd: number | null
  cronbach_alpha: number | null
  items: string[]
  warning: string | null
}

export interface DescriptiveStat {
  item: string
  label: string
  n: number
  mean: number | null
  median: number | null
  sd: number | null
  iqr: number | null
  skewness: number | null
  kurtosis: number | null
}

export interface CorrelationResult {
  label: string          // combined display label (x_label ↔ y_label)
  x_label: string
  y_label: string
  n: number
  r: number | null
  p_value: number | null
  method: string
  significant: boolean | null
  suppressed: boolean
  note: string
}

export interface RegressionResult {
  outcome: string
  predictors: string[]
  n: number
  r_squared: number | null
  adj_r_squared: number | null
  f_statistic: number | null
  f_p_value: number | null
  coefficients: Record<string, unknown>
  suppressed: boolean
  note: string
}

export interface AnalyticsSummary {
  response_counts: { employee: number; manager: number; customer: number; total: number }
  index_scores: { TAI_employee: number | null; EJSI: number | null; EPI_manager: number | null; CSEI: number | null }
  suppression_notes: Record<string, string | null>
  data_label: string
}

export interface AnalyticsFilters {
  department?: string
  from_date?: string
  to_date?: string
  bank_type?: string
  experience_range?: string
  [key: string]: string | undefined
}

// ── RAG / FAQ ─────────────────────────────────────────────────────────────

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources?: string[]
  isLoading?: boolean
  isFallback?: boolean
  timestamp: Date
}

export interface AskRequest {
  question: string
  conversation_id?: string
}

export interface AskResponse {
  answer: string
  sources: string[]
  is_fallback: boolean
  conversation_id: string
}

// ── Chart helpers ─────────────────────────────────────────────────────────

export interface ChartDataPoint {
  label: string
  value: number
  [key: string]: string | number
}

export interface SentimentData {
  category: string
  positive: number
  neutral: number
  negative: number
}

export interface TrendPoint {
  period: string
  score: number
  count: number
}
