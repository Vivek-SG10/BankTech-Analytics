import { Link } from 'react-router-dom'
import { useAuth } from '../context/useAuth'
import { Card } from '../components/ui'

const FEATURES = [
  {
    icon: '📊',
    title: 'Sentiment Analytics',
    description:
      'Analyse employee and customer sentiment across banking touchpoints using validated survey instruments and NLP-powered visualisations.',
  },
  {
    icon: '🤖',
    title: 'AI FAQ Assistant',
    description:
      "A retrieval-augmented chatbot grounded in your organisation's policy documents, providing cited, auditable answers to banking queries.",
  },

  {
    icon: '🔍',
    title: 'Research Insights',
    description:
      'Explore aggregated, anonymised findings from multi-role stakeholder surveys to support evidence-based decision making.',
  },
]

const ROLES = [
  { role: 'Employee', desc: 'Complete surveys on workplace technology adoption and satisfaction.' },
  { role: 'Manager', desc: 'Report on digital transformation initiatives and team engagement.' },
  { role: 'Customer', desc: 'Share your experience with digital banking services and support.' },
  { role: 'Researcher / Admin', desc: 'Access aggregated analytics, methodology, and raw findings.' },
]

export default function LandingPage() {
  const { isAuthenticated } = useAuth()

  return (
    <div className="bg-white">
      {/* ── Hero ── */}
      <section className="relative bg-gradient-to-br from-blue-900 via-blue-800 to-blue-700 text-white overflow-hidden">
        <div className="absolute inset-0 opacity-10 bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-white via-transparent to-transparent pointer-events-none" />
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-24 sm:py-32 text-center relative">
          <span className="inline-block mb-4 px-4 py-1.5 rounded-full bg-blue-600/40 border border-blue-400/30 text-blue-200 text-sm font-medium tracking-wide">
            Academic Research Project · 2024
          </span>
          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-extrabold leading-tight tracking-tight mb-6">
            BankTech Analytics
          </h1>
          <p className="text-xl sm:text-2xl font-light text-blue-100 mb-4 max-w-2xl mx-auto">
            Understanding the Impact of Financial Technology on Banking Stakeholders
          </p>
          <p className="text-base text-blue-200 max-w-xl mx-auto mb-10 leading-relaxed">
            This platform collects structured survey data from bank employees, managers, and
            customers to study fintech adoption, sentiment, and service quality—supporting
            evidence-based research and policy recommendations.
          </p>
          <div className="flex flex-col sm:flex-row justify-center gap-4">
            {isAuthenticated ? (
              <Link
                to="/dashboard"
                className="px-8 py-3 rounded-xl bg-white text-blue-800 font-semibold text-lg shadow-lg hover:shadow-xl hover:-translate-y-0.5 transition-all"
              >
                Go to Dashboard →
              </Link>
            ) : (
              <>
                <Link
                  to="/register"
                  className="px-8 py-3 rounded-xl bg-white text-blue-800 font-semibold text-lg shadow-lg hover:shadow-xl hover:-translate-y-0.5 transition-all"
                >
                  Participate in Research
                </Link>
                <Link
                  to="/login"
                  className="px-8 py-3 rounded-xl bg-blue-600/40 text-white font-semibold text-lg border border-blue-400/40 hover:bg-blue-600/60 transition"
                >
                  Sign In
                </Link>
              </>
            )}
          </div>
        </div>
      </section>

      {/* ── Feature Cards ── */}
      <section className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-20">
        <div className="text-center mb-12">
          <h2 className="text-3xl font-bold text-slate-900 mb-3">Platform Features</h2>
          <p className="text-slate-500 max-w-xl mx-auto">
            A purpose-built research tool combining rigorous survey collection with intelligent analytics.
          </p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {FEATURES.map(f => (
            <Card key={f.title} className="text-center hover:shadow-md transition-shadow">
              <div className="text-5xl mb-4">{f.icon}</div>
              <h3 className="text-lg font-bold text-slate-900 mb-2">{f.title}</h3>
              <p className="text-sm text-slate-600 leading-relaxed">{f.description}</p>
            </Card>
          ))}
        </div>
      </section>

      {/* ── Participant Roles ── */}
      <section className="bg-slate-50 border-y border-slate-200">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-20">
          <div className="text-center mb-12">
            <h2 className="text-3xl font-bold text-slate-900 mb-3">Who Can Participate?</h2>
            <p className="text-slate-500 max-w-xl mx-auto">
              The study involves four stakeholder groups, each with a tailored experience.
            </p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
            {ROLES.map(r => (
              <div key={r.role} className="flex items-start gap-4 bg-white rounded-xl p-5 border border-slate-200 shadow-sm">
                <span className="mt-0.5 h-8 w-8 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center font-bold text-sm shrink-0">
                  {r.role[0]}
                </span>
                <div>
                  <p className="font-semibold text-slate-900 text-sm">{r.role}</p>
                  <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">{r.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Ethics & Data notice ── */}
      <section className="max-w-3xl mx-auto px-4 py-16 text-center">
        <p className="text-sm text-slate-500 leading-relaxed">
          All data is collected with informed consent, stored securely, and analysed in aggregate.
          Individual responses are never disclosed. This research follows institutional ethics guidelines.{' '}
          <Link to="/privacy" className="text-blue-600 hover:underline">Privacy policy →</Link>
        </p>
      </section>
    </div>
  )
}
