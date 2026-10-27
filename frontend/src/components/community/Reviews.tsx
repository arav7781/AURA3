'use client'

import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Star } from 'lucide-react'
import { clsx } from 'clsx'
import { useReviews } from '@/lib/api/hooks'
import { api, errorMessage } from '@/lib/api/client'
import { useAuth } from '@/context/AuthContext'
import { Button, Card, EmptyState, Spinner } from '@/components/ui'

const DIMENSIONS = ['team', 'market', 'product', 'traction'] as const
type Ratings = Record<(typeof DIMENSIONS)[number], number>

function Stars({ value, onChange, label }: { value: number; onChange?: (v: number) => void; label: string }) {
  return (
    <span className="inline-flex" role={onChange ? 'radiogroup' : undefined} aria-label={label}>
      {[1, 2, 3, 4, 5].map(n => (
        <button key={n} type="button" disabled={!onChange} onClick={() => onChange?.(n)} aria-label={`${n} of 5`}
                role={onChange ? 'radio' : undefined} aria-checked={onChange ? value === n : undefined}
                className={clsx('p-0.5', onChange ? 'cursor-pointer' : 'cursor-default')}>
          <Star className={clsx('w-4 h-4', n <= value ? 'fill-amber-400 text-amber-400' : 'text-slate-300')} />
        </button>
      ))}
    </span>
  )
}

function ReviewForm({ startupId, initial }: { startupId: string; initial: (Ratings & { note: string }) | null }) {
  const client = useQueryClient()
  const [ratings, setRatings] = useState<Ratings>(initial ?? { team: 3, market: 3, product: 3, traction: 3 })
  const [note, setNote] = useState(initial?.note ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const save = async () => {
    setBusy(true)
    setError(null)
    try {
      await api(`/api/startups/${startupId}/review`, { method: 'PUT', body: { ...ratings, note } })
      await client.invalidateQueries({ queryKey: ['reviews', startupId] })
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <Card title={initial ? 'Your review' : 'Review this startup'}>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {DIMENSIONS.map(d => (
          <label key={d} className="block">
            <span className="block text-xs font-semibold capitalize text-slate-700">{d}</span>
            <Stars value={ratings[d]} label={d} onChange={v => setRatings(r => ({ ...r, [d]: v }))} />
          </label>
        ))}
      </div>
      <textarea value={note} onChange={e => setNote(e.target.value)} maxLength={2000} rows={3}
                placeholder="What convinced you, and what would you need to see?"
                className="mt-3 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
      {error && <p className="mt-2 text-sm text-rose-700">{error}</p>}
      <div className="mt-3 flex justify-end"><Button busy={busy} onClick={save}>{initial ? 'Update review' : 'Post review'}</Button></div>
    </Card>
  )
}

export function Reviews({ startupId, isOwner }: { startupId: string; isOwner: boolean }) {
  const reviews = useReviews(startupId)
  const { userRole } = useAuth()
  if (reviews.isPending) return <Spinner />
  const data = reviews.data
  return (
    <div className="space-y-5">
      {data && data.summary.count > 0 && (
        <Card title={`Investor consensus · ${data.summary.count} review${data.summary.count === 1 ? '' : 's'}`}>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
            {DIMENSIONS.map(d => (
              <div key={d}>
                <p className="text-xs font-semibold capitalize text-slate-600">{d}</p>
                <p className="text-lg font-black text-slate-900">{data.summary[d]?.toFixed(1)}<span className="text-xs text-slate-400"> / 5</span></p>
              </div>
            ))}
            <div>
              <p className="text-xs font-semibold text-slate-600">Overall</p>
              <p className="text-lg font-black text-[#0284c7]">{data.summary.average?.toFixed(2)}</p>
            </div>
          </div>
          {isOwner && <p className="mt-3 text-xs text-slate-500">Reviewers are anonymous to founders.</p>}
        </Card>
      )}
      {userRole === 'investor' && <ReviewForm key={data?.mine?.id ?? 'new'} startupId={startupId} initial={data?.mine ?? null} />}
      {data?.items.length ? (
        <ul className="space-y-3">
          {data.items.map(review => (
            <li key={review.id} className="rounded-xl border border-slate-200 bg-white p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm font-bold text-slate-900">
                  {review.reviewer.name}
                  {review.reviewer.plan && <span className="ml-2 text-[11px] font-mono uppercase text-slate-500">{review.reviewer.plan}</span>}
                </p>
                <span className="text-xs text-slate-500">{new Date(review.created_at).toLocaleDateString()}</span>
              </div>
              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
                {DIMENSIONS.map(d => <span key={d} className="inline-flex items-center gap-1 text-xs capitalize text-slate-600">{d} <Stars value={review[d]} label={d} /></span>)}
              </div>
              {review.note && <p className="mt-2 text-sm text-slate-700">{review.note}</p>}
            </li>
          ))}
        </ul>
      ) : <EmptyState title="No reviews yet">{userRole === 'investor' ? 'Be the first to review.' : null}</EmptyState>}
    </div>
  )
}
