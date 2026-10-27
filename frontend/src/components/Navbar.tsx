'use client'

import Link from 'next/link'
import { Coins, Diamond, LogOut } from 'lucide-react'
import { motion } from 'framer-motion'
import { useAuth } from '@/context/AuthContext'
import { useRouter } from 'next/navigation'
import { formatAC } from '@/lib/format'

const linkClass =
  'flex items-center px-5 h-full border-r border-slate-200 text-[10px] font-bold font-mono text-slate-600 uppercase tracking-wider transition-colors'

export function Navbar() {
  const { me, userRole, loading, logout } = useAuth()
  const router = useRouter()

  const handleLogout = async () => {
    await logout()
    router.push('/')
  }

  return (
    <motion.nav
      initial={{ y: -50, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.5, ease: 'easeOut' }}
      className="border-b border-slate-200 bg-white/80 backdrop-blur-xl sticky top-0 z-50 h-14 shadow-sm"
    >
      <div className="max-w-full mx-auto h-full">
        <div className="flex justify-between items-center h-full">
          <div className="flex items-center h-full overflow-x-auto">
            <Link href="/" className="flex items-center gap-2 px-6 border-r border-slate-200 h-full hover:bg-slate-50 transition-colors group">
              <Diamond className="w-4 h-4 text-[#0284c7] group-hover:drop-shadow-[0_0_8px_rgba(2,132,199,0.5)] transition-all" />
              <span className="text-xs font-bold font-mono tracking-tighter text-slate-900 uppercase">AURA3</span>
            </Link>
            <div className="flex items-center h-full">
              {userRole === 'investor' && (
                <Link href="/investor" className={`${linkClass} hover:text-[#0284c7]`}>Deal flow</Link>
              )}
              {userRole === 'startup' && (
                <Link href="/founder" className={`${linkClass} hover:text-[#0284c7]`}>Founder portal</Link>
              )}
              {me && <Link href="/rankings" className={`${linkClass} hover:text-[#0284c7]`}>Rankings</Link>}
              {me && <Link href="/wallet" className={`${linkClass} hover:text-[#059669]`}>Wallet</Link>}
              <Link href="/pricing" className={`${linkClass} hover:text-[#0284c7]`}>Pricing</Link>
            </div>
          </div>

          <div className="flex items-center gap-3 px-6 shrink-0">
            {me ? (
              <>
                {me.user.role === 'investor' && (
                  <Link href="/investor" className="hidden md:flex items-center gap-1.5 px-2 py-1 rounded bg-amber-50 border border-amber-200" title="Available AuraCoin">
                    <Coins className="w-3.5 h-3.5 text-amber-600" />
                    <span className="text-[11px] font-mono font-bold text-slate-800">{formatAC(me.balances.available, { compact: true })}</span>
                  </Link>
                )}
                <div className="flex items-center gap-2 px-2 py-1.5 bg-slate-50 rounded border border-slate-200">
                  <span className="hidden sm:block max-w-[10rem] truncate text-[11px] font-semibold text-slate-800">{me.user.name}</span>
                  <span className="text-[10px] font-mono font-bold uppercase text-[#0284c7]">
                    {me.user.role === 'investor' ? me.plan?.name ?? 'Investor' : 'Founder'}
                  </span>
                  <button onClick={handleLogout} className="text-slate-500 hover:text-red-500 transition-colors cursor-pointer" title="Sign out" aria-label="Sign out">
                    <LogOut className="w-3.5 h-3.5" />
                  </button>
                </div>
              </>
            ) : !loading && (
              <>
                <Link href="/login" className="text-[11px] font-mono font-bold uppercase tracking-wider text-slate-700 hover:text-[#0284c7]">Sign in</Link>
                <Link href="/register" className="text-[11px] font-mono font-bold uppercase tracking-wider text-white bg-[#0284c7] rounded px-3 py-1.5 hover:brightness-110">Get started</Link>
              </>
            )}
          </div>
        </div>
      </div>
    </motion.nav>
  )
}
