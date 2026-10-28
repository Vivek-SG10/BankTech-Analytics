import type {
  LoginCredentials,
  RegisterPayload,
  AuthTokenResponse,
  HealthResponse,
  SurveySubmission,
  AskRequest,
  AskResponse,
  User,
  UserRole,
  EmployeeSurveyPayload,
  ManagerSurveyPayload,
  CustomerSurveyPayload,
  SurveySubmitResponse,
  SubmissionSummary,
  AnalyticsSummary,
  AnalyticsFilters,
  IndexResult,
  DescriptiveStat,
  CorrelationResult,
  RegressionResult,
} from '../types'


// Base URL comes from env var; falls back to same-origin (proxy handles /api).
const BASE_URL = import.meta.env.VITE_API_URL
  ? `${import.meta.env.VITE_API_URL}/api/v1`
  : '/api/v1'

// ── Helpers ───────────────────────────────────────────────────────────────

function getAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem('bt_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
      ...(options.headers as Record<string, string> | undefined),
    },
    ...options,
  })

  if (!res.ok) {
    let detail = `HTTP ${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      detail = body.detail ?? detail
    } catch {
      // ignore parse failure
    }
    throw new Error(detail)
  }

  // 204 No Content
  if (res.status === 204) return undefined as unknown as T
  return res.json() as Promise<T>
}

/** Build a query string from a filters object, omitting undefined/null/empty values. */
function buildQuery(filters: Record<string, string | undefined | null>): string {
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(filters)) {
    if (v != null && v !== '') params.set(k, v)
  }
  const s = params.toString()
  return s ? `?${s}` : ''
}

// ── Health ────────────────────────────────────────────────────────────────

export const healthApi = {
  get: () => request<HealthResponse>('/health'),
}

// ── Auth ──────────────────────────────────────────────────────────────────

export const authApi = {
  login: (creds: LoginCredentials) =>
    request<AuthTokenResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify(creds),
    }),

  register: (payload: RegisterPayload) =>
    request<AuthTokenResponse>('/auth/register', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  me: () => request<AuthTokenResponse['user']>('/auth/me'),

  logout: () => {
    // Fire-and-forget — client clears state regardless of network result
    void fetch(`${BASE_URL}/auth/logout`, { method: 'POST' }).catch(() => undefined)
    localStorage.removeItem('bt_token')
    localStorage.removeItem('bt_user')
  },
}

// ── Admin user-management ────────────────────────────────────────────────────

export const adminApi = {
  listUsers: () =>
    request<User[]>('/auth/users'),

  setRole: (userId: string, role: UserRole) =>
    request<User>(`/auth/users/${userId}/role`, {
      method: 'PATCH',
      body: JSON.stringify({ role }),
    }),

  setActive: (userId: string, is_active: boolean) =>
    request<User>(`/auth/users/${userId}/active`, {
      method: 'PATCH',
      body: JSON.stringify({ is_active }),
    }),

  seedDemoAccounts: () =>
    request<User[]>('/dev/seed', { method: 'POST' }),
}


// ── Surveys ───────────────────────────────────────────────────────────────

export const surveyApi = {
  /** Legacy generic submit — kept for compatibility */
  submit: (submission: SurveySubmission) =>
    request<{ id: string; message: string }>('/surveys', {
      method: 'POST',
      body: JSON.stringify(submission),
    }),

  /** Role-specific typed submission endpoints */
  submitEmployee: (payload: EmployeeSurveyPayload) =>
    request<SurveySubmitResponse>('/surveys/employee', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  submitManager: (payload: ManagerSurveyPayload) =>
    request<SurveySubmitResponse>('/surveys/manager', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  submitCustomer: (payload: CustomerSurveyPayload) =>
    request<SurveySubmitResponse>('/surveys/customer', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  /** List authenticated user's own submissions */
  listMine: () =>
    request<SubmissionSummary[]>('/surveys/mine'),
}

// ── Analytics ─────────────────────────────────────────────────────────────

export const analyticsApi = {
  /** Dashboard summary cards — lightweight */
  getSummary: (filters: AnalyticsFilters = {}) =>
    request<AnalyticsSummary>(`/analytics/summary${buildQuery(filters)}`),

  getOverview: (filters: AnalyticsFilters = {}) =>
    request<{
      employee_responses: number
      manager_responses: number
      customer_responses: number
    }>(`/analytics/overview${buildQuery(filters)}`),

  getTai: (filters: AnalyticsFilters = {}) =>
    request<{ TAI_employee: IndexResult; TAI_manager: IndexResult; methodology: string }>(
      `/analytics/tai${buildQuery(filters)}`
    ),

  getEjsi: (filters: AnalyticsFilters = {}) =>
    request<{ EJSI: IndexResult; methodology: string }>(
      `/analytics/ejsi${buildQuery(filters)}`
    ),

  getEpi: (filters: AnalyticsFilters = {}) =>
    request<{ EPI_manager: IndexResult; EPI_self: IndexResult; methodology: string }>(
      `/analytics/epi${buildQuery(filters)}`
    ),

  getCsei: (filters: AnalyticsFilters = {}) =>
    request<{ CSEI: IndexResult; methodology: string }>(
      `/analytics/csei${buildQuery(filters)}`
    ),

  getDescriptive: (filters: AnalyticsFilters = {}) =>
    request<{ items: DescriptiveStat[]; n_employee: number; n_manager: number; n_customer: number }>(
      `/analytics/descriptive${buildQuery(filters)}`
    ),

  getMissing: (filters: AnalyticsFilters = {}) =>
    request<Record<string, unknown>>(`/analytics/missing${buildQuery(filters)}`),

  getCorrelations: (filters: AnalyticsFilters = {}) =>
    request<{ correlations: CorrelationResult[]; caution: string }>(
      `/analytics/correlations${buildQuery(filters)}`
    ),

  getRegression: (filters: AnalyticsFilters = {}) =>
    request<{ models: RegressionResult[]; caution: string }>(
      `/analytics/regression${buildQuery(filters)}`
    ),

  /** Returns a download URL for the CSV export (GET with auth header). */
  getCsvExportUrl: (filters: AnalyticsFilters = {}) => {
    const q = buildQuery(filters)
    return `${BASE_URL}/analytics/export/csv${q}`
  },

  /** Trigger a CSV download by fetching with auth header and creating a blob URL. */
  downloadCsv: async (filters: AnalyticsFilters = {}) => {
    const url = `${BASE_URL}/analytics/export/csv${buildQuery(filters)}`
    const res = await fetch(url, { headers: getAuthHeaders() })
    if (!res.ok) throw new Error(`Export failed: HTTP ${res.status}`)
    const blob = await res.blob()
    const blobUrl = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = blobUrl
    a.download = 'banktech_analytics_export.csv'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(blobUrl)
  },

  // Legacy stubs (kept to avoid breaking existing imports that use these names)
  getSentiment: () => Promise.resolve(null),
  getTrends:    () => Promise.resolve(null),
  getTopics:    () => Promise.resolve(null),
}

// ── RAG / FAQ ─────────────────────────────────────────────────────────────

export const ragApi = {
  ask: (payload: AskRequest) =>
    request<AskResponse>('/rag/ask', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
}
