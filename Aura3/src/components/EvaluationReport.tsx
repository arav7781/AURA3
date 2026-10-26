'use client'

import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ChevronDown, ExternalLink, ShieldAlert, ShieldCheck } from 'lucide-react'
import {
  Chart as ChartJS, RadialLinearScale, PointElement, LineElement, Filler, Tooltip, Legend,
  CategoryScale, LinearScale, BarElement,
} from 'chart.js'
import { Bar, Line, Radar } from 'react-chartjs-2'
import type { AnalysisReport, EvidenceMetric } from '@/lib/api'
import { flagLabel } from '@/lib/api'

ChartJS.register(RadialLinearScale, PointElement, LineElement, Filler, Tooltip, Legend, CategoryScale, LinearScale, BarElement)

const ACCENT = '#0284c7'
const KIND_LABELS: Record<EvidenceMetric['kind'], string> = {
  reported: 'Source-reported', source_forecast: 'Source forecast',
  company_reported: 'Company-reported (unverified)', company_forecast: 'Company forecast (unverified)',
}
const marketValue = (value: number | null) => value === null ? 'Unavailable'
  : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', notation: 'compact', maximumSignificantDigits: 4 }).format(value * 1e9)
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

function EmptyChart({ children }: { children: React.ReactNode }) {
  return <div className="min-h-[180px] flex items-center justify-center rounded-lg bg-slate-50 p-6 text-center text-sm text-slate-500">{children}</div>
}

function EvidenceDetails({ rows }: { rows: { label: string; metric: EvidenceMetric }[] }) {
  if (!rows.length) return null
  return (
    <details className="mt-4 text-xs text-slate-600">
      <summary className="cursor-pointer font-semibold text-[#0284c7]">View data &amp; sources ({rows.length})</summary>
      <div className="mt-3 space-y-3">
        {rows.map(({ label, metric }, i) => (
          <div key={`${label}-${i}`} className="border-t border-slate-100 pt-3">
            <p className="font-semibold text-slate-800">{label}: {metric.value.toLocaleString('en-US', { maximumSignificantDigits: 8 })} {metric.unit} · {metric.year ?? metric.period}</p>
            <p>{KIND_LABELS[metric.kind]} · {[metric.market, metric.geography].filter(Boolean).join(' · ')}</p>
            {metric.source_url ? (
              <a href={metric.source_url} target="_blank" rel="noopener noreferrer" className="text-[#0284c7] hover:underline">{metric.source_title || metric.source_url}</a>
            ) : <p>{metric.source_title}</p>}
            <blockquote className="mt-1 border-l-2 border-slate-200 pl-2">{metric.quote}</blockquote>
            {metric.retrieved_at && <p className="mt-1 text-slate-400">Retrieved {new Date(metric.retrieved_at).toLocaleString()}</p>}
          </div>
        ))}
      </div>
    </details>
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
  const marketRows = (['tam_usd_b', 'sam_usd_b', 'som_usd_b'] as const)
    .filter(key => m[key] !== null)
    .map(key => ({ label: key.slice(0, 3).toUpperCase(), value: m[key] as number }))
  const marketEvidence = Object.entries(m.evidence).map(([key, metric]) => ({ label: key.replace('_usd_b', '').replace('_pct', '').toUpperCase(), metric }))

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-xs text-slate-600 space-y-2">
        <p>Charts use this report’s saved search evidence and dated company figures. Forecasts retain their source labels; AI scores are analytical judgments.</p>
        {report.researchStatus === 'unavailable' && <p className="font-semibold text-amber-700">Web research was unavailable. External market figures could not be established.</p>}
        {report.dataGaps.length > 0 && (
          <details open={!report.evidenceVersion}>
            <summary className="cursor-pointer font-semibold">Data availability ({report.dataGaps.length})</summary>
            <ul className="mt-2 list-disc pl-4 space-y-1">{report.dataGaps.map(gap => <li key={gap}>{gap}</li>)}</ul>
          </details>
        )}
      </div>
      <div className={`grid grid-cols-1 gap-4 ${showCompliance ? 'md:grid-cols-3' : 'md:grid-cols-2'}`}>
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm flex items-center gap-5">
          <div className="relative w-20 h-20">
            <svg viewBox="0 0 36 36" className="w-20 h-20 -rotate-90">
              <circle cx="18" cy="18" r="15.9" fill="none" stroke="#e2e8f0" strokeWidth="3" />
              <circle cx="18" cy="18" r="15.9" fill="none" stroke={ACCENT} strokeWidth="3" strokeLinecap="round"
                strokeDasharray={`${(report.score ?? 0) * 10} 100`} />
            </svg>
            <span className="absolute inset-0 flex items-center justify-center text-xl font-black text-slate-900">{report.score?.toFixed(1) ?? 'N/A'}</span>
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
            {(['tam_usd_b', 'sam_usd_b', 'som_usd_b'] as const).map(key => (
              <div key={key}>
                <p className={`${m[key] === null ? 'text-xs' : 'text-lg'} font-black text-slate-900`}>{marketValue(m[key])}</p>
                <p className="text-[10px] font-mono text-slate-500">{key.slice(0, 3).toUpperCase()}</p>
                {m.evidence[key] && <p className="text-[10px] text-slate-500">{m.evidence[key].year} · {KIND_LABELS[m.evidence[key].kind]}</p>}
              </div>
            ))}
          </div>
          <p className="text-xs text-slate-500 mt-3">{m.cagr_pct === null ? 'CAGR unavailable' : `${m.cagr_pct}% CAGR · ${m.evidence.cagr_pct?.period} · ${KIND_LABELS[m.evidence.cagr_pct.kind]}`}</p>
        </div>
        {showCompliance && <ComplianceBadge verified={report.complianceFlags.length === 0} flags={report.complianceFlags} />}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card title="Evaluation scorecard · AI judgment">
          {scoreKeys.length > 0 ? (
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
          ) : <EmptyChart>No analytical scores available.</EmptyChart>}
        </Card>
        <Card title="Published market data">
          {m.trend.length > 0 ? (
          <div className="h-[260px]">
            <Line
              data={{
                datasets: (['reported', 'source_forecast'] as const)
                  .filter(kind => m.trend.some(p => p.kind === kind))
                  .map(kind => ({
                    label: KIND_LABELS[kind],
                    data: m.trend.filter(p => p.kind === kind).map(p => ({ x: p.year, y: p.size_usd_b })),
                    borderColor: kind === 'reported' ? ACCENT : '#d97706',
                    backgroundColor: kind === 'reported' ? ACCENT : '#d97706',
                    pointStyle: kind === 'reported' ? 'circle' as const : 'rectRot' as const,
                    pointRadius: 5,
                    showLine: false,
                  })),
              }}
              options={{ maintainAspectRatio: false, scales: {
                x: { type: 'linear', ticks: { precision: 0, callback: value => String(value) }, title: { display: true, text: 'Source year' } },
                y: { beginAtZero: true, title: { display: true, text: 'USD billions' } },
              } }}
            />
          </div>
          ) : <EmptyChart>No dated market observations or publisher forecasts found.</EmptyChart>}
          <p className="text-xs text-slate-500 mt-3">Only published points are shown. Missing years are not interpolated.</p>
          <EvidenceDetails rows={m.trend.map(metric => ({ label: `Market ${metric.year}`, metric }))} />
        </Card>
        <Card title="TAM / SAM / SOM">
          {marketRows.length > 0 ? (
          <div className="h-[220px]">
            <Bar
              data={{
                labels: marketRows.map(row => row.label),
                datasets: [{ data: marketRows.map(row => row.value), backgroundColor: ['#0284c7', '#38bdf8', '#bae6fd'], borderRadius: 6 }],
              }}
              options={{ maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, title: { display: true, text: 'USD billions' } } } }}
            />
          </div>
          ) : <EmptyChart>No source-supported market sizing available.</EmptyChart>}
          <p className="text-xs text-slate-500 mt-3">{m.basis}</p>
          <EvidenceDetails rows={marketEvidence} />
        </Card>
          <Card title={`${report.revenueMetric || 'Revenue / ARR'} · dated figures & explicit forecasts`}>
            {report.projectedRevenue.length > 0 ? (
            <div className="h-[220px]">
              <Bar
                data={{
                  labels: report.projectedRevenue.map(r => [String(r.year), KIND_LABELS[r.kind].replace(' (unverified)', '')]),
                  datasets: [{ data: report.projectedRevenue.map(r => r.revenue), backgroundColor: report.projectedRevenue.map(r => r.kind.includes('forecast') ? '#d97706' : '#10b981'), borderRadius: 6 }],
                }}
                options={{ maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, title: { display: true, text: `${report.revenueCurrency} millions` } } } }}
              />
            </div>
            ) : <EmptyChart>No dated revenue or ARR figures with supporting evidence. No growth assumptions applied.</EmptyChart>}
            {report.projectedRevenue.length > 0 && <p className="mt-3 text-xs text-slate-500">{report.revenueCurrency} millions · Company claims are unverified; forecasts are not actual results.</p>}
            <EvidenceDetails rows={report.projectedRevenue.map(metric => ({ label: `${metric.metric} ${metric.year}`, metric }))} />
          </Card>
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
        <Card title={`Research sources (${report.sources.length})`}>
          <ul className="space-y-1.5">
            {report.sources.map(s => (
              <li key={s.url}>
                <a href={s.url} target="_blank" rel="noopener noreferrer" className="text-sm text-[#0284c7] hover:underline inline-flex items-center gap-1.5">
                  {s.title || s.url} <ExternalLink className="w-3 h-3" />
                </a>
                {s.retrieved_at && <span className="block text-[10px] text-slate-400">Retrieved {new Date(s.retrieved_at).toLocaleString()}</span>}
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
