'use client'

import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ChevronDown, ExternalLink, ShieldAlert, ShieldCheck } from 'lucide-react'
import {
  Chart as ChartJS, RadialLinearScale, PointElement, LineElement, Filler, Tooltip, Legend,
  CategoryScale, LinearScale, LogarithmicScale, BarElement,
} from 'chart.js'
import { Bar, Line, Radar } from 'react-chartjs-2'
import type { AnalysisReport } from '@/lib/api'
import { flagLabel } from '@/lib/api'

ChartJS.register(RadialLinearScale, PointElement, LineElement, Filler, Tooltip, Legend, CategoryScale, LinearScale, LogarithmicScale, BarElement)

const ACCENT = '#0284c7'
const SCORE_LABELS: Record<string, string> = {
  product: 'Product', market: 'Market', team: 'Team', traction: 'Traction',
  businessModel: 'Business model', moat: 'Moat', risk: 'Execution risk',
}

const labelColor = (label: string) =>
  label === 'Strong Buy' ? 'bg-emerald-600' : label === 'Buy' ? 'bg-emerald-500' : label === 'Hold' ? 'bg-amber-500' : 'bg-rose-500'

function Card({ title, children, className = '' }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={`bg-white border border-slate-200 rounded-xl p-5 shadow-sm ${className}`}>
      <h3 className="text-[11px] font-bold font-mono uppercase tracking-widest text-slate-500 mb-4">{title}</h3>
      {children}
    </div>
  )
}

export function ComplianceBadge({ verified, flags }: { verified?: boolean; flags: string[] }) {
  return (
    <div className={`flex items-start gap-3 rounded-lg border px-4 py-3 ${verified && flags.length === 0 ? 'border-emerald-200 bg-emerald-50' : 'border-amber-200 bg-amber-50'}`}>
      {verified ? <ShieldCheck className="w-5 h-5 text-emerald-600 shrink-0" /> : <ShieldAlert className="w-5 h-5 text-amber-600 shrink-0" />}
      <div>
        <p className={`text-sm font-bold ${verified ? 'text-emerald-800' : 'text-amber-800'}`}>
          {verified ? 'MCA verified' : 'MCA not verified'}
        </p>
        <p className="text-xs text-slate-600">
          {flags.length ? flags.map(flagLabel).join(' · ') : 'No compliance flags raised'}
        </p>
      </div>
    </div>
  )
}

export function EvaluationReport({ report, showCompliance = true }: { report: AnalysisReport; showCompliance?: boolean }) {
  const [openSection, setOpenSection] = useState<string | null>('executive_summary')
  const scoreKeys = Object.keys(SCORE_LABELS).filter(k => k in report.categoryScores)
  const m = report.marketSizing
  const thisYear = new Date().getFullYear()

  return (
    <div className="space-y-6">
      <div className={`grid grid-cols-1 gap-4 ${showCompliance ? 'md:grid-cols-3' : 'md:grid-cols-2'}`}>
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm flex items-center gap-5">
          <div className="relative w-20 h-20">
            <svg viewBox="0 0 36 36" className="w-20 h-20 -rotate-90">
              <circle cx="18" cy="18" r="15.9" fill="none" stroke="#e2e8f0" strokeWidth="3" />
              <circle cx="18" cy="18" r="15.9" fill="none" stroke={ACCENT} strokeWidth="3" strokeLinecap="round"
                strokeDasharray={`${report.score * 10} 100`} />
            </svg>
            <span className="absolute inset-0 flex items-center justify-center text-xl font-black text-slate-900">{report.score.toFixed(1)}</span>
          </div>
          <div>
            <p className="text-[11px] font-mono uppercase tracking-widest text-slate-500">AI score / 10</p>
            <span className={`inline-block mt-2 px-3 py-1 rounded-full text-white text-sm font-bold ${labelColor(report.recommendationLabel)}`}>
              {report.recommendationLabel}
            </span>
          </div>
        </div>
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
          <p className="text-[11px] font-mono uppercase tracking-widest text-slate-500 mb-3">Market sizing (USD)</p>
          <div className="grid grid-cols-3 gap-2 text-center">
            {[['TAM', m.tam_usd_b], ['SAM', m.sam_usd_b], ['SOM', m.som_usd_b]].map(([k, v]) => (
              <div key={k as string}>
                <p className="text-lg font-black text-slate-900">${Number(v) >= 1 ? Number(v).toFixed(1) + 'B' : (Number(v) * 1000).toFixed(0) + 'M'}</p>
                <p className="text-[10px] font-mono text-slate-500">{k}</p>
              </div>
            ))}
          </div>
          <p className="text-xs text-slate-500 mt-3">{m.cagr_pct}% expected annual growth</p>
        </div>
        {showCompliance && <ComplianceBadge verified={report.complianceFlags.length === 0} flags={report.complianceFlags} />}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card title="Evaluation scorecard">
          <div className="h-[260px]">
            <Radar
              data={{
                labels: scoreKeys.map(k => SCORE_LABELS[k]),
                datasets: [{
                  label: 'Score',
                  data: scoreKeys.map(k => report.categoryScores[k]),
                  backgroundColor: 'rgba(2,132,199,0.15)',
                  borderColor: ACCENT,
                  pointBackgroundColor: ACCENT,
                }],
              }}
              options={{
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: { r: { min: 0, max: 10, ticks: { stepSize: 2, display: false }, pointLabels: { font: { size: 11 }, color: '#334155' } } },
              }}
            />
          </div>
        </Card>
        <Card title={`Market growth — ${m.cagr_pct}% CAGR (estimate)`}>
          <div className="h-[260px]">
            <Line
              data={{
                labels: m.trend.map(p => String(p.year)),
                datasets: [{
                  label: 'Market size (USD B)',
                  data: m.trend.map(p => p.size_usd_b),
                  borderColor: ACCENT,
                  backgroundColor: 'rgba(2,132,199,0.08)',
                  fill: true,
                  tension: 0.3,
                  segment: { borderDash: ctx => (Number(m.trend[ctx.p0DataIndex]?.year) >= thisYear ? [6, 4] : undefined) },
                }],
              }}
              options={{ maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: false, title: { display: true, text: 'USD billions' } } } }}
            />
          </div>
        </Card>
        <Card title="TAM / SAM / SOM">
          <div className="h-[220px]">
            <Bar
              data={{
                labels: ['TAM', 'SAM', 'SOM'],
                datasets: [{ data: [m.tam_usd_b, m.sam_usd_b, m.som_usd_b], backgroundColor: ['#0284c7', '#38bdf8', '#bae6fd'], borderRadius: 6 }],
              }}
              options={{ maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { type: 'logarithmic', title: { display: true, text: 'USD billions (log scale)' } } } }}
            />
          </div>
          <p className="text-xs text-slate-500 mt-3">{m.basis}</p>
        </Card>
        {report.projectedRevenue.length > 0 && (
          <Card title="Projected revenue (USD millions, estimate)">
            <div className="h-[220px]">
              <Bar
                data={{
                  labels: report.projectedRevenue.map(r => String(r.year)),
                  datasets: [{ data: report.projectedRevenue.map(r => r.revenue), backgroundColor: '#10b981', borderRadius: 6 }],
                }}
                options={{ maintainAspectRatio: false, plugins: { legend: { display: false } } }}
              />
            </div>
          </Card>
        )}
      </div>

      <Card title="Investor report — 11 sections">
        <div className="divide-y divide-slate-100">
          {report.sections.map((section, i) => (
            <div key={section.key}>
              <button
                onClick={() => setOpenSection(openSection === section.key ? null : section.key)}
                className="w-full flex items-center justify-between py-3 text-left group"
              >
                <span className="text-sm font-bold text-slate-900 group-hover:text-[#0284c7]">
                  <span className="font-mono text-slate-400 mr-2">{String(i + 1).padStart(2, '0')}</span>{section.title}
                </span>
                <ChevronDown className={`w-4 h-4 text-slate-400 transition-transform ${openSection === section.key ? 'rotate-180' : ''}`} />
              </button>
              {openSection === section.key && (
                <div className="pb-4 text-sm leading-relaxed text-slate-700 markdown-content report-markdown">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{section.content}</ReactMarkdown>
                </div>
              )}
            </div>
          ))}
        </div>
      </Card>

      {report.sources.length > 0 && (
        <Card title={`Sources the analyst used (${report.sources.length})`}>
          <ul className="space-y-1.5">
            {report.sources.map(s => (
              <li key={s.url}>
                <a href={s.url} target="_blank" rel="noopener noreferrer" className="text-sm text-[#0284c7] hover:underline inline-flex items-center gap-1.5">
                  {s.title || s.url} <ExternalLink className="w-3 h-3" />
                </a>
              </li>
            ))}
          </ul>
        </Card>
      )}
      {report.generatedAt && (
        <p className="text-[11px] font-mono text-slate-400">
          Generated {new Date(report.generatedAt).toLocaleString()} · {report.model} · AI analysis, not financial advice
        </p>
      )}
    </div>
  )
}
