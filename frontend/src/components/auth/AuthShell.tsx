import Link from 'next/link'
import { BrandMark, Wordmark } from '@/components/Navbar'

export function AuthShell({ title, subtitle, children, footer }: {
  title: string
  subtitle: string
  children: React.ReactNode
  footer: React.ReactNode
}) {
  return (
    <div className="min-h-[calc(100vh-3.5rem)] flex items-start justify-center px-4 py-12 sm:py-16">
      <div className="w-full max-w-md">
        <Link href="/" className="mb-8 inline-flex items-center gap-2 text-ink">
          <BrandMark className="h-6 w-6 text-jade-600" />
          <Wordmark />
        </Link>
        <h1 className="font-display text-[2.15rem] font-semibold leading-tight tracking-[-0.02em] text-ink">{title}</h1>
        <p className="mt-2 text-slate-600">{subtitle}</p>
        <div className="mt-8 bg-white border border-slate-200 rounded-xl shadow-sm p-6">{children}</div>
        <div className="mt-6 text-sm text-slate-600">{footer}</div>
      </div>
    </div>
  )
}

export function Field({ label, hint, ...input }: React.InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string }) {
  return (
    <label className="block">
      <span className="block text-[11px] font-mono font-bold uppercase tracking-widest text-slate-600 mb-1.5">{label}</span>
      <input
        {...input}
        className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-[15px] text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-jade-600/30 focus:border-jade-600"
      />
      {hint && <span className="block mt-1 text-xs text-slate-500">{hint}</span>}
    </label>
  )
}

export function FormError({ message }: { message: string | null }) {
  if (!message) return null
  return (
    <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
      {message}
    </p>
  )
}

/** Only same-site paths are accepted as a post-login destination (no open redirects). */
export function safeNext(next: string | null): string | null {
  return next && next.startsWith('/') && !next.startsWith('//') && !next.startsWith('/\\') ? next : null
}
