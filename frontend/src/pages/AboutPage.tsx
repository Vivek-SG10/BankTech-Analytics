import { Link } from 'react-router-dom'
import { Card } from '../components/ui'
import { PageShell } from '../components/Layout'

export default function AboutPage() {
  return (
    <PageShell title="About This Project" subtitle="BankTech Analytics — Academic Research Platform">
      <div className="max-w-3xl mx-auto space-y-6">
        <Card>
          <h2 className="text-lg font-bold text-slate-900 mb-3">Project Purpose</h2>
          <p className="text-sm text-slate-600 leading-relaxed">
            BankTech Analytics is an academic mini-project studying how financial technology
            adoption affects different banking stakeholders. The platform collects structured
            survey responses from bank employees, branch managers, and retail customers to
            generate evidence-based insights into digital transformation in the banking sector.
          </p>
          <p className="text-sm text-slate-600 leading-relaxed mt-3">
            The project is not affiliated with, endorsed by, or operated on behalf of any
            commercial bank. All participation is voluntary and data is handled in accordance
            with our <Link to="/privacy" className="text-blue-600 hover:underline">privacy policy</Link>.
          </p>
        </Card>

        <Card>
          <h2 className="text-lg font-bold text-slate-900 mb-3">Research Team</h2>
          <div className="p-4 rounded-lg bg-amber-50 border border-amber-200">
            <p className="text-sm text-amber-800">
              <strong>Placeholder:</strong> Research team contact details will be added here
              by the project maintainer. This section should not be edited by the AI.
            </p>
          </div>
        </Card>

        <Card>
          <h2 className="text-lg font-bold text-slate-900 mb-3">Development Phases</h2>
          <div className="space-y-3">
            {[
              { phase: 'Phase 0', label: 'Infrastructure & Scaffold', status: 'complete', desc: 'Docker Compose, FastAPI, PostgreSQL, React scaffold, CI health checks.' },
              { phase: 'Phase 1', label: 'Frontend Foundation', status: 'current', desc: 'Full UI with routing, role-based dashboards, surveys, analytics charts, and FAQ interface.' },
              { phase: 'Phase 2', label: 'Auth & Data Persistence', status: 'upcoming', desc: 'JWT authentication, survey submission to PostgreSQL, real analytics from the database.' },
              { phase: 'Phase 3', label: 'RAG Pipeline', status: 'upcoming', desc: 'ChromaDB vector store, LLM integration, cited FAQ answers from banking policy documents.' },
            ].map(p => (
              <div key={p.phase} className="flex gap-4 items-start">
                <div className={`mt-0.5 h-6 w-6 rounded-full flex items-center justify-center text-xs font-bold shrink-0 ${
                  p.status === 'complete' ? 'bg-green-100 text-green-700' :
                  p.status === 'current' ? 'bg-blue-100 text-blue-700' :
                  'bg-slate-100 text-slate-400'
                }`}>
                  {p.status === 'complete' ? '✓' : p.status === 'current' ? '●' : '○'}
                </div>
                <div>
                  <p className="text-sm font-semibold text-slate-800">{p.phase}: {p.label}</p>
                  <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">{p.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <h2 className="text-lg font-bold text-slate-900 mb-3">Technology Stack</h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
            {['React 19', 'TypeScript 7', 'Tailwind CSS 4', 'React Router 7', 'Recharts', 'FastAPI', 'PostgreSQL 16', 'SQLAlchemy 2', 'Docker'].map(t => (
              <span key={t} className="px-3 py-1.5 rounded-lg bg-slate-50 border border-slate-200 text-slate-700 font-medium text-center">
                {t}
              </span>
            ))}
          </div>
        </Card>
      </div>
    </PageShell>
  )
}
