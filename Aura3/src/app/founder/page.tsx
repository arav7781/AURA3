'use client'

import { useCallback, useEffect } from 'react'
import { useAccount } from 'wagmi'
import { motion } from 'framer-motion'
import { useRouter } from 'next/navigation'
import { History, Sparkles } from 'lucide-react'
import { CreateProposalForm } from '@/components/CreateProposalForm'
import { ProposalList } from '@/components/ProposalList'
import { EvaluationsList } from '@/components/EvaluationsList'
import { useAuth } from '@/context/AuthContext'

export default function FounderDashboard() {
  const { isConnected, address } = useAccount()
  const { userRole, loading, enterAs } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (!loading && userRole !== 'startup') enterAs('startup')
  }, [loading, userRole, enterAs])

  const onProposalCreated = useCallback(() => router.refresh(), [router])

  return (
    <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }} className="max-w-7xl mx-auto px-6 py-10">
      <div className="mb-8 flex flex-col md:flex-row justify-between md:items-end gap-4 border-b border-slate-200 pb-6">
        <div>
          <p className="text-[11px] font-mono uppercase tracking-widest text-[#0284c7] mb-2">Founder portal</p>
          <h1 className="text-3xl font-black text-slate-900 tracking-tight">Raise from the AURA-3 DAO</h1>
          <p className="text-slate-600 mt-1">Upload your deck, get an AI due-diligence report in about a minute, then publish it for token holders to vote on.</p>
        </div>
        {address && (
          <div className="text-right">
            <p className="text-[10px] font-mono text-slate-500 uppercase">Founder wallet</p>
            <p className="text-xs font-mono text-slate-800">{address.slice(0, 8)}…{address.slice(-6)}</p>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
        <div className="xl:col-span-7">
          <CreateProposalForm onSuccess={onProposalCreated} />
        </div>
        <div className="xl:col-span-5 space-y-6">
          <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
            <div className="px-5 py-4 border-b border-slate-200 bg-slate-50">
              <h2 className="text-[11px] font-bold font-mono text-slate-900 uppercase tracking-widest flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-[#0284c7]" /> {address ? 'Your AI evaluations' : 'Recent AI evaluations'}
              </h2>
            </div>
            <EvaluationsList founderAddress={address} />
          </div>
          <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
            <div className="px-5 py-4 border-b border-slate-200 bg-slate-50">
              <h2 className="text-[11px] font-bold font-mono text-slate-900 uppercase tracking-widest flex items-center gap-2">
                <History className="w-4 h-4 text-[#0284c7]" /> Your on-chain proposals
              </h2>
            </div>
            {isConnected ? (
              <div className="max-h-[500px] overflow-y-auto">
                <ProposalList filterFounder={address} source="founder" />
              </div>
            ) : (
              <p className="p-6 text-sm text-slate-500">Connect MetaMask (Sepolia) to see proposals you have published.</p>
            )}
          </div>
        </div>
      </div>
    </motion.div>
  )
}
