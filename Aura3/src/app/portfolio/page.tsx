'use client'

import { useAccount } from 'wagmi'
import { useProposals } from '@/hooks/useProposals'
import { useInvestments } from '@/hooks/useInvestments'
import { InvestorStartupActions } from '@/components/InvestorStartupActions'
import { Briefcase } from 'lucide-react'
import { StartupAvatar } from '@/components/StartupAvatar'

export default function PortfolioPage() {
  const { isConnected, address } = useAccount()
  const { proposals } = useProposals()

  // Investor Data (Only startups the user actually had voting power / invested in)
  const globalExecuted = proposals.filter(p => p.executed)
  const { investedProposals } = useInvestments(address, globalExecuted)

  return (
    <div className="max-w-6xl mx-auto px-6 py-10">
      <div className="mb-12 border-b border-[#111] pb-8 flex justify-between items-end">
        <div>
          <h1 className="text-xl font-bold text-white uppercase tracking-widest mb-2 font-mono">Operations: Investment Portfolio</h1>
          <p className="text-[10px] font-bold font-mono text-sky-300 uppercase tracking-[0.2em]">Manage your active equity positions and token settlements.</p>
        </div>
        <div className="hidden lg:block text-right">
          <p className="text-[9px] font-bold text-sky-300 uppercase mb-1">Session ID</p>
          <p className="text-[10px] font-mono text-white">{address?.slice(0, 16).toUpperCase()}...</p>
        </div>
      </div>

      {!isConnected ? (
        <div className="border border-[#111] border-dashed p-20 text-center bg-white/[0.01]">
          <h2 className="text-[10px] font-bold font-mono text-sky-400 uppercase tracking-[0.3em] mb-4">Signal Lost: Wallet Disconnected</h2>
          <p className="text-[9px] font-bold font-mono text-[#222] uppercase tracking-widest">Connect MetaMask to synchronize your portfolios</p>
        </div>
      ) : (
        <div className="space-y-16">

          {/* Global Investment Portfolio (Investor) */}
          {investedProposals.length > 0 && (
            <div className="border border-[#111] relative bg-black">
              <div className="absolute top-0 left-1/2 -translate-x-1/2 -translate-y-1/2 px-4 bg-black border border-[#111]">
                <span className="text-[9px] font-mono font-bold text-sky-200 tracking-[0.3em] uppercase">Executive Assets</span>
              </div>

              <div className="p-6 border-b border-[#111] bg-[#050505] flex items-center justify-between">
                <div>
                  <h3 className="text-[10px] font-bold font-mono text-white uppercase tracking-widest flex items-center gap-2 mb-1">
                    <Briefcase className="w-3.5 h-3.5 text-[#03e1ff]" /> Investment Portfolio
                  </h3>
                   <p className="text-[9px] font-bold font-mono text-sky-300 uppercase tracking-widest">Active equity positions and settlement controls.</p>
                </div>
                <div className="px-3 py-1 border border-[#111] bg-black">
                   <span className="text-[9px] font-bold font-mono text-[#00ffbd] uppercase">{investedProposals.length} Holdings</span>
                </div>
              </div>
              
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
                {investedProposals.map(startup => (
                  <div key={startup.id} className="border-r border-b border-[#111] flex flex-col bg-black group transition-all hover:bg-white/[0.01]">
                    <div className="p-5 border-b border-[#111] flex justify-between items-start">
                      <div>
                        <h3 className="text-xs font-bold text-white mb-1 truncate uppercase tracking-tighter group-hover:text-[#00ffbd] transition-colors">{startup.description}</h3>
                        <p className="text-[9px] font-mono text-sky-300">ID-{startup.id}</p>
                      </div>
                      <StartupAvatar seed={startup.id} size={28} />
                    </div>
                    <div className="flex-1">
                      {startup.startupContract && (
                        <InvestorStartupActions 
                          address={startup.startupContract as `0x${string}`} 
                          initialValuation={startup.valuation}
                        />
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {investedProposals.length === 0 && (
             <div className="border border-[#111] bg-[#050505] text-sky-300 text-[10px] font-bold font-mono p-12 text-center uppercase tracking-widest">
                No active asset streams found
             </div>
          )}
        </div>
      )}
    </div>
  )
}
