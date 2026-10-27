'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useState } from 'react'
import { Coins, LogOut, Menu, X } from 'lucide-react'
import { clsx } from 'clsx'
import { useAuth } from '@/context/AuthContext'
import { formatAC } from '@/lib/format'

/** The AURA3 mark: the corner brackets TitanOCR draws around a page it has found. */
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" className={className}>
      <path d="M3 8V3h5M16 3h5v5M21 16v5h-5M8 21H3v-5" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
      <rect x="8.5" y="8.5" width="7" height="7" rx="1.2" fill="currentColor" />
    </svg>
  )
}

export function Navbar() {
  const { me, userRole, loading, logout } = useAuth()
  const pathname = usePathname()
  const overHero = pathname === '/'
  const [open, setOpen] = useState<string | null>(null)
  const menuOpen = open === pathname // closes itself on navigation

  const links = [
    userRole === 'investor' && { href: '/investor', label: 'Deal flow' },
    userRole === 'startup' && { href: '/founder', label: 'Founder portal' },
    me && { href: '/copilot', label: 'Copilot' },
    me && { href: '/rankings', label: 'Rankings' },
    me && { href: '/wallet', label: 'Wallet' },
    { href: '/pricing', label: 'Pricing' },
  ].filter(Boolean) as { href: string; label: string }[]

  return (
    <nav className={clsx('z-50', overHero ? 'absolute inset-x-0 top-3 px-3' : 'sticky top-0 border-b border-slate-200 bg-white/85 backdrop-blur-xl')}>
      <div className={clsx(
        'mx-auto flex h-14 items-center justify-between gap-4',
        overHero
          ? 'max-w-7xl rounded-full border border-white/10 bg-[rgb(20_12_6/0.55)] px-3 pl-5 shadow-[0_12px_30px_-12px_rgb(0_0_0/0.6)] backdrop-blur-md sm:h-[60px]'
          : 'max-w-7xl px-4 sm:px-6',
      )}>
        <div className="flex min-w-0 items-center gap-6">
          <Link href="/" className={clsx('flex shrink-0 items-center gap-2.5', overHero ? 'text-hero-ink' : 'text-ink')}>
            <BrandMark className="h-5 w-5" />
            <span className="font-display text-[1.05rem] font-extrabold tracking-tight">AURA3</span>
          </Link>
          <div className="hidden min-w-0 items-center gap-1 overflow-x-auto md:flex">
            {links.map(link => (
              <Link key={link.href} href={link.href}
                    className={clsx('shrink-0 rounded-full px-3 py-1.5 text-[0.92rem] font-medium transition-colors',
                      overHero ? 'text-hero-ink-2 hover:text-hero-ink' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900')}>
                {link.label}
              </Link>
            ))}
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <button type="button" onClick={() => setOpen(menuOpen ? null : pathname)} aria-label={menuOpen ? 'Close menu' : 'Open menu'} aria-expanded={menuOpen}
                  className={clsx('rounded-full p-2 md:hidden', overHero ? 'text-hero-ink hover:bg-white/10' : 'text-slate-700 hover:bg-slate-100')}>
            {menuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
          {me ? (
            <>
              {me.user.role === 'investor' && (
                <Link href="/wallet" title="Available AuraCoin"
                      className={clsx('hidden items-center gap-1.5 rounded-full px-3 py-1.5 md:flex',
                        overHero ? 'bg-white/10 text-hero-ink' : 'border border-amber-200 bg-amber-50 text-slate-800')}>
                  <Coins className={clsx('h-3.5 w-3.5', overHero ? 'text-amber-300' : 'text-amber-600')} />
                  <span className="font-mono text-[11px] font-semibold">{formatAC(me.balances.available, { compact: true })}</span>
                </Link>
              )}
              <div className={clsx('flex items-center gap-2 rounded-full py-1.5 pl-3 pr-2',
                overHero ? 'bg-white/10 text-hero-ink' : 'border border-slate-200 bg-slate-50')}>
                <span className="hidden max-w-[10rem] truncate text-[0.85rem] font-semibold sm:block">{me.user.name}</span>
                <span className={clsx('font-mono text-[10px] font-semibold uppercase', overHero ? 'text-hero-accent' : 'text-cobalt')}>
                  {me.user.role === 'investor' ? me.plan?.name ?? 'Investor' : 'Founder'}
                </span>
                <button onClick={() => logout('/')} title="Sign out" aria-label="Sign out"
                        className={clsx('rounded-full p-1 transition-colors', overHero ? 'text-hero-ink-3 hover:text-hero-ink' : 'text-slate-500 hover:text-rose-600')}>
                  <LogOut className="h-3.5 w-3.5" />
                </button>
              </div>
            </>
          ) : !loading && (
            <>
              <Link href="/login" className={clsx('rounded-full px-3 py-2 text-[0.92rem] font-medium', overHero ? 'text-hero-ink-2 hover:text-hero-ink' : 'text-slate-700 hover:text-slate-950')}>
                Sign in
              </Link>
              <Link href="/register" className="rounded-full bg-cobalt-bright px-4 py-2 text-[0.92rem] font-semibold text-white transition-colors hover:bg-[#4560ff]">
                Get started
              </Link>
            </>
          )}
        </div>
      </div>
      {menuOpen && (
        <div className={clsx('mx-auto mt-2 grid gap-1 p-2 md:hidden', overHero
          ? 'max-w-7xl rounded-2xl border border-white/10 bg-[rgb(20_12_6/0.85)] backdrop-blur-md'
          : 'border-t border-slate-200 bg-white')}>
          {links.map(link => (
            <Link key={link.href} href={link.href}
                  className={clsx('rounded-xl px-4 py-3 text-base font-medium', overHero ? 'text-hero-ink hover:bg-white/10' : 'text-slate-800 hover:bg-slate-100')}>
              {link.label}
            </Link>
          ))}
        </div>
      )}
    </nav>
  )
}
