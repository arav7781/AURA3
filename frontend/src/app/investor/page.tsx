'use client'

import { useEffect } from 'react'
import Link from 'next/link'
import { useAccount } from 'wagmi'
import { Brain, Landmark, Sparkles } from 'lucide-react'
import { InvestorActions } from '@/components/InvestorActions'
import { ProposalList } from '@/components/ProposalList'
import { EvaluationsList } from '@/components/EvaluationsList'
import { useProposals } from '@/hooks/useProposals'
import { useAuth } from '@/context/AuthContext'

export default function InvestorDashboard() {
  const { isConnected } = useAccount()
  const { proposals } = useProposals()
  const { userRole, loading, enterAs } = useAuth()

  useEffect(() => {
    if (!loading && userRole !== 'investor') enterAs('investor')
  }, [loading, userRole, enterAs])

  return (
    <div className="max-w-7xl mx-auto px-6 py-10">
      <div className="mb-8 flex flex-col md:flex-row justify-between md:items-end gap-4 border-b border-slate-200 pb-6">
        <div>
          <p className="text-[11px] font-mono uppercase tracking-widest text-[#0284c7] mb-2">Investor dashboard</p>
          <h1 className="text-3xl font-black text-slate-900 tracking-tight">Discover, question and back startups</h1>
          <p className="text-slate-600 mt-1">Read AI due-diligence reports, chat with the Venture Analyst, then vote with your governance tokens.</p>
        </div>
        <Link href="/finscope" className="inline-flex items-center gap-2 bg-[#7c3aed] text-white text-sm font-bold rounded-lg px-4 py-2.5 hover:brightness-110">
          <Brain className="w-4 h-4" /> Ask FinScope AI
        </Link>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-7 space-y-6">
          <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
            <div className="px-5 py-4 border-b border-slate-200 bg-slate-50">
              <h2 className="text-[11px] font-bold font-mono text-slate-900 uppercase tracking-widest flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-[#0284c7]" /> AI-evaluated startups
              </h2>
            </div>
            <EvaluationsList />
          </div>
          <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
            <div className="px-5 py-4 border-b border-slate-200 bg-slate-50 flex justify-between items-center">
              <h2 className="text-[11px] font-bold font-mono text-slate-900 uppercase tracking-widest flex items-center gap-2">
                <Landmark className="w-4 h-4 text-[#0284c7]" /> On-chain governance proposals
              </h2>
              <span className="text-[10px] font-mono text-slate-500 uppercase">{proposals.length} on Sepolia</span>
            </div>
            <div className="max-h-[600px] overflow-y-auto">
              <ProposalList />
            </div>
          </div>
        </div>
        <div className="lg:col-span-5">
          {isConnected ? (
            <InvestorActions />
          ) : (
            <div className="bg-white border border-dashed border-slate-300 rounded-xl p-8 text-center">
              <p className="text-sm font-bold text-slate-900 mb-1">Treasury & voting power</p>
              <p className="text-sm text-slate-500">Connect MetaMask on Sepolia (top right) to buy governance tokens and vote.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
