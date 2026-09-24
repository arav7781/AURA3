'use client'

import Link from 'next/link'
import { ConnectButton } from './ConnectButton'
import { Diamond, LogOut, Repeat } from 'lucide-react'
import { motion } from 'framer-motion'
import { useAuth, getDashboardPath } from '@/context/AuthContext'
import { useRouter } from 'next/navigation'

const linkClass =
  'flex items-center px-5 h-full border-r border-slate-200 text-[10px] font-bold font-mono text-slate-600 uppercase tracking-wider transition-colors'

export function Navbar() {
  const { userRole, enterAs, logout } = useAuth()
  const router = useRouter()

  const handleLogout = async () => {
    await logout()
    router.push('/')
  }

  const switchRole = () => {
    const next = userRole === 'investor' ? 'startup' : 'investor'
    enterAs(next)
    router.push(getDashboardPath(next))
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
                <Link href="/investor" className={`${linkClass} hover:text-[#0284c7]`}>Investor Dash</Link>
              )}
              {userRole === 'startup' && (
                <Link href="/founder" className={`${linkClass} hover:text-[#0284c7]`}>Founder Portal</Link>
              )}
              <Link href="/evaluations" className={`${linkClass} hover:text-[#0284c7]`}>AI Evaluations</Link>
              <Link href="/finscope" className={`${linkClass} hover:text-[#7c3aed]`}>FinScope AI</Link>
              <Link href="/portfolio" className={`${linkClass} hover:text-[#059669]`}>Portfolio</Link>
              <Link href="/exit-window" className={`${linkClass} hover:text-[#059669]`}>Exit Window</Link>
            </div>
          </div>

          <div className="flex items-center gap-3 px-6 shrink-0">
            <div className="hidden xl:flex items-center gap-1.5 px-2 py-1 rounded bg-slate-50 border border-slate-200">
              <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              <span className="text-[9px] font-mono text-slate-700 font-bold uppercase">Sepolia Live</span>
            </div>

            {userRole && (
              <div className="flex items-center gap-2 px-2 py-1.5 bg-slate-50 rounded border border-slate-200">
                <span className="text-[10px] font-mono font-bold uppercase text-slate-700">
                  {userRole === 'investor' ? 'Investor' : 'Founder'} (demo)
                </span>
                <button onClick={switchRole} className="text-slate-500 hover:text-[#0284c7] transition-colors cursor-pointer" title={`Switch to ${userRole === 'investor' ? 'founder' : 'investor'} view`}>
                  <Repeat className="w-3.5 h-3.5" />
                </button>
                <button onClick={handleLogout} className="text-red-500 hover:text-red-400 transition-colors cursor-pointer" title="Exit demo session">
                  <LogOut className="w-3.5 h-3.5" />
                </button>
              </div>
            )}

            <ConnectButton />
          </div>
        </div>
      </div>
    </motion.nav>
  )
}
