'use client'

import Link from 'next/link'
import { PlanCards } from '@/components/PlanCards'
import { Card } from '@/components/ui'
import { useAuth } from '@/context/AuthContext'

export default function PricingPage() {
  const { me } = useAuth()
  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 py-12 space-y-8">
      <div className="text-center">
        <p className="text-[11px] font-mono uppercase tracking-widest text-jade-600 mb-2">Pricing</p>
        <h1 className="font-display text-[2.7rem] font-semibold leading-tight tracking-[-0.02em] text-ink">Investors subscribe. Founders list free.</h1>
        <p className="mt-2 text-slate-600 max-w-2xl mx-auto">
          Plans include monthly AuraCoin for voting and pledging in DAO rounds. Founders pay nothing to list or be
          evaluated; AURA3 keeps 2% of each milestone tranche released to them.
        </p>
      </div>
      <PlanCards current={me?.plan?.id} action={plan => (
        <Link href={me ? '/wallet#plans' : `/register?role=investor`}
              className="block w-full rounded-lg bg-jade-600 px-4 py-2 text-center text-sm font-bold text-white hover:brightness-110">
          {me ? (me.plan?.id === plan.id ? 'Your plan' : `Choose ${plan.name}`) : `Start with ${plan.name}`}
        </Link>
      )} />
      <div className="grid gap-4 md:grid-cols-2">
        <Card title="For founders">
          <ul className="list-disc pl-5 space-y-1 text-sm text-slate-700">
            <li>Free listing, AI evaluation (five a day) and evidence report</li>
            <li>Investor reviews and rankings on your startup</li>
            <li>2% success fee on each tranche released from escrow</li>
          </ul>
          <Link href="/register?role=startup" className="mt-4 inline-block text-sm font-bold text-jade-600 hover:underline">List your startup →</Link>
        </Card>
        <Card title="About AuraCoin">
          <p className="text-sm text-slate-700">
            AuraCoin (AC) is a closed-loop utility credit: granted with plans, used for quadratic votes (n votes cost
            n² AC, returned after the vote) and escrowed pledges. It is never sold, transferred between users or
            redeemed for money. Demo plans activate without payment.
          </p>
        </Card>
      </div>
    </div>
  )
}
