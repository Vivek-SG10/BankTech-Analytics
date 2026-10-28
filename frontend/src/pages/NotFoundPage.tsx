import { Link } from 'react-router-dom'
import { PageShell } from '../components/Layout'

export default function NotFoundPage() {
  return (
    <PageShell title="">
      <div className="flex flex-col items-center justify-center py-24 text-center">
        <p className="text-8xl font-black text-slate-200 mb-4">404</p>
        <h1 className="text-2xl font-bold text-slate-900 mb-2">Page not found</h1>
        <p className="text-slate-500 mb-8 max-w-xs">
          The page you're looking for doesn't exist or has been moved.
        </p>
        <div className="flex gap-3">
          <Link
            to="/"
            className="px-6 py-2.5 rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700 transition"
          >
            Back to Home
          </Link>
          <Link
            to="/dashboard"
            className="px-6 py-2.5 rounded-lg border border-slate-300 text-slate-700 font-medium hover:bg-slate-50 transition"
          >
            Dashboard
          </Link>
        </div>
      </div>
    </PageShell>
  )
}
