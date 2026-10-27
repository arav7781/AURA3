'use client'

import { useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Coins, LogOut, Menu, X } from 'lucide-react'
import { clsx } from 'clsx'
import { useAuth } from '@/context/AuthContext'
import { formatAC } from '@/lib/format'

/** The AURA3 mark: an aura of three arcs (the 3) around a solid core. */
export function BrandMark({ className, core }: { className?: string; core?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" className={className}>
      <g stroke="currentColor" strokeWidth="2.4" strokeLinecap="round">
        <path d="M13.56 3.14A9 9 0 0 1 20.46 15.08" />
        <path d="M18.89 17.79A9 9 0 0 1 5.11 17.79" />
        <path d="M3.54 15.08A9 9 0 0 1 10.44 3.14" />
      </g>
      <circle cx="12" cy="12" r="3.1" fill={core ?? 'currentColor'} />
    </svg>
  )
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={clsx('font-display text-[1.32rem] font-semibold leading-none tracking-[-0.02em]', className)}>
      Aura<span className="ml-[1px] align-[0.32em] font-mono text-[0.62em] font-semibold text-jade-500">3</span>
    </span>
  )
}

export function Navbar() {
  const { me, userRole, loading, logout } = useAuth()
  const pathname = usePathname()
  const dark = pathname === '/'
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
    <nav className={clsx('z-50 border-b', dark
      ? 'absolute inset-x-0 top-0 border-white/10 text-mist'
      : 'sticky top-0 border-line bg-paper-2/85 text-ink backdrop-blur-xl')}>
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6">
        <div className="flex min-w-0 items-center gap-8">
          <Link href="/" className="flex shrink-0 items-center gap-2.5" aria-label="AURA3 home">
            <BrandMark className={clsx('h-7 w-7', dark ? 'text-mist' : 'text-jade-600')} core={dark ? 'var(--color-jade-400)' : undefined} />
            <Wordmark />
          </Link>
          <div className="hidden items-center gap-1 md:flex">
            {links.map(link => {
              const active = pathname === link.href || pathname.startsWith(`${link.href}/`)
              return (
                <Link key={link.href} href={link.href}
                      className={clsx('relative px-3 py-2 text-[0.93rem] font-medium transition-colors', dark
                        ? 'text-mist-2 hover:text-white'
                        : active ? 'text-ink' : 'text-ink-3 hover:text-ink')}>
                  {link.label}
                  {active && !dark && <span className="absolute inset-x-3 -bottom-[13px] h-[2px] rounded-full bg-jade-600" />}
                </Link>
              )
            })}
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          {me ? (
            <>
              {me.user.role === 'investor' && (
                <Link href="/wallet" title="Available AuraCoin"
                      className={clsx('hidden items-center gap-1.5 rounded-lg px-2.5 py-1.5 md:flex',
                        dark ? 'bg-white/[0.07] text-mist' : 'border border-marigold-100 bg-marigold-50 text-ink')}>
                  <Coins className={clsx('h-3.5 w-3.5', dark ? 'text-marigold-300' : 'text-marigold-500')} />
                  <span className="font-mono text-[0.75rem] font-medium">{formatAC(me.balances.available, { compact: true })}</span>
                </Link>
              )}
              <div className={clsx('flex items-center gap-2 rounded-lg py-1.5 pl-3 pr-1.5',
                dark ? 'bg-white/[0.07]' : 'border border-line bg-white')}>
                <span className="hidden max-w-[10rem] truncate text-[0.87rem] font-medium sm:block">{me.user.name}</span>
                <span className={clsx('font-mono text-[0.68rem] font-medium uppercase', dark ? 'text-jade-300' : 'text-jade-600')}>
                  {me.user.role === 'investor' ? me.plan?.name ?? 'Investor' : 'Founder'}
                </span>
                <button onClick={() => logout('/')} title="Sign out" aria-label="Sign out"
                        className={clsx('rounded-md p-1 transition-colors', dark ? 'text-mist-3 hover:text-white' : 'text-ink-3 hover:text-rose-600')}>
                  <LogOut className="h-3.5 w-3.5" />
                </button>
              </div>
            </>
          ) : !loading && (
            <>
              <Link href="/login" className={clsx('hidden px-3 py-2 text-[0.93rem] font-medium sm:block', dark ? 'text-mist-2 hover:text-white' : 'text-ink-2 hover:text-ink')}>
                Sign in
              </Link>
              <Link href="/register" className={clsx('rounded-lg px-4 py-2 text-[0.93rem] font-semibold transition-colors',
                dark ? 'bg-jade-400 text-night hover:bg-jade-300' : 'bg-jade-600 text-white hover:bg-jade-700')}>
                Get started
              </Link>
            </>
          )}
          <button type="button" onClick={() => setOpen(menuOpen ? null : pathname)} aria-label={menuOpen ? 'Close menu' : 'Open menu'} aria-expanded={menuOpen}
                  className={clsx('rounded-lg p-2 md:hidden', dark ? 'text-mist hover:bg-white/10' : 'text-ink-2 hover:bg-black/5')}>
            {menuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </div>
      {menuOpen && (
        <div className={clsx('grid gap-1 border-t p-3 md:hidden', dark ? 'border-white/10 bg-night/95 backdrop-blur-md' : 'border-line bg-paper-2')}>
          {[...links, ...(!me ? [{ href: '/login', label: 'Sign in' }] : [])].map(link => (
            <Link key={link.href} href={link.href}
                  className={clsx('rounded-lg px-4 py-3 text-base font-medium', dark ? 'text-mist hover:bg-white/10' : 'text-ink hover:bg-black/5')}>
              {link.label}
            </Link>
          ))}
        </div>
      )}
    </nav>
  )
}
