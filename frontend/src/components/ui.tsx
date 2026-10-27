'use client'

import Link from 'next/link'
import { clsx } from 'clsx'
import { Loader2, Lock } from 'lucide-react'

export function Card({ title, action, children, className }: {
  title?: React.ReactNode
  action?: React.ReactNode
  children: React.ReactNode
  className?: string
}) {
  return (
    <section className={clsx('bg-white border border-slate-200 rounded-xl shadow-sm', className)}>
      {(title || action) && (
        <header className="flex items-center justify-between gap-3 px-5 py-3.5 border-b border-slate-100">
          <h2 className="text-[11px] font-bold font-mono uppercase tracking-widest text-slate-600">{title}</h2>
          {action}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  )
}

const BADGE = {
  slate: 'bg-slate-100 text-slate-700 border-slate-200',
  jade: 'bg-jade-50 text-jade-700 border-jade-200',
  green: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  amber: 'bg-amber-50 text-amber-800 border-amber-200',
  red: 'bg-rose-50 text-rose-700 border-rose-200',
  marigold: 'bg-marigold-50 text-marigold-700 border-marigold-300',
}

export function Badge({ tone = 'slate', children, title }: { tone?: keyof typeof BADGE; children: React.ReactNode; title?: string }) {
  return (
    <span title={title} className={clsx('inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold', BADGE[tone])}>
      {children}
    </span>
  )
}

export const recommendationTone = (label: string | null | undefined): keyof typeof BADGE =>
  label === 'Strong Buy' || label === 'Buy' ? 'green' : label === 'Hold' ? 'amber' : label === 'Pass' ? 'red' : 'slate'

export function RecommendationBadge({ label }: { label: string | null | undefined }) {
  if (!label) return <Badge>Not evaluated</Badge>
  return <Badge tone={recommendationTone(label)}>{label}</Badge>
}

export function ScoreRing({ score, size = 64 }: { score: number | null | undefined; size?: number }) {
  const value = score ?? 0
  const colour = value >= 6.5 ? 'var(--color-jade-500)' : value >= 5 ? 'var(--color-marigold-400)' : '#d6455d'
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }} aria-label={score == null ? 'No AI score' : `AI score ${score} out of 10`}>
      <svg viewBox="0 0 36 36" className="-rotate-90" style={{ width: size, height: size }}>
        <circle cx="18" cy="18" r="15.9" fill="none" stroke="#e2e8f0" strokeWidth="3" />
        {score != null && (
          <circle cx="18" cy="18" r="15.9" fill="none" stroke={colour} strokeWidth="3" strokeLinecap="round"
                  strokeDasharray={`${value * 10} 100`} />
        )}
      </svg>
      <span className="absolute inset-0 flex items-center justify-center font-black text-slate-900" style={{ fontSize: size * 0.28 }}>
        {score == null ? '—' : score.toFixed(1)}
      </span>
    </div>
  )
}

export function Stat({ label, value, hint }: { label: string; value: React.ReactNode; hint?: React.ReactNode }) {
  return (
    <div>
      <p className="text-[11px] font-mono uppercase tracking-widest text-slate-500">{label}</p>
      <p className="mt-1 text-xl font-black text-slate-900">{value}</p>
      {hint && <p className="text-xs text-slate-500 mt-0.5">{hint}</p>}
    </div>
  )
}

export function Tabs<T extends string>({ tabs, active, onChange }: {
  tabs: { id: T; label: string; locked?: boolean }[]
  active: T
  onChange: (id: T) => void
}) {
  return (
    <div role="tablist" className="flex gap-1 overflow-x-auto border-b border-slate-200">
      {tabs.map(tab => (
        <button
          key={tab.id}
          role="tab"
          aria-selected={active === tab.id}
          onClick={() => onChange(tab.id)}
          className={clsx(
            'shrink-0 inline-flex items-center gap-1.5 px-4 py-2.5 text-sm font-semibold border-b-2 -mb-px transition-colors',
            active === tab.id ? 'border-jade-600 text-jade-600' : 'border-transparent text-slate-600 hover:text-slate-900',
          )}
        >
          {tab.label}
          {tab.locked && <Lock className="w-3 h-3" />}
        </button>
      ))}
    </div>
  )
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-16 text-slate-400" aria-busy="true">
      <Loader2 className="w-5 h-5 animate-spin" />
      {label && <span className="text-sm">{label}</span>}
    </div>
  )
}

export function EmptyState({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50/60 px-6 py-10 text-center">
      <p className="font-semibold text-slate-800">{title}</p>
      {children && <div className="mt-1 text-sm text-slate-600">{children}</div>}
    </div>
  )
}

export function ErrorNote({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : 'Something went wrong'
  return <p role="alert" className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{message}</p>
}

/** Shown in place of a feature the viewer's plan does not include. */
export function LockedFeature({ title, plan = 'Angel', children }: { title: string; plan?: string; children?: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-jade-200 bg-gradient-to-b from-jade-50 to-white px-6 py-10 text-center">
      <Lock className="mx-auto w-5 h-5 text-jade-600" />
      <p className="mt-3 font-bold text-slate-900">{title}</p>
      <p className="mt-1 text-sm text-slate-600">{children ?? `Available on the ${plan} plan and above.`}</p>
      <Link href="/wallet#plans" className="mt-4 inline-block rounded-lg bg-jade-600 px-4 py-2 text-sm font-bold text-white hover:brightness-110">
        Upgrade to {plan}
      </Link>
    </div>
  )
}

export function Button({ variant = 'primary', busy, children, className, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'danger'
  busy?: boolean
}) {
  return (
    <button
      {...props}
      disabled={busy || props.disabled}
      className={clsx(
        'inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-bold transition disabled:opacity-60 disabled:cursor-not-allowed',
        variant === 'primary' && 'bg-jade-600 text-white hover:brightness-110',
        variant === 'secondary' && 'border border-slate-300 bg-white text-slate-800 hover:bg-slate-50',
        variant === 'danger' && 'border border-rose-300 bg-white text-rose-700 hover:bg-rose-50',
        className,
      )}
    >
      {busy && <Loader2 className="w-4 h-4 animate-spin" />}
      {children}
    </button>
  )
}

export const FLAG_LABELS: Record<string, string> = {
  MCA_NOT_VERIFIED: 'Not verified with MCA',
  NAME_MISMATCH: 'Registered name differs',
  NO_DIRECTORS_FOUND: 'No directors on record',
  INVALID_CIN_FORMAT: 'Malformed CIN',
  SANDBOX_REGISTRY: 'Registry sandbox record',
  DECK_HIDDEN_INSTRUCTIONS: 'Hidden instructions in deck',
  OCR_REVIEW_REQUIRED: 'Low-confidence OCR',
  OCR_PARTIAL: 'Partly unreadable document',
}

export const flagLabel = (flag: string) =>
  FLAG_LABELS[flag] ?? flag.replace(/^COMPANY_STATUS_/, 'Company status: ').replace(/_/g, ' ').toLowerCase().replace(/^\w/, c => c.toUpperCase())

const SEVERE = new Set(['COMPANY_STATUS_STRUCK_OFF', 'COMPANY_STATUS_UNDER_LIQUIDATION', 'DECK_HIDDEN_INSTRUCTIONS', 'NAME_MISMATCH', 'INVALID_CIN_FORMAT'])

export function FlagBadges({ flags }: { flags: string[] }) {
  if (!flags.length) return null
  return (
    <span className="inline-flex flex-wrap gap-1">
      {flags.map(flag => <Badge key={flag} tone={SEVERE.has(flag) ? 'red' : 'amber'}>{flagLabel(flag)}</Badge>)}
    </span>
  )
}

export const STAGE_LABELS: Record<string, string> = { pre_seed: 'Pre-seed', seed: 'Seed', series_a: 'Series A', series_b: 'Series B' }
