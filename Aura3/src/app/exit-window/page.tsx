'use client'

import { useAccount } from 'wagmi'
import { useProposals } from '@/hooks/useProposals'
import { FounderStartupActions } from '@/components/FounderStartupActions'
import { LayoutDashboard } from 'lucide-react'
import { StartupAvatar } from '@/components/StartupAvatar'

export default function ExitWindowPage() {
  const { isConnected, address } = useAccount()
  const { proposals } = useProposals()

  // Founder Data
  const myProposals = proposals.filter(p => address && p.founder.toLowerCase() === address.toLowerCase())
  const managedVentures = myProposals.filter(p => p.executed)

  return (
    <div className="max-w-6xl mx-auto px-6 py-10">
      <div className="mb-12 border-b border-[#111] pb-8 flex justify-between items-end">
        <div>
          <h1 className="text-xl font-bold text-white uppercase tracking-widest mb-2 font-mono">Operations: Exit Window</h1>
          <p className="text-[10px] font-bold font-mono text-sky-300 uppercase tracking-[0.2em]">Manage your active startup capital and initialize investor exits.</p>
        </div>
        <div className="hidden lg:block text-right">
          <p className="text-[9px] font-bold text-sky-300 uppercase mb-1">Session ID</p>
          <p className="text-[10px] font-mono text-white">{address?.slice(0, 16).toUpperCase()}...</p>
        </div>
      </div>

      {!isConnected ? (
        <div className="border border-[#111] border-dashed p-20 text-center bg-white/[0.01]">
          <h2 className="text-[10px] font-bold font-mono text-sky-400 uppercase tracking-[0.3em] mb-4">Signal Lost: Wallet Disconnected</h2>
          <p className="text-[9px] font-bold font-mono text-[#222] uppercase tracking-widest">Connect MetaMask to synchronize your managed ventures.</p>
        </div>
      ) : (
        <div className="space-y-16">

          {/* Managed Startups Section (Founder) */}
          {managedVentures.length > 0 && (
            <div className="border border-[#111] relative bg-black">
              <div className="absolute top-0 left-1/2 -translate-x-1/2 -translate-y-1/2 px-4 bg-black border border-[#111]">
                <span className="text-[9px] font-mono font-bold text-sky-200 tracking-[0.3em] uppercase">Executive Assets</span>
              </div>

              <div className="p-6 border-b border-[#111] bg-[#050505] flex items-center justify-between">
                <div>
                  <h3 className="text-[10px] font-bold font-mono text-white uppercase tracking-widest flex items-center gap-2 mb-1">
                    <LayoutDashboard className="w-3.5 h-3.5 text-[#00ffbd]" /> Managed Ventures
                  </h3>
                  <p className="text-[9px] font-bold font-mono text-sky-300 uppercase tracking-widest">Operational fund management and exit streams.</p>
                </div>
                <div className="px-3 py-1 border border-[#111] bg-black">
                   <span className="text-[9px] font-bold font-mono text-[#00ffbd] uppercase">{managedVentures.length} Deployed</span>
                </div>
              </div>
              
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
                {managedVentures.map(startup => (
                  <div key={startup.id} className="border-r border-b border-[#111] flex flex-col bg-black group transition-all hover:bg-white/[0.01]">
                    <div className="p-5 border-b border-[#111] flex justify-between items-start">
                      <div>
                        <h3 className="text-xs font-bold text-white mb-1 truncate uppercase tracking-tighter group-hover:text-[#00ffbd] transition-colors">{startup.description}</h3>
                        <p className="text-[9px] font-mono text-sky-300">PROP_ID: #{startup.id}</p>
                      </div>
                      <StartupAvatar seed={startup.id} size={28} />
                    </div>
                    <div className="flex-1">
                      {startup.startupContract && (
                        <FounderStartupActions 
                          address={startup.startupContract as `0x${string}`} 
                          valuation={startup.valuation}
                        />
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {managedVentures.length === 0 && (
             <div className="border border-[#111] bg-[#050505] text-sky-300 text-[10px] font-bold font-mono p-12 text-center uppercase tracking-widest">
                No active asset streams found
             </div>
          )}
        </div>
      )}
    </div>
  )
}
