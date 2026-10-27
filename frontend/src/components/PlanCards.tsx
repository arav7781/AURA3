'use client'

import { Check } from 'lucide-react'
import { clsx } from 'clsx'
import { usePlans } from '@/lib/api/hooks'
import type { Plan } from '@/lib/api/types'
import { formatAC } from '@/lib/format'
import { Spinner } from '@/components/ui'

/** The three investor plans. ``action`` renders each card's button (choose, current, sign up…). */
export function PlanCards({ current, action }: { current?: string | null; action: (plan: Plan) => React.ReactNode }) {
  const plans = usePlans()
  if (plans.isPending) return <Spinner />
  const features = plans.data?.features ?? {}
  return (
    <div className="grid gap-4 md:grid-cols-3">
      {(plans.data?.plans ?? []).map(plan => (
        <div key={plan.id} className={clsx('flex flex-col rounded-2xl border bg-white p-6 shadow-sm',
          plan.id === 'angel' ? 'border-jade-600 ring-1 ring-jade-600' : 'border-slate-200')}>
          <div className="flex items-baseline justify-between">
            <h3 className="text-lg font-black text-slate-900">{plan.name}</h3>
            {current === plan.id && <span className="text-[11px] font-mono font-bold uppercase text-jade-600">Current</span>}
          </div>
          <p className="mt-1 text-sm text-slate-600 min-h-[2.5rem]">{plan.blurb}</p>
          <p className="mt-4 text-3xl font-black text-slate-900">
            {plan.price_inr_month ? `₹${plan.price_inr_month.toLocaleString('en-IN')}` : 'Free'}
            {plan.price_inr_month > 0 && <span className="text-sm font-semibold text-slate-500"> / month</span>}
          </p>
          <p className="mt-1 text-sm font-semibold text-amber-700">
            {plan.monthly_ac ? `${formatAC(plan.monthly_ac * 100)} every month` : `${formatAC(plan.welcome_ac * 100)} welcome credit`}
          </p>
          <ul className="mt-4 space-y-2 text-sm text-slate-700 flex-1">
            <li className="flex gap-2"><Check className="w-4 h-4 shrink-0 text-emerald-600" />Copilot: {plan.copilot_daily ? `${plan.copilot_daily} messages a day` : 'unlimited'}</li>
            <li className="flex gap-2"><Check className="w-4 h-4 shrink-0 text-emerald-600" />Code sandbox: {plan.sandbox_daily} runs a day</li>
            {plan.features.filter(f => f !== 'copilot').map(f => (
              <li key={f} className="flex gap-2"><Check className="w-4 h-4 shrink-0 text-emerald-600" />{features[f] ?? f}</li>
            ))}
          </ul>
          <div className="mt-6">{action(plan)}</div>
        </div>
      ))}
    </div>
  )
}
