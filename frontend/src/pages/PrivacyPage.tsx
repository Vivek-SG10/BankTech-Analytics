import { Card } from '../components/ui'
import { PageShell } from '../components/Layout'

export default function PrivacyPage() {
  return (
    <PageShell title="Privacy Policy" subtitle="How we collect, store and use your data">
      <div className="max-w-3xl mx-auto space-y-6">
        <Card>
          <p className="text-sm text-slate-500 mb-4">Last updated: October 2026 · Academic Research Version</p>
          <div className="space-y-5 text-sm text-slate-700 leading-relaxed">
            <section>
              <h2 className="font-bold text-slate-900 mb-2">1. Who We Are</h2>
              <p>
                BankTech Analytics is an academic research project conducted under institutional
                ethics oversight. It is not a commercial banking product and does not process real
                financial transactions or sensitive banking credentials.
              </p>
            </section>

            <section>
              <h2 className="font-bold text-slate-900 mb-2">2. What Data We Collect</h2>
              <ul className="space-y-1 list-disc list-inside text-slate-600">
                <li>Name and email address (for account management)</li>
                <li>Self-reported role and department</li>
                <li>Survey responses on a 1–5 Likert scale</li>
                <li>Optional free-text survey answers</li>
                <li>Anonymised conversation logs from the FAQ assistant</li>
              </ul>
              <p className="mt-2 text-slate-500 text-xs">
                We do not collect banking account numbers, passwords, financial data, or any information
                that could identify you in published research outputs.
              </p>
            </section>

            <section>
              <h2 className="font-bold text-slate-900 mb-2">3. How We Use Your Data</h2>
              <ul className="space-y-1 list-disc list-inside text-slate-600">
                <li>Aggregate statistical analysis of fintech adoption and satisfaction</li>
                <li>Thematic analysis of qualitative responses</li>
                <li>Academic publication in aggregate, anonymised form</li>
                <li>Improving the research platform and survey instruments</li>
              </ul>
            </section>

            <section>
              <h2 className="font-bold text-slate-900 mb-2">4. Data Storage & Security</h2>
              <p>
                Data is stored in a password-protected PostgreSQL database deployed within a private
                Docker environment. Access is restricted to the research team. Passwords are hashed
                using bcrypt. The platform uses JWT tokens for session management (Phase 2).
              </p>
            </section>

            <section>
              <h2 className="font-bold text-slate-900 mb-2">5. Your Rights</h2>
              <ul className="space-y-1 list-disc list-inside text-slate-600">
                <li>Right to access your submitted data</li>
                <li>Right to request deletion of your account and responses</li>
                <li>Right to withdraw from the study at any time without penalty</li>
              </ul>
              <p className="mt-2 text-slate-500 text-xs">
                Note: Once responses are included in aggregate analysis, individual withdrawal may
                not be possible, but your data will never be individually identifiable in outputs.
              </p>
            </section>

            <section>
              <h2 className="font-bold text-slate-900 mb-2">6. Third Parties</h2>
              <p>
                We do not share, sell or disclose individual data to any third party. The FAQ
                assistant may use an external LLM API in Phase 2; only the text of your question
                (not your identity) would be transmitted.
              </p>
            </section>

            <section>
              <h2 className="font-bold text-slate-900 mb-2">7. Contact</h2>
              <p>
                For any privacy-related questions, contact the research team via the{' '}
                <a href="/about" className="text-blue-600 hover:underline">About page</a>.
              </p>
            </section>
          </div>
        </Card>
      </div>
    </PageShell>
  )
}
