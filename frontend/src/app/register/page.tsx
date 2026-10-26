'use client'

import { Suspense, useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import { Check, Loader2, Rocket, TrendingUp } from 'lucide-react'
import { clsx } from 'clsx'
import { AuthShell, Field, FormError } from '@/components/auth/AuthShell'
import { getDashboardPath, useAuth, type PlanId, type UserRole } from '@/context/AuthContext'
import { api, errorMessage } from '@/lib/api/client'
import { formatAC } from '@/lib/format'

interface Plan {
  id: PlanId
  name: string
  price_inr_month: number
  monthly_ac: number
  welcome_ac: number
  blurb: string
}

export default function RegisterPage() {
  return (
    <Suspense>
      <RegisterForm />
    </Suspense>
  )
}

function RegisterForm() {
  const router = useRouter()
  const params = useSearchParams()
  const { me, register } = useAuth()
  const [role, setRole] = useState<UserRole>(params.get('role') === 'startup' ? 'startup' : 'investor')
  const [plan, setPlan] = useState<PlanId>('scout')
  const [name, setName] = useState('')
  const [startupName, setStartupName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const plans = useQuery({
    queryKey: ['plans'],
    queryFn: () => api<{ plans: Plan[]; demo_payments: boolean }>('/api/plans'),
    staleTime: Infinity,
  })

  useEffect(() => {
    if (me && !busy) router.replace(getDashboardPath(me.user.role))
  }, [me, busy, router])

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const created = await register({
        email: email.trim(),
        password,
        name: name.trim(),
        role,
        ...(role === 'investor' ? { plan } : { startup_name: startupName.trim() || undefined }),
      })
      router.replace(getDashboardPath(created.user.role))
    } catch (err) {
      setError(errorMessage(err))
      setBusy(false)
    }
  }

  const roles: { id: UserRole; label: string; icon: typeof TrendingUp; text: string }[] = [
    { id: 'investor', label: 'Investor', icon: TrendingUp, text: 'Review, rank and back startups with AuraCoin' },
    { id: 'startup', label: 'Founder', icon: Rocket, text: 'Publish your deck, get an AI evaluation, raise' },
  ]

  return (
    <AuthShell
      title="Create your account"
      subtitle="One account per person. Your session is a signed token in a secure cookie; nothing is stored in the browser."
      footer={<>Already have an account? <Link href="/login" className="font-semibold text-[#0284c7] hover:underline">Sign in</Link></>}
    >
      <form onSubmit={submit} className="space-y-4">
        <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label="Account type">
          {roles.map(option => (
            <button
              key={option.id}
              type="button"
              role="radio"
              aria-checked={role === option.id}
              onClick={() => setRole(option.id)}
              className={clsx(
                'rounded-lg border p-3 text-left transition-colors',
                role === option.id ? 'border-[#0284c7] bg-sky-50 ring-1 ring-[#0284c7]' : 'border-slate-200 hover:bg-slate-50',
              )}
            >
              <option.icon className={clsx('w-4 h-4', role === option.id ? 'text-[#0284c7]' : 'text-slate-400')} />
              <span className="mt-1.5 block text-sm font-bold text-slate-900">{option.label}</span>
              <span className="block text-xs text-slate-500 leading-snug">{option.text}</span>
            </button>
          ))}
        </div>

        <Field label="Your name" autoComplete="name" required maxLength={120} value={name} onChange={e => setName(e.target.value)} />
        {role === 'startup' && (
          <Field label="Startup name" maxLength={120} value={startupName} onChange={e => setStartupName(e.target.value)}
                 hint="You can change it and add your deck after signing up." />
        )}
        <Field label="Email" type="email" autoComplete="email" required value={email} onChange={e => setEmail(e.target.value)} />
        <Field label="Password" type="password" autoComplete="new-password" required minLength={10} value={password}
               onChange={e => setPassword(e.target.value)} hint="At least 10 characters." />

        {role === 'investor' && (
          <fieldset>
            <legend className="text-[11px] font-mono font-bold uppercase tracking-widest text-slate-600 mb-1.5">Plan</legend>
            <div className="space-y-2">
              {(plans.data?.plans ?? []).map(option => (
                <label
                  key={option.id}
                  className={clsx(
                    'flex cursor-pointer gap-3 rounded-lg border p-3 transition-colors',
                    plan === option.id ? 'border-[#0284c7] bg-sky-50 ring-1 ring-[#0284c7]' : 'border-slate-200 hover:bg-slate-50',
                  )}
                >
                  <input type="radio" name="plan" value={option.id} checked={plan === option.id} onChange={() => setPlan(option.id)} className="sr-only" />
                  <span className={clsx('mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border',
                    plan === option.id ? 'border-[#0284c7] bg-[#0284c7]' : 'border-slate-300')}>
                    {plan === option.id && <Check className="h-3 w-3 text-white" />}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-baseline justify-between gap-2">
                      <span className="text-sm font-bold text-slate-900">{option.name}</span>
                      <span className="text-sm font-semibold text-slate-700">
                        {option.price_inr_month ? `₹${option.price_inr_month.toLocaleString('en-IN')}/mo` : 'Free'}
                      </span>
                    </span>
                    <span className="block text-xs text-slate-500">{option.blurb}</span>
                    <span className="block text-xs font-mono text-slate-600 mt-0.5">
                      {option.monthly_ac ? `${formatAC(option.monthly_ac * 100)} every month` : `${formatAC(option.welcome_ac * 100)} welcome credit`}
                    </span>
                  </span>
                </label>
              ))}
            </div>
            {plans.data?.demo_payments && (
              <p className="mt-2 text-xs text-slate-500">Demo: paid plans are activated without payment. AuraCoin is a closed-loop credit and cannot be cashed out.</p>
            )}
          </fieldset>
        )}

        <FormError message={error} />
        <button
          type="submit"
          disabled={busy}
          className="w-full inline-flex items-center justify-center gap-2 rounded-lg bg-[#0284c7] px-4 py-2.5 font-bold text-white hover:brightness-110 disabled:opacity-60"
        >
          {busy && <Loader2 className="w-4 h-4 animate-spin" />}
          Create account
        </button>
      </form>
    </AuthShell>
  )
}
