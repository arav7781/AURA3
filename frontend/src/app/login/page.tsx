'use client'

import { Suspense, useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import { Loader2, LogIn, UserRound } from 'lucide-react'
import { AuthShell, Field, FormError, safeNext } from '@/components/auth/AuthShell'
import { getDashboardPath, useAuth } from '@/context/AuthContext'
import { api, errorMessage } from '@/lib/api/client'

interface DemoAccount {
  email: string
  name: string
  role: 'investor' | 'startup'
  plan?: string | null
  headline?: string | null
}

interface DemoAccounts {
  enabled: boolean
  accounts: DemoAccount[]
  password?: string
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  )
}

function LoginForm() {
  const router = useRouter()
  const next = safeNext(useSearchParams().get('next'))
  const { me, login } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const demo = useQuery({
    queryKey: ['demo-accounts'],
    queryFn: () => api<DemoAccounts>('/api/public/demo-accounts'),
    staleTime: Infinity,
  })

  useEffect(() => {
    if (me) router.replace(next ?? getDashboardPath(me.user.role))
  }, [me, next, router])

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const signedIn = await login(email.trim(), password)
      router.replace(next ?? getDashboardPath(signedIn.user.role))
    } catch (err) {
      setError(errorMessage(err))
      setBusy(false)
    }
  }

  const accounts = demo.data?.enabled ? demo.data.accounts : []

  return (
    <AuthShell
      title="Sign in"
      subtitle="Investors review and rank startups; founders publish decks and raise in AuraCoin."
      footer={<>New to AURA3? <Link href="/register" className="font-semibold text-[#0284c7] hover:underline">Create an account</Link></>}
    >
      <form onSubmit={submit} className="space-y-4">
        <Field label="Email" type="email" autoComplete="email" required value={email} onChange={e => setEmail(e.target.value)} />
        <Field label="Password" type="password" autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} />
        <FormError message={error} />
        <button
          type="submit"
          disabled={busy}
          className="w-full inline-flex items-center justify-center gap-2 rounded-lg bg-[#0284c7] px-4 py-2.5 font-bold text-white hover:brightness-110 disabled:opacity-60"
        >
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <LogIn className="w-4 h-4" />}
          Sign in
        </button>
      </form>

      {accounts.length > 0 && (
        <div className="mt-6 border-t border-slate-200 pt-5">
          <p className="text-[11px] font-mono font-bold uppercase tracking-widest text-slate-600">Demo accounts</p>
          <p className="mt-1 text-xs text-slate-500">
            {demo.data?.password ? <>Password for every demo account: <code className="font-mono text-slate-800">{demo.data.password}</code>. </> : null}
            Pick one to fill the form.
          </p>
          <ul className="mt-3 max-h-64 overflow-y-auto divide-y divide-slate-100 rounded-lg border border-slate-200">
            {accounts.map(account => (
              <li key={account.email}>
                <button
                  type="button"
                  onClick={() => {
                    setEmail(account.email)
                    if (demo.data?.password) setPassword(demo.data.password)
                  }}
                  className="w-full flex items-center gap-3 px-3 py-2 text-left hover:bg-slate-50"
                >
                  <UserRound className="w-4 h-4 shrink-0 text-slate-400" />
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-semibold text-slate-900 truncate">{account.name}</span>
                    <span className="block text-xs text-slate-500 truncate">{account.headline ?? account.email}</span>
                  </span>
                  <span className="text-[10px] font-mono font-bold uppercase text-slate-500">
                    {account.role === 'investor' ? account.plan ?? 'investor' : 'founder'}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </AuthShell>
  )
}
