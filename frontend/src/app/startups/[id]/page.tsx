'use client'

import { Suspense, useState } from 'react'
import Link from 'next/link'
import { useParams, useSearchParams } from 'next/navigation'
import { ArrowLeft, Bot, Download, ShieldAlert, ShieldCheck } from 'lucide-react'
import { RequireRole } from '@/components/auth/RequireRole'
import { Reviews } from '@/components/community/Reviews'
import { EvaluationReport, type DeckCitation } from '@/components/evaluation/EvaluationReport'
import { EmbeddingMap } from '@/components/evidence/EmbeddingMap'
import { EvidenceViewer } from '@/components/evidence/EvidenceViewer'
import { Badge, Card, EmptyState, ErrorNote, FlagBadges, flagLabel, LockedFeature, RecommendationBadge, ScoreRing, Spinner, STAGE_LABELS, Stat, Tabs } from '@/components/ui'
import { useAuth } from '@/context/AuthContext'
import { useEvaluation, useStartup } from '@/lib/api/hooks'
import type { StartupDetail } from '@/lib/api/types'
import { formatINR } from '@/lib/format'

type Tab = 'overview' | 'evaluation' | 'evidence' | 'map' | 'reviews' | 'round'

export default function StartupPage() {
  return (
    <RequireRole>
      <Suspense>
        <StartupView />
      </Suspense>
    </RequireRole>
  )
}

function StartupView() {
  const { id } = useParams<{ id: string }>()
  const params = useSearchParams()
  const startup = useStartup(id)
  const evaluation = useEvaluation(startup.data?.id)
  const { has } = useAuth()
  // Deep links from copilot citations: ?tab=evidence&doc=…&page=…&chunk=…
  const linked = params.get('doc')
    ? { documentId: params.get('doc')!, page: Number(params.get('page') ?? 1), chunkId: params.get('chunk') ?? '' }
    : null
  const [tab, setTab] = useState<Tab>((params.get('tab') as Tab) ?? 'overview')
  const [focus, setFocus] = useState<DeckCitation | null>(linked)

  if (startup.isPending) return <Spinner label="Loading startup" />
  if (startup.isError) return <div className="max-w-3xl mx-auto px-4 py-16"><ErrorNote error={startup.error} /></div>
  const s = startup.data
  const owner = s.is_owner
  const report = evaluation.data?.report ?? null
  const openCitation = (citation: DeckCitation) => {
    setFocus({ ...citation })
    setTab('evidence')
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const tabs: { id: Tab; label: string; locked?: boolean }[] = [
    { id: 'overview', label: 'Overview' },
    { id: 'evaluation', label: 'AI evaluation', locked: !owner && !has('full_report') },
    { id: 'evidence', label: 'Deck evidence', locked: !owner && !has('deck_access') },
    { id: 'map', label: 'Embedding map', locked: !owner && !has('chunk_explorer') },
    { id: 'reviews', label: 'Reviews' },
    { id: 'round', label: 'Round' },
  ]

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8">
      <Link href={owner ? '/founder' : '/investor'} className="inline-flex items-center gap-1 text-sm font-semibold text-slate-600 hover:text-[#0284c7]">
        <ArrowLeft className="w-4 h-4" /> {owner ? 'Founder portal' : 'Deal flow'}
      </Link>
      <header className="mt-4 mb-6 flex flex-col gap-5 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-5">
          <ScoreRing score={s.ai_score} size={76} />
          <div>
            <h1 className="text-3xl font-black tracking-tight text-slate-900">{s.name}</h1>
            <p className="mt-1 text-slate-600">{s.one_liner}</p>
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <Badge tone="sky">{s.domain}</Badge>
              <Badge>{STAGE_LABELS[s.stage]}</Badge>
              <RecommendationBadge label={s.recommendation} />
              <FlagBadges flags={s.compliance_flags} />
              {s.status !== 'published' && <Badge tone="violet">Draft · only you can see it</Badge>}
            </div>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link href={`/copilot?startup=${s.slug}`} className="inline-flex items-center gap-2 rounded-lg bg-ink px-4 py-2 text-sm font-bold text-white hover:bg-black">
            <Bot className="w-4 h-4" /> Ask the copilot
          </Link>
          {report && !report.redacted && (owner || has('pdf_reports')) && (
            <a href={`/api/startups/${s.id}/report.pdf`} className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-bold text-slate-800 hover:bg-slate-50">
              <Download className="w-4 h-4" /> PDF report
            </a>
          )}
        </div>
      </header>

      <Tabs tabs={tabs} active={tab} onChange={setTab} />
      <div className="mt-6">
        {tab === 'overview' && <Overview startup={s} />}
        {tab === 'evaluation' && (
          evaluation.isPending ? <Spinner /> : report ? <EvaluationReport report={report} onCite={openCitation} /> : (
            <EmptyState title="No published evaluation yet">
              {owner ? <>Run one from the <Link href="/founder" className="font-semibold text-[#0284c7]">founder portal</Link>.</> : null}
            </EmptyState>
          )
        )}
        {tab === 'evidence' && <EvidenceViewer startupId={s.id} focus={focus} />}
        {tab === 'map' && (owner || has('chunk_explorer')
          ? <EmbeddingMap startupId={s.id} allStartups={has('chunk_explorer')} onOpen={c => c.documentId && openCitation(c)} />
          : <LockedFeature title="Embedding map">See where this deck sits among all decks in meaning-space, and ask the HNSW index questions live.</LockedFeature>)}
        {tab === 'reviews' && <Reviews startupId={s.id} isOwner={owner} />}
        {tab === 'round' && <Round startup={s} />}
      </div>
    </div>
  )
}

function Overview({ startup: s }: { startup: StartupDetail }) {
  const verified = !!s.mca?.mca_verified
  return (
    <div className="grid gap-5 lg:grid-cols-3">
      <div className="space-y-5 lg:col-span-2">
        <Card title="About"><p className="text-sm leading-relaxed text-slate-700 whitespace-pre-line">{s.description || s.one_liner}</p></Card>
        {!!s.profile.team?.length && (
          <Card title="Team">
            <ul className="grid gap-4 sm:grid-cols-2">
              {s.profile.team.map(member => (
                <li key={member.name}>
                  <p className="font-bold text-slate-900">{member.name}</p>
                  <p className="text-sm text-[#0284c7]">{member.role}</p>
                  {member.background && <p className="mt-1 text-sm text-slate-600">{member.background}</p>}
                </li>
              ))}
            </ul>
          </Card>
        )}
        {!!s.profile.competitors?.length && (
          <Card title="Competitors named in the deck">
            <ul className="divide-y divide-slate-100">
              {s.profile.competitors.map(c => (
                <li key={c.name} className="py-2 text-sm"><b className="text-slate-900">{c.name}</b> <span className="text-slate-600">— {c.positioning}</span></li>
              ))}
            </ul>
          </Card>
        )}
      </div>
      <div className="space-y-5">
        <Card title="Company">
          <div className="grid grid-cols-2 gap-4">
            <Stat label="Headquarters" value={<span className="text-base">{s.hq_city ?? '—'}</span>} hint={s.hq_state} />
            <Stat label="Founded" value={<span className="text-base">{s.founded_year ?? '—'}</span>} />
            <Stat label="Raising" value={<span className="text-base">{s.ask_inr ? formatINR(s.ask_inr) : '—'}</span>} />
            <Stat label="Pre-money" value={<span className="text-base">{s.pre_money_inr ? formatINR(s.pre_money_inr) : '—'}</span>} />
          </div>
        </Card>
        <Card title="Registry (MCA)">
          <div className="flex items-start gap-3">
            {verified ? <ShieldCheck className="w-5 h-5 shrink-0 text-emerald-600" /> : <ShieldAlert className="w-5 h-5 shrink-0 text-amber-600" />}
            <div className="text-sm">
              <p className="font-bold text-slate-900">{verified ? 'Active company' : s.mca?.company_status ? `Status: ${s.mca.company_status}` : 'Not verified'}</p>
              {s.cin && <p className="font-mono text-xs text-slate-600">CIN {s.cin}</p>}
              {s.mca?.company_name && <p className="text-slate-600">Registered as {s.mca.company_name}</p>}
              {!!s.mca?.directors?.length && <p className="text-slate-600">Directors: {s.mca.directors.join(', ')}</p>}
              {s.mca?.source && <p className="mt-1 text-xs text-slate-400">Source: {s.mca.source.replace('_', ' ')}</p>}
              {s.compliance_flags.length > 0 && (
                <ul className="mt-2 list-disc pl-4 text-amber-800">{s.compliance_flags.map(f => <li key={f}>{flagLabel(f)}</li>)}</ul>
              )}
            </div>
          </div>
        </Card>
        {s.profile.gtm && (
          <Card title="Go-to-market">
            <ul className="list-disc pl-4 text-sm text-slate-700 space-y-1">{s.profile.gtm.channels.map(c => <li key={c}>{c}</li>)}</ul>
            <p className="mt-2 text-sm text-slate-600"><b>Target:</b> {s.profile.gtm.target}</p>
          </Card>
        )}
      </div>
    </div>
  )
}

function Round({ startup: s }: { startup: StartupDetail }) {
  const round = s.profile.round
  if (!round) return <EmptyState title="No round terms yet" />
  const post = round.ask_inr + round.pre_money_inr
  return (
    <div className="grid gap-5 lg:grid-cols-3">
      <Card title="Terms" className="lg:col-span-1">
        <div className="grid grid-cols-2 gap-4">
          <Stat label="Raising" value={formatINR(round.ask_inr)} />
          <Stat label="Pre-money" value={formatINR(round.pre_money_inr)} />
          <Stat label="Post-money" value={formatINR(post)} hint={`${((round.ask_inr / post) * 100).toFixed(1)}% to new investors`} />
          <Stat label="Minimum raise" value={`${round.min_raise_pct}%`} />
        </div>
        <p className="mt-4 text-xs text-slate-500">
          On AURA3 a round runs as a DAO proposal: investors vote quadratically in AuraCoin and pledge into escrow;
          money is released in the milestone tranches below, with a 2% platform fee per release. Rounds open in the next release.
        </p>
      </Card>
      <Card title="Use of funds" className="lg:col-span-1">
        <ul className="space-y-2.5">
          {round.use_of_funds.map(u => (
            <li key={u.category}>
              <div className="flex justify-between text-sm"><span className="text-slate-700">{u.category}</span><b>{u.pct}%</b></div>
              <div className="mt-1 h-2 rounded-full bg-slate-100"><div className="h-2 rounded-full bg-[#0284c7]" style={{ width: `${u.pct}%` }} /></div>
            </li>
          ))}
        </ul>
      </Card>
      <Card title="Milestone tranches" className="lg:col-span-1">
        <ol className="relative border-l-2 border-slate-200 ml-2 space-y-4">
          {round.tranches.map((t, i) => (
            <li key={i} className="ml-4">
              <span className="absolute -left-[7px] mt-1 h-3 w-3 rounded-full border-2 border-white bg-[#0284c7]" />
              <p className="text-sm font-bold text-slate-900">Tranche {i + 1} · {t.pct}% · {formatINR(Math.round(round.ask_inr * t.pct / 100))}</p>
              <p className="text-sm text-slate-600">{t.title}{t.criteria ? ` — ${t.criteria}` : ''}</p>
              {t.due_days && <p className="text-xs text-slate-400">within {t.due_days} days</p>}
            </li>
          ))}
        </ol>
      </Card>
    </div>
  )
}
