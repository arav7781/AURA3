'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useQueryClient } from '@tanstack/react-query'
import { ArrowDown, ArrowUp, X } from 'lucide-react'
import { clsx } from 'clsx'
import { RequireRole } from '@/components/auth/RequireRole'
import { Button, Card, EmptyState, ScoreRing, Spinner } from '@/components/ui'
import { useAuth } from '@/context/AuthContext'
import { api, errorMessage } from '@/lib/api/client'
import { useCatalogue, useRankings } from '@/lib/api/hooks'
import type { StartupCard } from '@/lib/api/types'

export default function RankingsPage() {
  return (
    <RequireRole>
      <Rankings />
    </RequireRole>
  )
}

function Rankings() {
  const rankings = useRankings()
  const { userRole } = useAuth()
  if (rankings.isPending) return <Spinner label="Loading rankings" />
  const data = rankings.data
  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 py-10 space-y-6">
      <div>
        <p className="text-[11px] font-mono uppercase tracking-widest text-jade-600 mb-2">Community</p>
        <h1 className="font-display text-[2.15rem] font-semibold leading-tight tracking-[-0.02em] text-ink">What investors rank highest</h1>
        <p className="mt-1 text-slate-600">{data?.method} {data?.ballots ?? 0} investor list{data?.ballots === 1 ? '' : 's'} so far.</p>
      </div>
      <div className="grid gap-6 lg:grid-cols-5">
        <Card title="Leaderboard" className="lg:col-span-3">
          {!data?.board.length ? <EmptyState title="No rankings yet" /> : (
            <div className="overflow-x-auto -mx-5">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-[11px] font-mono uppercase tracking-widest text-slate-500">
                    <th className="px-5 py-2">#</th><th className="py-2">Startup</th><th className="py-2 text-right">Community</th>
                    <th className="py-2 text-right">AI</th><th className="px-5 py-2 text-right" title="AI rank minus community rank">Gap</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {data.board.map(row => (
                    <tr key={row.id}>
                      <td className="px-5 py-2.5 font-mono text-slate-500">{row.community_rank}</td>
                      <td className="py-2.5">
                        <Link href={`/startups/${row.slug}`} className="font-bold text-slate-900 hover:text-jade-600">{row.name}</Link>
                        <span className="block text-xs text-slate-500">{row.domain} · on {row.rankers} list{row.rankers === 1 ? '' : 's'}</span>
                      </td>
                      <td className="py-2.5 text-right font-mono font-bold text-slate-900">{row.community_score.toFixed(1)}</td>
                      <td className="py-2.5 text-right font-mono text-slate-700">{row.ai_score?.toFixed(1) ?? '—'}</td>
                      <td className={clsx('px-5 py-2.5 text-right font-mono font-semibold',
                        (row.rank_gap ?? 0) > 0 ? 'text-emerald-700' : (row.rank_gap ?? 0) < 0 ? 'text-rose-700' : 'text-slate-400')}>
                        {row.rank_gap == null ? '—' : row.rank_gap > 0 ? `+${row.rank_gap}` : row.rank_gap}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="px-5 pt-3 text-xs text-slate-500">Gap: positive when investors rank a startup above where the AI score puts it.</p>
            </div>
          )}
        </Card>
        {userRole === 'investor'
          ? <MyList key={data?.mine.map(s => s.id).join()} initial={data?.mine ?? []} />
          : <Card title="Your list" className="lg:col-span-2"><p className="text-sm text-slate-600">Investors rank their top 10; founders see how the community and the AI compare.</p></Card>}
      </div>
    </div>
  )
}

function MyList({ initial }: { initial: StartupCard[] }) {
  const client = useQueryClient()
  const catalogue = useCatalogue({ sort: 'score' })
  const [list, setList] = useState<StartupCard[]>(initial)
  const [state, setState] = useState<{ busy: boolean; note: string | null }>({ busy: false, note: null })
  const available = (catalogue.data?.items ?? []).filter(s => !list.some(l => l.id === s.id))
  const move = (index: number, by: number) => setList(items => {
    const next = [...items]
    const [item] = next.splice(index, 1)
    next.splice(index + by, 0, item)
    return next
  })
  const save = async () => {
    setState({ busy: true, note: null })
    try {
      await api('/api/me/ranking', { method: 'PUT', body: { startup_ids: list.map(s => s.id) } })
      await client.invalidateQueries({ queryKey: ['rankings'] })
      setState({ busy: false, note: 'Saved' })
    } catch (err) {
      setState({ busy: false, note: errorMessage(err) })
    }
  }
  return (
    <Card title="Your top 10" className="lg:col-span-2" action={<Button busy={state.busy} onClick={save}>Save</Button>}>
      {state.note && <p className="mb-3 text-sm text-slate-600">{state.note}</p>}
      <ol className="space-y-2">
        {list.map((s, i) => (
          <li key={s.id} className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2">
            <span className="w-5 font-mono text-sm text-slate-500">{i + 1}</span>
            <ScoreRing score={s.ai_score} size={30} />
            <span className="flex-1 truncate text-sm font-semibold text-slate-900">{s.name}</span>
            <button aria-label={`Move ${s.name} up`} disabled={i === 0} onClick={() => move(i, -1)} className="p-1 text-slate-500 disabled:opacity-30"><ArrowUp className="w-4 h-4" /></button>
            <button aria-label={`Move ${s.name} down`} disabled={i === list.length - 1} onClick={() => move(i, 1)} className="p-1 text-slate-500 disabled:opacity-30"><ArrowDown className="w-4 h-4" /></button>
            <button aria-label={`Remove ${s.name}`} onClick={() => setList(items => items.filter(x => x.id !== s.id))} className="p-1 text-slate-400 hover:text-rose-600"><X className="w-4 h-4" /></button>
          </li>
        ))}
      </ol>
      {list.length < 10 && (
        <select aria-label="Add a startup" value="" onChange={e => {
          const pick = available.find(s => s.id === e.target.value)
          if (pick) setList(items => [...items, pick])
        }} className="mt-3 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm">
          <option value="">Add a startup…</option>
          {available.map(s => <option key={s.id} value={s.id}>{s.name} · {s.domain}{s.ai_score != null ? ` · AI ${s.ai_score.toFixed(1)}` : ''}</option>)}
        </select>
      )}
    </Card>
  )
}
