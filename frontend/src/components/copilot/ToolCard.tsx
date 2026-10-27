'use client'

import { useState } from 'react'
import Link from 'next/link'
import { AlertTriangle, BarChart3, Check, ChevronDown, Download, ExternalLink, FileSearch, FileText, Globe, Loader2, Lock, MessageSquare, Search, Table2, Building2 } from 'lucide-react'
import { clsx } from 'clsx'
import type { Card, Part } from '@/lib/copilot'
import { Badge, FlagBadges, RecommendationBadge, ScoreRing, STAGE_LABELS } from '@/components/ui'

type ToolPart = Extract<Part, { type: 'tool' }>

const ICONS: Record<string, typeof Search> = {
  search_startups: Search, get_startup: Building2, list_documents: FileText, search_documents: FileSearch,
  read_page: FileText, get_evaluation: BarChart3, compare_startups: Table2, get_reviews: MessageSquare, web_search: Globe,
}

function label(part: ToolPart): string {
  const a = part.args as Record<string, string | number | string[] | undefined>
  const who = a.startup ? ` · ${a.startup}` : ''
  switch (part.name) {
    case 'search_startups': return `Searched startups${a.query ? ` · “${a.query}”` : ''}${a.domain ? ` · ${a.domain}` : ''}`
    case 'get_startup': return `Profile${who}`
    case 'list_documents': return `Submitted documents${who}`
    case 'search_documents': return `Searched documents · “${a.query}”${who}`
    case 'read_page': return `Read page ${a.page}${who}`
    case 'get_evaluation': return `AI evaluation${who}`
    case 'compare_startups': return `Compared ${(a.startups as string[] | undefined)?.join(', ') ?? 'startups'}`
    case 'get_reviews': return `Investor reviews${who}`
    case 'web_search': return `Web search · “${a.query}”`
    default: return part.name
  }
}

export function evidenceHref(slug: string, documentId: string, page: number, chunkId?: string) {
  return `/startups/${slug}?tab=evidence&doc=${documentId}&page=${page}${chunkId ? `&chunk=${chunkId}` : ''}`
}

function Body({ card }: { card: Card }) {
  switch (card.type) {
    case 'startups':
      return card.items.length ? (
        <div className="grid gap-2 sm:grid-cols-2">
          {card.items.map((s: Card) => (
            <Link key={s.id} href={`/startups/${s.slug}`} className="flex items-center gap-3 rounded-lg border border-slate-200 bg-white p-2.5 hover:border-cobalt/50">
              <ScoreRing score={s.ai_score} size={38} />
              <span className="min-w-0">
                <span className="block truncate text-sm font-bold text-slate-900">{s.name}</span>
                <span className="block truncate text-xs text-slate-500">{s.domain} · {STAGE_LABELS[s.stage] ?? s.stage}</span>
              </span>
            </Link>
          ))}
        </div>
      ) : <p className="text-sm text-slate-500">No matches.</p>
    case 'startup': {
      const s = card.item
      return (
        <Link href={`/startups/${s.slug}`} className="flex items-center gap-3 rounded-lg border border-slate-200 bg-white p-3 hover:border-cobalt/50">
          <ScoreRing score={s.ai_score} size={44} />
          <span className="min-w-0 flex-1">
            <span className="flex flex-wrap items-center gap-1.5"><b className="text-slate-900">{s.name}</b><RecommendationBadge label={s.recommendation} /><FlagBadges flags={s.compliance_flags} /></span>
            <span className="block truncate text-xs text-slate-500">{s.one_liner}</span>
          </span>
        </Link>
      )
    }
    case 'documents':
      return card.items.length ? (
        <ul className="space-y-2">
          {card.items.map((d: Card) => (
            <li key={d.id} className="flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 bg-white p-3">
              <FileText className="h-5 w-5 shrink-0 text-cobalt" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-semibold text-slate-900">{d.filename}</span>
                <span className="block font-mono text-[0.65rem] text-slate-500">
                  {d.kind} · {d.pages} pages · {new Date(d.uploaded_at).toLocaleDateString()} · TitanOCR {d.ocr_seconds} s
                </span>
              </span>
              {d.flags?.length > 0 && <FlagBadges flags={d.flags} />}
              {card.can_open ? (
                <span className="flex gap-1.5">
                  <Link href={d.view_url} className="rounded-full bg-[#eef1fd] px-3 py-1 text-xs font-semibold text-cobalt hover:bg-[#e2e7fc]">Open</Link>
                  {d.download_url && (
                    <a href={d.download_url} className="inline-flex items-center gap-1 rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50">
                      <Download className="h-3 w-3" /> Download
                    </a>
                  )}
                </span>
              ) : (
                <Link href="/wallet#plans" className="inline-flex items-center gap-1 rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-600"><Lock className="h-3 w-3" /> Angel to open</Link>
              )}
            </li>
          ))}
        </ul>
      ) : <p className="text-sm text-slate-500">No processed documents yet.</p>
    case 'passages':
      return card.items.length ? (
        <ul className="space-y-2">
          {card.items.map((p: Card) => (
            <li key={p.cid} className="rounded-lg border border-slate-200 bg-white p-3">
              <Link href={evidenceHref(p.slug, p.document_id, p.page_no, p.chunk_id)} className="inline-flex items-center gap-1 font-mono text-[0.65rem] text-cobalt hover:underline">
                <FileText className="h-3 w-3" /> {p.startup} · p.{p.page_no}{p.slide_title ? ` · ${p.slide_title}` : ''} · {p.cid}
              </Link>
              {p.flagged && <span className="ml-2"><Badge tone="red">possible hidden instructions</Badge></span>}
              <p className="mt-1 line-clamp-4 whitespace-pre-line text-sm text-slate-700">{p.text}</p>
            </li>
          ))}
        </ul>
      ) : <p className="text-sm text-slate-500">No matching passages.</p>
    case 'evaluation':
      return card.score == null ? <p className="text-sm text-slate-500">No published evaluation.</p> : (
        <div className="flex flex-wrap items-center gap-4 rounded-lg border border-slate-200 bg-white p-3">
          <ScoreRing score={card.score} size={48} />
          <div className="min-w-0 space-y-1.5">
            <span className="flex flex-wrap items-center gap-1.5"><RecommendationBadge label={card.label} /><FlagBadges flags={card.flags} /></span>
            {card.categories && (
              <span className="flex flex-wrap gap-x-3 gap-y-0.5 font-mono text-[0.65rem] text-slate-500">
                {Object.entries(card.categories as Record<string, number>).map(([k, v]) => <span key={k}>{k.replace('_', ' ')} {v.toFixed(1)}</span>)}
              </span>
            )}
          </div>
        </div>
      )
    case 'comparison':
      return (
        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-slate-100 text-left">{['', ...card.items.map((r: Card) => r.name)].map((h: string) => <th key={h} className="px-3 py-2 font-semibold">{h}</th>)}</tr></thead>
            <tbody className="divide-y divide-slate-100">
              {[
                ['AI score', (r: Card) => r.ai_score != null ? `${r.ai_score} · ${r.recommendation}` : '—'],
                ['Stage', (r: Card) => STAGE_LABELS[r.stage] ?? r.stage],
                ['Raising', (r: Card) => r.ask_inr ? `₹${r.ask_inr / 1e7} Cr` : '—'],
                ['Reviews', (r: Card) => r.reviews ? `${r.reviews} · ${r.review_avg}/5` : '0'],
                ['Community rank', (r: Card) => r.community_rank ?? '—'],
              ].map(([name, cell]) => (
                <tr key={name as string}><td className="px-3 py-2 text-slate-500">{name as string}</td>{card.items.map((r: Card) => <td key={r.id} className="px-3 py-2">{(cell as (r: Card) => string)(r)}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      )
    case 'reviews':
      return card.items.length ? (
        <div className="rounded-lg border border-slate-200 bg-white p-3 text-sm">
          <p className="font-mono text-[0.65rem] text-slate-500">{card.items.length} reviews · {Object.entries(card.averages as Record<string, number>).map(([k, v]) => `${k} ${v}`).join(' · ')}</p>
          <ul className="mt-2 space-y-1.5">{card.items.slice(0, 3).map((r: Card, i: number) => <li key={i} className="text-slate-700"><b>{r.reviewer}:</b> {r.note}</li>)}</ul>
        </div>
      ) : <p className="text-sm text-slate-500">No reviews yet.</p>
    case 'web':
      return (
        <ol className="space-y-1.5">
          {card.items.map((w: Card) => (
            <li key={w.n} className="flex gap-2 text-sm">
              <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded bg-violet-50 font-mono text-[0.6rem] font-semibold text-violet-700">{w.n}</span>
              <a href={w.url} target="_blank" rel="noopener noreferrer" className="min-w-0 truncate text-slate-800 hover:text-cobalt hover:underline">
                {w.title || w.url} <ExternalLink className="inline h-3 w-3" />
              </a>
            </li>
          ))}
        </ol>
      )
    case 'error':
      return (
        <p className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          {card.code === 'PLAN_REQUIRED' ? <Lock className="mt-0.5 h-4 w-4 shrink-0" /> : <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />}
          <span>{card.message} {card.code === 'PLAN_REQUIRED' && <Link href="/wallet#plans" className="font-semibold underline">Upgrade</Link>}</span>
        </p>
      )
    default:
      return null
  }
}

export function ToolCard({ part }: { part: ToolPart }) {
  const Icon = ICONS[part.name] ?? Search
  const collapsible = part.card?.type === 'passages' || part.card?.type === 'web'
  const [open, setOpen] = useState(!collapsible)
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50/70">
      <button type="button" onClick={() => setOpen(o => !o)} disabled={!part.card}
              className="flex w-full items-center gap-2 px-3 py-2 text-left">
        <Icon className="h-4 w-4 shrink-0 text-cobalt" />
        <span className="min-w-0 flex-1 truncate text-[0.82rem] font-semibold text-slate-700">{label(part)}</span>
        {part.status === 'running' && <Loader2 className="h-3.5 w-3.5 animate-spin text-slate-400" />}
        {part.status === 'done' && <Check className="h-3.5 w-3.5 text-emerald-600" />}
        {part.status === 'error' && <AlertTriangle className="h-3.5 w-3.5 text-amber-600" />}
        {part.card && <ChevronDown className={clsx('h-3.5 w-3.5 text-slate-400 transition-transform', open && 'rotate-180')} />}
      </button>
      {open && part.card && <div className="px-3 pb-3"><Body card={part.card} /></div>}
    </div>
  )
}
