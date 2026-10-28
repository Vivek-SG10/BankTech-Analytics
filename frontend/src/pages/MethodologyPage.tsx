import { Link } from 'react-router-dom'
import { Card } from '../components/ui'
import { PageShell } from '../components/Layout'

export default function MethodologyPage() {
  return (
    <PageShell
      title="Research Methodology"
      subtitle="How this study is designed and conducted"
    >
      <div className="max-w-3xl mx-auto space-y-6">
        <Card>
          <h2 className="text-lg font-bold text-slate-900 mb-3">Study Overview</h2>
          <p className="text-sm text-slate-600 leading-relaxed">
            BankTech Analytics is an academic research project investigating the impact of financial
            technology (fintech) on banking stakeholders in the digital era. The study employs a
            mixed-methods approach combining structured Likert-scale surveys with open-ended
            qualitative questions across three participant groups: employees, managers, and customers.
          </p>
        </Card>

        <Card>
          <h2 className="text-lg font-bold text-slate-900 mb-3">Research Questions</h2>
          <ol className="space-y-3 text-sm text-slate-600">
            {[
              'How has the adoption of digital banking technologies affected employee satisfaction and operational efficiency?',
              'What is the relationship between fintech adoption and customer satisfaction across different service touchpoints?',
              'How do managerial perspectives on digital transformation align with frontline employee and customer experiences?',
              'What factors most strongly predict successful fintech adoption in traditional banking institutions?',
            ].map((q, i) => (
              <li key={i} className="flex gap-3">
                <span className="font-bold text-blue-600 shrink-0">RQ{i + 1}.</span>
                {q}
              </li>
            ))}
          </ol>
        </Card>

        <Card>
          <h2 className="text-lg font-bold text-slate-900 mb-3">Survey Instruments</h2>
          <p className="text-sm text-slate-600 leading-relaxed mb-4">
            Each participant group completes a role-specific survey developed from validated
            instruments in the technology acceptance and organisational behaviour literature.
            All Likert-scale items use a 5-point scale (1 = Strongly Disagree, 5 = Strongly Agree).
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {[
              { role: 'Employee Survey', count: '6 questions', focus: 'Technology adoption, training, satisfaction' },
              { role: 'Manager Survey', count: '6 questions', focus: 'Team adoption, strategic alignment, analytics' },
              { role: 'Customer Survey', count: '6 questions', focus: 'Usability, security, service quality' },
            ].map(s => (
              <div key={s.role} className="p-4 rounded-lg bg-slate-50 border border-slate-200">
                <p className="text-sm font-semibold text-slate-800">{s.role}</p>
                <p className="text-xs text-slate-500 mt-1">{s.count}</p>
                <p className="text-xs text-slate-600 mt-1 leading-relaxed">{s.focus}</p>
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <h2 className="text-lg font-bold text-slate-900 mb-3">Data Analysis</h2>
          <ul className="space-y-2 text-sm text-slate-600">
            {[
              'Descriptive statistics (mean, standard deviation) for all Likert items',
              'Sentiment analysis of open-text responses using NLP',
              'Cross-group comparison using non-parametric tests (Mann–Whitney U)',
              'Thematic analysis of qualitative responses',
              'Correlation analysis between adoption metrics and satisfaction scores',
            ].map(item => (
              <li key={item} className="flex gap-2">
                <span className="text-blue-500 shrink-0 mt-0.5">→</span>
                {item}
              </li>
            ))}
          </ul>
        </Card>

        <Card>
          <h2 className="text-lg font-bold text-slate-900 mb-3">Technical Platform</h2>
          <div className="grid grid-cols-2 gap-3 text-sm">
            {[
              { label: 'Frontend', value: 'React 19, TypeScript, Tailwind CSS' },
              { label: 'Backend', value: 'FastAPI (Python 3.11)' },
              { label: 'Database', value: 'PostgreSQL 16' },
              { label: 'RAG Pipeline', value: 'ChromaDB + LLM (Phase 2)' },
              { label: 'Auth', value: 'JWT Bearer Tokens (Phase 2)' },
              { label: 'Deployment', value: 'Docker Compose' },
            ].map(r => (
              <div key={r.label} className="p-3 rounded-lg bg-slate-50 border border-slate-100">
                <p className="text-xs text-slate-500">{r.label}</p>
                <p className="text-sm font-medium text-slate-800">{r.value}</p>
              </div>
            ))}
          </div>
        </Card>

        <p className="text-xs text-center text-slate-400 pb-4">
          This research follows institutional ethics guidelines. Any questions?{' '}
          <Link to="/about" className="text-blue-600 hover:underline">Contact the research team →</Link>
        </p>
      </div>
    </PageShell>
  )
}
