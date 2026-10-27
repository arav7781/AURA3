'use client'

import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ChevronDown, ExternalLink, FileText } from 'lucide-react'
import { clsx } from 'clsx'
import type { Claim, Metric, Report, ReportCitation } from '@/lib/api/types'
import { Badge, Card, FlagBadges, LockedFeature, RecommendationBadge, ScoreRing } from '@/components/ui'

export interface DeckCitation { documentId: string; page: number; chunkId: string }

const DIMENSIONS: { key: string; rationale: string; label: string }[] = [
  { key: 'product', rationale: 'product', label: 'Product' },
  { key: 'market', rationale: 'market', label: 'Market' },
  { key: 'team', rationale: 'team', label: 'Team' },
  { key: 'businessModel', rationale: 'business_model', label: 'Business model' },
  { key: 'moat', rationale: 'moat', label: 'Moat' },
  { key: 'risk', rationale: 'execution_risk', label: 'Execution risk' },
  { key: 'traction', rationale: 'traction', label: 'Traction' },
]

const KIND: Record<string, string> = {
  reported: 'Source-reported', source_forecast: 'Source forecast', company_reported: 'Company-reported',
  company_estimate: 'Company estimate', company_forecast: 'Company forecast',
}

const CHECK: Record<Claim['check']['status'], { text: string; tone: 'green' | 'red' | 'amber' | 'slate' }> = {
  consistent: { text: 'Matches source', tone: 'green' },
  differs: { text: 'Differs from source', tone: 'red' },
  different_period: { text: 'Source covers another period', tone: 'amber' },
  different_currency: { text: 'Source in another currency', tone: 'amber' },
  unverified: { text: 'Not independently sourced', tone: 'slate' },
}

function amount(metric: Metric): string {
  return `${metric.value.toLocaleString('en-IN', { maximumFractionDigits: 2 })} ${metric.unit}`
}

/** Turns [c:abc1234] and [w:3] markers into links the renderer below shows as citation chips. */
function linkCitations(text: string, citations: Record<string, ReportCitation>): string {
  return text.replace(/\[([cw]:[a-z0-9]{1,7})\]/g, (marker, ref: string) => {
    const citation = citations[ref]
    if (!citation) return ''
    return citation.type === 'deck' ? `[p.${citation.page_no}](#cite-${ref})` : `[${ref.slice(2)}](#cite-${ref})`
  })
}

function Markdown({ text, report, onCite }: { text: string; report: Report; onCite: (c: DeckCitation) => void }) {
  return (
    <div className="markdown-content text-sm leading-relaxed text-slate-700">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          img: () => null, // reports never load remote images
          a: ({ href, children }) => {
            const ref = href?.startsWith('#cite-') ? href.slice(6) : null
            const citation = ref ? report.citations[ref] : null
            if (citation?.type === 'deck') {
              return (
                <button
                  type="button"
                  onClick={() => onCite({ documentId: citation.document_id, page: citation.page_no, chunkId: citation.chunk_id })}
                  title={citation.slide_title ? `Deck page ${citation.page_no}: ${citation.slide_title}` : `Deck page ${citation.page_no}`}
                  className="mx-0.5 inline-flex items-center gap-0.5 rounded bg-sky-50 px-1.5 py-px align-baseline text-[11px] font-semibold text-sky-700 ring-1 ring-sky-200 hover:bg-sky-100"
                >
                  <FileText className="w-3 h-3" />{children}
                </button>
              )
            }
            if (citation?.type === 'web') {
              return (
                <a href={citation.url} target="_blank" rel="noopener noreferrer" title={citation.title}
                   className="mx-0.5 inline-flex rounded bg-violet-50 px-1.5 py-px align-baseline text-[11px] font-semibold text-violet-700 ring-1 ring-violet-200 hover:bg-violet-100">
                  {children}
                </a>
              )
            }
            return <a href={href} target="_blank" rel="noopener noreferrer" className="text-[#0284c7] underline">{children}</a>
          },
        }}
      >
        {linkCitations(text, report.citations)}
      </ReactMarkdown>
    </div>
  )
}

function SlideChip({ metric, onCite }: { metric: Metric; onCite: (c: DeckCitation) => void }) {
  if (!metric.citation) return null
  const c = metric.citation
  return (
    <button type="button" onClick={() => onCite({ documentId: c.document_id, page: c.page_no, chunkId: c.chunk_id })}
            className="inline-flex items-center gap-0.5 rounded bg-sky-50 px-1.5 py-px text-[11px] font-semibold text-sky-700 ring-1 ring-sky-200 hover:bg-sky-100">
      <FileText className="w-3 h-3" />p.{c.page_no}
    </button>
  )
}

function Scorecard({ report }: { report: Report }) {
  const rows = DIMENSIONS.filter(d => d.key in report.categoryScores)
  return (
    <ul className="space-y-3">
      {rows.map(d => {
        const score = report.categoryScores[d.key]
        const spread = report.scoreSpread?.[d.rationale]
        return (
          <li key={d.key}>
            <div className="flex items-baseline justify-between gap-2 text-sm">
              <span className="font-semibold text-slate-800">{d.label}</span>
              <span className="font-mono text-slate-700">
                {score.toFixed(1)}
                {spread ? <span className="text-[11px] text-slate-400"> ±{(spread / 2).toFixed(1)}</span> : null}
              </span>
            </div>
            <div className="mt-1 h-2 rounded-full bg-slate-100">
              <div className={clsx('h-2 rounded-full', score >= 6.5 ? 'bg-emerald-500' : score >= 5 ? 'bg-amber-500' : 'bg-rose-500')}
                   style={{ width: `${score * 10}%` }} />
            </div>
          </li>
        )
      })}
    </ul>
  )
}

function MarketPanel({ report, onCite }: { report: Report; onCite: (c: DeckCitation) => void }) {
  const m = report.marketSizing
  if (!m) return null
  const keys = ['tam_usd_b', 'sam_usd_b', 'som_usd_b', 'cagr_pct'] as const
  const rows = keys.filter(k => m.evidence[k] || m.claims[k])
  if (!rows.length) return <p className="text-sm text-slate-500">No market figures with a quote and a period were found.</p>
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-[11px] font-mono uppercase tracking-widest text-slate-500">
            <th className="py-2 pr-3">Metric</th><th className="py-2 pr-3">The deck claims</th><th className="py-2 pr-3">Retrieved source</th><th className="py-2">Check</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 align-top">
          {rows.map(key => {
            const claim = m.claims[key]
            const sourced = m.evidence[key]
            return (
              <tr key={key}>
                <td className="py-2.5 pr-3 font-semibold text-slate-800">{key.split('_')[0].toUpperCase()}</td>
                <td className="py-2.5 pr-3">
                  {claim ? (
                    <span className="space-x-1">
                      <span>{amount(claim)} · {claim.year ?? claim.period}</span> <SlideChip metric={claim} onCite={onCite} />
                      <span className="block text-xs text-slate-500">{KIND[claim.kind]} · {claim.market}</span>
                    </span>
                  ) : <span className="text-slate-400">—</span>}
                </td>
                <td className="py-2.5 pr-3">
                  {sourced ? (
                    <span>
                      {amount(sourced)} · {sourced.year ?? sourced.period}
                      <a href={sourced.source_url ?? undefined} target="_blank" rel="noopener noreferrer"
                         className="block text-xs text-[#0284c7] hover:underline truncate max-w-[16rem]">{sourced.source_title}</a>
                    </span>
                  ) : <span className="text-slate-400">—</span>}
                </td>
                <td className="py-2.5">{claim ? <Badge tone={CHECK[claim.check.status].tone}>{CHECK[claim.check.status].text}</Badge> : <Badge tone="green">Sourced</Badge>}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function RevenuePanel({ report, onCite }: { report: Report; onCite: (c: DeckCitation) => void }) {
  const rows = report.projectedRevenue ?? []
  if (!rows.length) return <p className="text-sm text-slate-500">No dated revenue or ARR with a supporting quote. No growth assumptions are applied.</p>
  const top = Math.max(...rows.map(r => r.revenue)) || 1
  return (
    <div>
      <div className="flex items-end gap-4 h-40 border-b border-slate-200 px-2">
        {rows.map(r => (
          <div key={r.year} className="flex-1 flex flex-col items-center justify-end h-full">
            <span className="text-xs font-bold text-slate-800">{r.value} {r.unit.replace('INR ', 'Rs ')}</span>
            <div className={clsx('w-full max-w-16 rounded-t', r.kind.includes('forecast') ? 'bg-amber-400' : 'bg-emerald-500')}
                 style={{ height: `${Math.max(4, (r.revenue / top) * 100)}%` }} />
          </div>
        ))}
      </div>
      <div className="flex gap-4 px-2 mt-1">
        {rows.map(r => (
          <div key={r.year} className="flex-1 text-center text-xs text-slate-600">
            {r.year} <SlideChip metric={r} onCite={onCite} />
          </div>
        ))}
      </div>
      <p className="mt-3 text-xs text-slate-500">{report.revenueMetric} in {report.revenueCurrency}, as the company reports it (unverified).</p>
    </div>
  )
}

export function EvaluationReport({ report, onCite }: { report: Report; onCite: (c: DeckCitation) => void }) {
  const [open, setOpen] = useState<string | null>(null)
  const header = (
    <div className="flex flex-wrap items-center gap-5">
      <ScoreRing score={report.score} size={84} />
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <RecommendationBadge label={report.recommendationLabel} />
          <FlagBadges flags={report.complianceFlags} />
        </div>
        <p className="text-xs text-slate-500">
          Overall = weighted mean of seven rubric scores ({report.rubricVersion ?? 'r1'}), each the trimmed mean of five
          independent judgments. Compliance flags can cap the label.
        </p>
      </div>
    </div>
  )

  if (report.redacted) {
    return (
      <div className="space-y-5">
        <Card>{header}</Card>
        <Card title="Executive summary"><Markdown text={report.executiveSummary} report={report} onCite={onCite} /></Card>
        <LockedFeature title="Full AI due-diligence report">
          The scorecard with rationales, market claims checked against sources, revenue evidence, all 11 sections and
          the PDF are on the Angel plan and above.
        </LockedFeature>
      </div>
    )
  }

  return (
    <div className="space-y-5">
      <Card>{header}</Card>
      <div className="grid gap-5 lg:grid-cols-5">
        <Card title="Executive summary" className="lg:col-span-3">
          <Markdown text={report.executiveSummary} report={report} onCite={onCite} />
        </Card>
        <Card title="Scorecard" className="lg:col-span-2"><Scorecard report={report} /></Card>
      </div>
      <Card title="Market: deck claims vs retrieved sources"><MarketPanel report={report} onCite={onCite} /></Card>
      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Revenue evidence"><RevenuePanel report={report} onCite={onCite} /></Card>
        <Card title={`Data gaps (${report.dataGaps?.length ?? 0})`}>
          {report.dataGaps?.length ? (
            <ul className="list-disc pl-5 space-y-1 text-sm text-slate-700">{report.dataGaps.map(gap => <li key={gap}>{gap}</li>)}</ul>
          ) : <p className="text-sm text-slate-500">None.</p>}
        </Card>
      </div>
      <Card title="Why these scores">
        <dl className="grid gap-4 md:grid-cols-2">
          {DIMENSIONS.filter(d => report.scoreRationales?.[d.rationale]).map(d => (
            <div key={d.key}>
              <dt className="text-sm font-bold text-slate-900">{d.label} · {report.categoryScores[d.key]?.toFixed(1)}</dt>
              <dd><Markdown text={report.scoreRationales![d.rationale]} report={report} onCite={onCite} /></dd>
            </div>
          ))}
        </dl>
      </Card>
      <Card title="Investor report · 11 sections">
        <div className="divide-y divide-slate-100 -my-2">
          {(report.sections ?? []).map((section, i) => (
            <div key={section.key}>
              <button onClick={() => setOpen(open === section.key ? null : section.key)}
                      className="w-full flex items-center justify-between py-3 text-left group" aria-expanded={open === section.key}>
                <span className="text-sm font-bold text-slate-900 group-hover:text-[#0284c7]">
                  <span className="font-mono text-slate-400 mr-2">{String(i + 1).padStart(2, '0')}</span>{section.title}
                </span>
                <ChevronDown className={clsx('w-4 h-4 text-slate-400 transition-transform', open === section.key && 'rotate-180')} />
              </button>
              {open === section.key && <div className="pb-4"><Markdown text={section.content} report={report} onCite={onCite} /></div>}
            </div>
          ))}
        </div>
      </Card>
      {!!report.sources?.length && (
        <Card title={`Web sources (${report.sources.length})`}>
          <ol className="space-y-1.5 list-decimal pl-5">
            {report.sources.map(source => (
              <li key={source.url} className="text-sm">
                <a href={source.url} target="_blank" rel="noopener noreferrer" className="text-[#0284c7] hover:underline inline-flex items-center gap-1">
                  {source.title || source.url} <ExternalLink className="w-3 h-3" />
                </a>
                <span className="block text-[11px] text-slate-400">Retrieved {new Date(source.retrieved_at).toLocaleDateString()}</span>
              </li>
            ))}
          </ol>
        </Card>
      )}
      <p className="text-[11px] font-mono text-slate-400">
        {report.generatedAt && `Generated ${new Date(report.generatedAt).toLocaleString()} · `}{report.model} · AI analysis, not investment advice
      </p>
    </div>
  )
}
