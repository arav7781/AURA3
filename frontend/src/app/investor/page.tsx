'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { Coins, Search, Trophy } from 'lucide-react'
import { RequireRole } from '@/components/auth/RequireRole'
import { StartupCard } from '@/components/startups/StartupCard'
import { Card, EmptyState, ErrorNote, Spinner, STAGE_LABELS } from '@/components/ui'
import { useAuth } from '@/context/AuthContext'
import { useCatalogue, type CatalogueFilters } from '@/lib/api/hooks'
import { formatAC } from '@/lib/format'

export default function InvestorPage() {
  return (
    <RequireRole role="investor">
      <DealFlow />
    </RequireRole>
  )
}

const SELECT = 'rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm'

function DealFlow() {
  const { me, has } = useAuth()
  const [text, setText] = useState('')
  const [filters, setFilters] = useState<CatalogueFilters>({ sort: 'score' })
  const catalogue = useCatalogue(filters)

  useEffect(() => {
    const timer = setTimeout(() => setFilters(f => ({ ...f, q: text.trim() || undefined })), 250)
    return () => clearTimeout(timer)
  }, [text])

  const facets = catalogue.data?.facets
  const items = catalogue.data?.items ?? []

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 py-10">
      <div className="mb-8 flex flex-col gap-4 border-b border-slate-200 pb-6 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-[11px] font-mono uppercase tracking-widest text-jade-600 mb-2">Deal flow</p>
          <h1 className="font-display text-[2.15rem] font-semibold leading-tight tracking-[-0.02em] text-ink">Startups with evidence you can check</h1>
          <p className="mt-1 text-slate-600">Every score cites the slide it came from. Review, rank, and back the ones you believe in with AuraCoin.</p>
        </div>
        <div className="flex gap-2">
          <Link href="/rankings" className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-bold text-slate-800 hover:bg-slate-50">
            <Trophy className="w-4 h-4 text-amber-500" /> Community rankings
          </Link>
          <Link href="/wallet" className="inline-flex items-center gap-2 rounded-lg bg-amber-50 border border-amber-200 px-4 py-2.5 text-sm font-bold text-slate-800">
            <Coins className="w-4 h-4 text-amber-600" /> {formatAC(me?.balances.available ?? 0)}
          </Link>
        </div>
      </div>

      {!has('full_report') && (
        <div className="mb-6 rounded-xl border border-jade-200 bg-jade-50 px-5 py-4 text-sm text-slate-700">
          You are on <b>Scout</b>: AI scores and summaries for every startup. Full reports, the deck evidence viewer,
          the embedding map and voting come with <Link href="/wallet#plans" className="font-bold text-jade-600 hover:underline">Angel</Link>.
        </div>
      )}

      <div className="mb-6 flex flex-wrap gap-2">
        <label className="relative flex-1 min-w-[14rem]">
          <Search className="pointer-events-none absolute left-3 top-1/2 w-4 h-4 -translate-y-1/2 text-slate-400" />
          <span className="sr-only">Search startups</span>
          <input value={text} onChange={e => setText(e.target.value)} placeholder="Search by name, domain or what they do"
                 className="w-full rounded-lg border border-slate-300 py-2 pl-9 pr-3 text-sm" />
        </label>
        <select aria-label="Domain" className={SELECT} value={filters.domain ?? ''} onChange={e => setFilters(f => ({ ...f, domain: e.target.value || undefined }))}>
          <option value="">All domains</option>
          {Object.entries(facets?.domains ?? {}).sort().map(([domain, n]) => <option key={domain} value={domain}>{domain} ({n})</option>)}
        </select>
        <select aria-label="Stage" className={SELECT} value={filters.stage ?? ''} onChange={e => setFilters(f => ({ ...f, stage: e.target.value || undefined }))}>
          <option value="">All stages</option>
          {Object.entries(facets?.stages ?? {}).map(([stage, n]) => <option key={stage} value={stage}>{STAGE_LABELS[stage] ?? stage} ({n})</option>)}
        </select>
        <select aria-label="Minimum AI score" className={SELECT} value={filters.min_score ?? ''} onChange={e => setFilters(f => ({ ...f, min_score: e.target.value ? Number(e.target.value) : undefined }))}>
          <option value="">Any score</option>
          {[5, 6, 6.5, 7].map(v => <option key={v} value={v}>Score ≥ {v}</option>)}
        </select>
        <select aria-label="Sort" className={SELECT} value={filters.sort} onChange={e => setFilters(f => ({ ...f, sort: e.target.value as CatalogueFilters['sort'] }))}>
          <option value="score">Highest AI score</option>
          <option value="newest">Newest</option>
          <option value="ask">Largest raise</option>
          <option value="name">Name</option>
        </select>
      </div>

      {catalogue.isError && <ErrorNote error={catalogue.error} />}
      {catalogue.isPending ? <Spinner label="Loading startups" /> : items.length === 0 ? (
        <EmptyState title="No startups match">Try fewer filters.</EmptyState>
      ) : (
        <>
          <p className="mb-3 text-sm text-slate-500">{items.length} startup{items.length === 1 ? '' : 's'}</p>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {items.map(startup => <StartupCard key={startup.id} startup={startup} />)}
          </div>
        </>
      )}

      <Card title="How scores are made" className="mt-10">
        <p className="text-sm text-slate-600">
          Decks are read by TitanOCR, split into cited passages and indexed for hybrid search. An agent researches the
          market, then a fixed rubric scores seven dimensions; the overall score is computed from them, and registry
          problems (struck off, name mismatch) cap the label. Deck figures are checked against retrieved sources.
        </p>
      </Card>
    </div>
  )
}
