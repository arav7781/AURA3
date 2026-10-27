'use client'

import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ArrowDownLeft, ArrowUpRight, Coins } from 'lucide-react'
import { clsx } from 'clsx'
import { RequireRole } from '@/components/auth/RequireRole'
import { PlanCards } from '@/components/PlanCards'
import { Button, Card, EmptyState, Spinner, Stat } from '@/components/ui'
import { useAuth } from '@/context/AuthContext'
import { api, errorMessage } from '@/lib/api/client'
import { useLedger } from '@/lib/api/hooks'
import { formatAC } from '@/lib/format'

const KIND_LABELS: Record<string, string> = {
  welcome: 'Welcome credit', plan_grant: 'Monthly plan grant', plan_topup: 'Upgrade top-up',
  vote_lock: 'Votes locked', vote_unlock: 'Votes returned', pledge: 'Pledge to escrow', refund: 'Refund',
  release: 'Tranche release', fee: 'Platform fee',
}

export default function WalletPage() {
  return (
    <RequireRole>
      <Wallet />
    </RequireRole>
  )
}

function Wallet() {
  const { me, refresh } = useAuth()
  const ledger = useLedger()
  const client = useQueryClient()
  const [pending, setPending] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  if (!me) return <Spinner />
  const investor = me.user.role === 'investor'
  const b = me.balances

  const choose = async (plan: string) => {
    setPending(plan)
    setMessage(null)
    try {
      const result = await api<{ effective: string; granted_minor: number }>('/api/me/plan', {
        method: 'POST', body: { plan }, idempotencyKey: crypto.randomUUID(),
      })
      await Promise.all([refresh(), client.invalidateQueries({ queryKey: ['ledger'] })])
      setMessage(result.effective === 'now'
        ? `Plan active.${result.granted_minor ? ` ${formatAC(result.granted_minor)} added to your wallet.` : ''}`
        : 'Downgrade scheduled for the end of this billing period.')
    } catch (err) {
      setMessage(errorMessage(err))
    } finally {
      setPending(null)
    }
  }

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 py-10 space-y-6">
      <div>
        <p className="text-[11px] font-mono uppercase tracking-widest text-jade-600 mb-2">Wallet</p>
        <h1 className="font-display text-[2.15rem] font-semibold leading-tight tracking-[-0.02em] text-ink">AuraCoin</h1>
        <p className="mt-1 text-slate-600">A closed-loop credit for voting and pledging inside AURA3. It comes with your plan; it cannot be bought, sold, transferred or cashed out.</p>
      </div>

      <Card>
        <div className="grid gap-6 sm:grid-cols-4">
          <Stat label="Available" value={<span className="inline-flex items-center gap-1.5"><Coins className="w-5 h-5 text-amber-500" />{formatAC(b.available)}</span>} />
          <Stat label="Locked in votes" value={formatAC(b.locked)} hint="Returned when voting closes" />
          <Stat label="In escrow" value={formatAC(b.escrowed)} hint="Pledged to open rounds" />
          {investor && me.plan && (
            <Stat label="Plan" value={me.plan.name} hint={me.plan.next_grant_at ? `Next grant ${new Date(me.plan.next_grant_at).toLocaleDateString()}` : undefined} />
          )}
        </div>
        {me.plan?.pending_plan && <p className="mt-4 text-sm text-amber-800">Switching to {me.plan.pending_plan} at the end of this period.</p>}
      </Card>

      {investor ? (
        <section id="plans" className="scroll-mt-20">
          <h2 className="mb-3 text-lg font-black text-slate-900">Plans</h2>
          {message && <p className="mb-3 rounded-lg border border-jade-200 bg-jade-50 px-4 py-2 text-sm text-slate-700">{message}</p>}
          <PlanCards current={me.plan?.id} action={plan => (
            <Button className="w-full" variant={plan.id === me.plan?.id ? 'secondary' : 'primary'}
                    disabled={plan.id === me.plan?.id} busy={pending === plan.id} onClick={() => choose(plan.id)}>
              {plan.id === me.plan?.id ? 'Your plan' : `Switch to ${plan.name}`}
            </Button>
          )} />
          <p className="mt-3 text-xs text-slate-500">Demo: plans activate without payment. Upgrades top up the difference immediately; downgrades take effect at the next period.</p>
        </section>
      ) : (
        <Card title="For founders">
          <p className="text-sm text-slate-600">Listing, evaluations and the deck builder are free. When a round passes, AURA3 keeps 2% of each tranche released to you from escrow; the rest lands in this wallet.</p>
        </Card>
      )}

      <Card title="History">
        {ledger.isPending ? <Spinner /> : !ledger.data?.items.length ? <EmptyState title="No transactions yet" /> : (
          <ul className="divide-y divide-slate-100">
            {ledger.data.items.map(item => (
              <li key={item.id} className="flex items-center gap-3 py-2.5 text-sm">
                {item.amount_minor >= 0 ? <ArrowDownLeft className="w-4 h-4 text-emerald-600" /> : <ArrowUpRight className="w-4 h-4 text-rose-600" />}
                <span className="flex-1">
                  <span className="font-semibold text-slate-800">{KIND_LABELS[item.kind] ?? item.kind.replace(/_/g, ' ')}</span>
                  {item.memo && <span className="block text-xs text-slate-500">{item.memo}</span>}
                </span>
                <span className="text-xs text-slate-400">{new Date(item.created_at).toLocaleString()}</span>
                <span className={clsx('w-28 text-right font-mono font-semibold', item.amount_minor >= 0 ? 'text-emerald-700' : 'text-rose-700')}>
                  {item.amount_minor >= 0 ? '+' : ''}{formatAC(item.amount_minor)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  )
}
