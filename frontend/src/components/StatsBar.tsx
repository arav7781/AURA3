'use client'

import { useReadContract } from 'wagmi'
import { VENTUREDAO_ADDRESS, VENTUREDAO_ABI } from '@/constants/abis'
import { formatEther } from 'viem'
import { Activity, Coins, Layers } from 'lucide-react'

export function StatsBar() {
  const { data: treasuryBalance } = useReadContract({
    address: VENTUREDAO_ADDRESS,
    abi: VENTUREDAO_ABI,
    functionName: 'getTreasuryBalance',
  })

  const { data: proposalCount } = useReadContract({
    address: VENTUREDAO_ADDRESS,
    abi: VENTUREDAO_ABI,
    functionName: 'proposalCount',
  })

  return (
    <div className="w-full max-w-5xl mx-auto grid grid-cols-1 md:grid-cols-3 gap-6 mb-12">
      <div className="bg-white border border-slate-200 shadow-sm rounded-2xl p-6 flex items-center gap-4">
        <div className="bg-emerald-50 p-3 rounded-xl border border-emerald-100">
          <Coins className="w-6 h-6 text-emerald-600" />
        </div>
        <div>
          <p className="text-sm text-slate-500 font-medium">Total Treasury</p>
          <h4 className="text-2xl font-bold font-mono text-slate-900">
            {treasuryBalance !== undefined ? Number(formatEther(treasuryBalance)).toFixed(3) : '0.000'} ETH
          </h4>
        </div>
      </div>

      <div className="bg-white border border-slate-200 shadow-sm rounded-2xl p-6 flex items-center gap-4">
        <div className="bg-sky-50 p-3 rounded-xl border border-sky-100">
          <Layers className="w-6 h-6 text-sky-600" />
        </div>
        <div>
          <p className="text-sm text-slate-500 font-medium">Total Proposals</p>
          <h4 className="text-2xl font-bold font-mono text-slate-900">
            {proposalCount !== undefined ? Number(proposalCount).toString() : '0'}
          </h4>
        </div>
      </div>

      <div className="bg-white border border-slate-200 shadow-sm rounded-2xl p-6 flex items-center gap-4">
        <div className="bg-purple-50 p-3 rounded-xl border border-purple-100">
          <Activity className="w-6 h-6 text-purple-600" />
        </div>
        <div>
          <p className="text-sm text-slate-500 font-medium">Active Proposals</p>
          <h4 className="text-2xl font-bold font-mono text-slate-900">
            {proposalCount !== undefined ? Number(proposalCount).toString() : '0'}
          </h4>
        </div>
      </div>
    </div>
  )
}
