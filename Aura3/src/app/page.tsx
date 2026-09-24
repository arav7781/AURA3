'use client'

import { useEffect, useState } from 'react'
import { NewsCards } from '@/components/NewsCards'
import { ScrollingFeatures } from '@/components/ScrollingFeatures'
import { useProposals } from '@/hooks/useProposals'
import { useBalance } from 'wagmi'
import { formatEther } from 'viem'
import { motion } from 'framer-motion'
import { VENTUREDAO_ADDRESS } from '@/constants/abis'
import { 
  Brain, Radar, Network, Gauge, Fuel, LineChart, 
  AlertTriangle, Lock, EyeOff, Timer, UploadCloud, Landmark, 
  Coins, Terminal, Cpu, Database, Wallet, Share2, Users 
} from 'lucide-react'
import { useRouter } from 'next/navigation'
import { useAuth, getDashboardPath } from '@/context/AuthContext'

export default function LandingPage() {
  const { proposals } = useProposals()
  const { data: balanceData } = useBalance({
    address: VENTUREDAO_ADDRESS,
  })
  
  const router = useRouter()
  const { enterAs } = useAuth()
  const terminalCommands = ['fetch_tvl --network ether', 'check_streams --active', 'cat /sys/status/nodes']
  const [activeCommandIndex, setActiveCommandIndex] = useState(0)
  const [typedCommand, setTypedCommand] = useState('')

  useEffect(() => {
    const target = terminalCommands[activeCommandIndex]
    if (typedCommand === target) {
      const rotateTimer = setTimeout(() => {
        setTypedCommand('')
        setActiveCommandIndex((prev) => (prev + 1) % terminalCommands.length)
      }, 850)
      return () => clearTimeout(rotateTimer)
    }

    const typeTimer = setTimeout(() => {
      setTypedCommand(target.slice(0, typedCommand.length + 1))
    }, 34)
    return () => clearTimeout(typeTimer)
  }, [typedCommand, activeCommandIndex])

  const enterRole = (role: 'investor' | 'startup', path = getDashboardPath(role)) => {
    enterAs(role)
    router.push(path)
  }

  // Calculate live metrics gracefully
  const activeStreams = proposals ? proposals.filter(p => !p.executed).length : 0
  const tvl = balanceData ? Number(formatEther(balanceData.value)).toFixed(4) : '0.0000'
  const heroBackdropImage = 'https://images.unsplash.com/photo-1639322537228-f710d846310a?auto=format&fit=crop&w=2200&q=80'
  const proposalJourneySteps = [
    {
      id: '01',
      title: 'The Spark',
      description: 'A founder submits a proposal with verifiable project data and initial technical milestones.',
      image: 'https://images.unsplash.com/photo-1520607162513-77705c0f0d4a?auto=format&fit=crop&w=1200&q=80',
    },
    {
      id: '02',
      title: 'AI Validation',
      description: 'FinScope AI analyzes the data for risk, ROI, and market fit, generating a trust score.',
      image: 'https://images.unsplash.com/photo-1620712943543-bcc4688e7485?auto=format&fit=crop&w=1200&q=80',
    },
    {
      id: '03',
      title: 'Consensus',
      description: 'DAO holders vote based on AI insights. Smart contracts ensure fair, weighted distribution.',
      image: 'https://images.unsplash.com/photo-1639322537228-f710d846310a?auto=format&fit=crop&w=1200&q=80',
    },
    {
      id: '04',
      title: 'Milestones',
      description: 'Treasury funds unlock automatically as the founder completes on-chain project goals.',
      image: 'https://images.unsplash.com/photo-1535320903710-d993d3d77d29?auto=format&fit=crop&w=1200&q=80',
    },
  ]

  return (
    <div className="flex flex-col min-h-screen bg-background text-on-background font-body selection:bg-primary-container selection:text-on-primary-container">
      
      {/* SideNavBar (System Status) */}
      <aside className="hidden lg:flex flex-col items-center py-8 gap-8 fixed left-0 top-0 h-full z-40 w-20 border-r border-[#03e1ff]/10 bg-white" style={{ paddingTop: '80px' }}>
        <div className="flex flex-col items-center gap-2 mb-10">
          <div className="w-10 h-10 rounded-full border border-secondary-fixed flex items-center justify-center bg-secondary-fixed/10">
            <Brain className="w-5 h-5 text-secondary-fixed" />
          </div>
          <span className="font-['JetBrains_Mono'] text-[8px] text-[#0b7285] font-black">SYS 3.0</span>
        </div>
        
        <div className="flex flex-col gap-10 items-center">
          <div className="group flex flex-col items-center gap-1 cursor-help transition-transform duration-200 hover:translate-x-1" title="Market Status">
            <Radar className="w-5 h-5 text-[#3cffc0]" />
            <span className="font-['JetBrains_Mono'] text-[8px] text-[#0b7285]/80 uppercase vertical-text mt-2 tracking-widest">Market</span>
          </div>
          <div className="group flex flex-col items-center gap-1 cursor-help transition-transform duration-200 hover:translate-x-1" title="Network Status">
            <Network className="w-5 h-5 text-[#0b7285]/80 group-hover:text-[#0284a1] transition-colors" />
            <span className="font-['JetBrains_Mono'] text-[8px] text-[#0b7285]/80 uppercase vertical-text mt-2 tracking-widest group-hover:text-[#0284a1] transition-colors">Network</span>
          </div>
          <div className="group flex flex-col items-center gap-1 cursor-help transition-transform duration-200 hover:translate-x-1" title="AI Latency">
            <Gauge className="w-5 h-5 text-[#0b7285]/80 group-hover:text-[#0284a1] transition-colors" />
            <span className="font-['JetBrains_Mono'] text-[8px] text-[#0b7285]/80 uppercase vertical-text mt-2 tracking-widest group-hover:text-[#0284a1] transition-colors">Latency</span>
          </div>
          <div className="group flex flex-col items-center gap-1 cursor-help transition-transform duration-200 hover:translate-x-1" title="Gas Price">
            <Fuel className="w-5 h-5 text-[#0b7285]/80 group-hover:text-[#0284a1] transition-colors" />
            <span className="font-['JetBrains_Mono'] text-[8px] text-[#0b7285]/80 uppercase vertical-text mt-2 tracking-widest group-hover:text-[#0284a1] transition-colors">Gas</span>
          </div>
        </div>
      </aside>

      <main className="lg:ml-20 flex-1 relative z-10 w-full overflow-hidden bg-white">
        {/* Hero Section */}
        <section className="relative px-6 overflow-hidden min-h-[calc(100svh-64px)] flex items-center py-20 mb-[-1px]">
          <div className="absolute inset-0 bg-gradient-to-b from-sky-50 via-white to-white" />

          <div className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-12 gap-10 lg:gap-14 items-center relative z-10">
            <div className="lg:col-span-7 z-10">
              <motion.div initial={{ opacity: 0, y: 28 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.75 }}>
                <div className="inline-flex items-center gap-2.5 px-4 py-2 bg-[#03e1ff]/[0.06] border border-[#03e1ff]/40 rounded-md mb-6 mt-4 backdrop-blur-md shadow-[0_0_18px_rgba(3,225,255,0.12)]">
                  <span className="w-2 h-2 rounded-full bg-secondary-fixed animate-pulse"></span>
                  <span className="font-['JetBrains_Mono'] text-[10px] text-[#0f8a66] uppercase tracking-[0.2em]">Protocol Active: V3.0.4-BETA</span>
                </div>

                <h1 className="font-body font-black text-6xl md:text-8xl tracking-tighter mb-7 glitch-text-new uppercase leading-[0.92]">
                  <span className="text-slate-900">AURA</span><span className="text-[#0284c7]">3</span>
                </h1>

                <p className="text-on-surface-variant text-xl max-w-2xl mb-8 leading-relaxed font-light">
                  A sovereign intelligence layer for decentralized capital. Secure your position in the next generation of autonomous liquidity.
                </p>

                <div className="flex flex-wrap gap-3 mb-10">
                  <div className="px-4 py-2 bg-[#03e1ff]/[0.05] border border-[#03e1ff]/30 rounded-full text-[10px] uppercase tracking-[0.18em] font-['JetBrains_Mono'] text-[#0b7f98]">Autonomous due diligence</div>
                  <div className="px-4 py-2 bg-[#03e1ff]/[0.05] border border-[#03e1ff]/30 rounded-full text-[10px] uppercase tracking-[0.18em] font-['JetBrains_Mono'] text-[#0b7f98]">Transparent execution</div>
                  <div className="px-4 py-2 bg-[#03e1ff]/[0.05] border border-[#03e1ff]/30 rounded-full text-[10px] uppercase tracking-[0.18em] font-['JetBrains_Mono'] text-[#0b7f98]">Investor-first liquidity</div>
                </div>

                <div className="flex flex-wrap gap-4 mb-8">
                  <button onClick={() => enterRole('investor')} className="bg-[#0284c7] text-white px-6 py-4 font-body font-bold uppercase tracking-widest hover:scale-105 transition-all shadow-[0_4px_20px_rgba(2,132,199,0.2)]">
                    Enter as Investor
                  </button>
                  <button onClick={() => enterRole('startup')} className="bg-white border border-slate-200 text-slate-800 px-6 py-4 font-body font-bold uppercase tracking-widest hover:bg-slate-50 transition-all">
                    Enter as Startup
                  </button>
                  <button onClick={() => enterRole('investor', '/finscope')} className="bg-slate-50 border border-slate-200 text-[#0284c7] px-6 py-4 font-body font-bold uppercase tracking-widest hover:bg-slate-100 transition-all">
                    FinScope AI Chat
                  </button>
                </div>
                <p className="text-sm text-slate-500 -mt-4">Demo mode — no sign-up needed. Pick a role to jump straight in.</p>
              </motion.div>
            </div>

            <div className="lg:col-span-5 relative mt-8 lg:mt-0">
              <motion.div initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.2, duration: 0.7 }} className="bg-black/90 border border-[#03e1ff]/30 p-1 rounded-sm shadow-[0_0_44px_rgba(3,225,255,0.16)] relative z-10 font-['JetBrains_Mono'] w-full max-w-md mx-auto backdrop-blur-xl">
                {/* Terminal Header */}
                <div className="bg-[#03e1ff]/10 border-b border-[#03e1ff]/30 px-3 py-2 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 bg-red-500 animate-pulse"></div>
                    <span className="text-[9px] text-[#03e1ff] uppercase tracking-[3px] font-bold">aurad@root: /var/metrics</span>
                  </div>
                  <div className="flex gap-1.5">
                    <span className="w-2 h-2 bg-white/20"></span>
                    <span className="w-2 h-2 bg-white/40"></span>
                    <span className="w-2 h-2 bg-white/60"></span>
                  </div>
                </div>
                {/* Terminal Body */}
                <div className="p-5 space-y-5">
                  <div className="flex flex-col gap-1">
                    <span className={`text-[10px] uppercase tracking-widest ${activeCommandIndex === 0 ? 'text-[#7defff] terminal-flicker' : 'text-gray-600'}`}>
                      {">"} {activeCommandIndex === 0 ? typedCommand : terminalCommands[0]}
                      {activeCommandIndex === 0 && <span className="inline-block w-1.5 h-3 ml-1 bg-[#03e1ff] align-middle animate-pulse" />}
                    </span>
                    <div className="flex items-end justify-between border-b border-white/5 pb-2">
                      <span className="text-xs text-on-surface-variant font-bold">TOTAL_VALUE_LOCKED</span>
                      <span className="text-sm text-[#03e1ff] font-bold shadow-sm">${tvl} ETH</span>
                    </div>
                  </div>

                  <div className="flex flex-col gap-1">
                    <span className={`text-[10px] uppercase tracking-widest ${activeCommandIndex === 1 ? 'text-[#7defff] terminal-flicker' : 'text-gray-600'}`}>
                      {">"} {activeCommandIndex === 1 ? typedCommand : terminalCommands[1]}
                      {activeCommandIndex === 1 && <span className="inline-block w-1.5 h-3 ml-1 bg-[#03e1ff] align-middle animate-pulse" />}
                    </span>
                    <div className="flex items-end justify-between border-b border-white/5 pb-2">
                      <span className="text-xs text-on-surface-variant font-bold">DATA_STREAMS</span>
                      <span className="text-sm text-tertiary font-bold">{activeStreams} PENDING</span>
                    </div>
                  </div>

                  <div className="flex flex-col gap-1">
                    <span className={`text-[10px] uppercase tracking-widest ${activeCommandIndex === 2 ? 'text-[#7defff] terminal-flicker' : 'text-gray-600'}`}>
                      {">"} {activeCommandIndex === 2 ? typedCommand : terminalCommands[2]}
                      {activeCommandIndex === 2 && <span className="inline-block w-1.5 h-3 ml-1 bg-[#03e1ff] align-middle animate-pulse" />}
                    </span>
                    <div className="flex items-end justify-between border-b border-white/5 pb-2">
                      <span className="text-xs text-on-surface-variant font-bold">AI_CONFIDENCE</span>
                      <span className="text-sm text-[#3cffc0] font-black">99.2%</span>
                    </div>
                    <div className="flex items-end justify-between border-b border-white/5 pb-2 mt-2">
                      <span className="text-xs text-on-surface-variant font-bold">NODES_ONLINE</span>
                      <span className="text-sm text-[#3cffc0] font-black">1,852</span>
                    </div>
                  </div>

                  <div className="pt-2 flex items-center gap-2">
                    <span className="text-[#03e1ff] text-xs">root@aura3:~#</span><span className="w-2 h-4 bg-[#03e1ff] animate-pulse"></span>
                  </div>
                </div>
              </motion.div>

              <motion.div
                initial={{ opacity: 0, y: 14 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.35, duration: 0.55 }}
                className="max-w-md mx-auto mt-4 grid grid-cols-3 gap-3"
              >
                <div className="glass-card p-4 rounded-xl shadow-sm border border-slate-200/50">
                  <p className="text-[9px] uppercase tracking-widest text-[#0284c7] font-bold font-body">Settlement</p>
                  <p className="text-sm font-black text-slate-900 mt-1 uppercase">Instant</p>
                </div>
                <div className="glass-card p-4 rounded-xl shadow-sm border border-slate-200/50">
                  <p className="text-[9px] uppercase tracking-widest text-[#0284c7] font-bold font-body">Due Diligence</p>
                  <p className="text-sm font-black text-slate-900 mt-1 uppercase">AI Native</p>
                </div>
                <div className="glass-card p-4 rounded-xl shadow-sm border border-slate-200/50">
                  <p className="text-[9px] uppercase tracking-widest text-[#0284c7] font-bold font-body">Governance</p>
                  <p className="text-sm font-black text-slate-900 mt-1 uppercase">On-chain</p>
                </div>
              </motion.div>
            </div>
          </div>
        </section>

        {/* Global News Cards
        <section className="px-6 relative z-20">
          <NewsCards />
        </section> */}

        {/* Why AURA-3 */}
        <section className="py-24 px-6 relative bg-surface-container-lowest overflow-hidden">
          <div className="max-w-4xl mx-auto relative z-10">
            <div className="inline-block px-3 py-1 border border-[#0284c7]/30 text-[#0284c7] font-mono text-[10px] uppercase tracking-widest mb-8">Mission Briefing</div>
            <h2 className="font-body font-black text-4xl md:text-5xl uppercase tracking-tighter mb-8 leading-tight">Addressing the <span className="text-secondary-fixed">Systemic Gaps</span> in Venture Capital</h2>
            <div className="space-y-6 text-on-surface-variant text-lg font-light leading-relaxed">
              <p>Centralized Venture Capital ecosystems have long struggled with structural inefficiencies: opaque investment criteria, restricted access for retail participants, and decision-making processes that concentrate power within small, homogeneous networks.</p>
              <p>These shortcomings disproportionately affect founders from underrepresented communities, whose funding prospects are shaped more by personal connections than by the merit of their ventures.</p>
              <p>AURA3 reengineers the funding pipeline from the ground up by combining on-chain token governance via ERC-20 smart contracts, an off-chain FinScope AI engine for risk assessment, and a milestone-gated treasury release mechanism.</p>
            </div>
          </div>
          <div className="absolute right-0 top-1/2 -translate-y-1/2 w-1/3 h-full opacity-10 pointer-events-none">
            {/* Keeping it simple without raw image tag, maybe just abstract gradient */}
            <div className="w-full h-full bg-gradient-to-l from-[#03e1ff] to-transparent" />
          </div>
        </section>

        {/* Problem Section: The Centralization Gap */}
        <section className="py-24 px-6 bg-white border-y border-outline-variant/10 relative">
          <div className="max-w-7xl mx-auto">
            <div className="flex flex-col md:flex-row justify-between items-end mb-16 gap-6">
              <div>
                <h2 className="font-body font-black text-4xl md:text-5xl uppercase tracking-tighter mb-4">The <span className="text-rose-500">Centralization</span> Gap</h2>
                <p className="text-on-surface-variant max-w-xl">Traditional venture capital is a black box. Opaque criteria, restricted access, and archaic manual processing stifle global innovation.</p>
              </div>
              <div className="font-['JetBrains_Mono'] text-[10px] text-error uppercase border border-error/20 px-4 py-2 flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-error" />
                System Inefficiency Detected
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-1">
              <div className="p-10 bg-surface-container border-b md:border-b-0 md:border-r border-outline-variant/5">
                <Lock className="w-8 h-8 text-rose-500/60 mb-6" />
                <h4 className="font-body font-bold text-xl uppercase mb-4">Gated Access</h4>
                <p className="text-on-surface-variant text-sm leading-relaxed">Only 0.1% of global investors have access to tier-1 venture opportunities, creating an artificial scarcity of capital flows.</p>
              </div>
              <div className="p-10 bg-surface-container border-b md:border-b-0 md:border-r border-outline-variant/5">
                <EyeOff className="w-8 h-8 text-rose-500/60 mb-6" />
                <h4 className="font-body font-bold text-xl uppercase mb-4">Opaque Logic</h4>
                <p className="text-on-surface-variant text-sm leading-relaxed">Investment decisions are made behind closed doors with no verifiable data trail or objective performance metrics.</p>
              </div>
              <div className="p-10 bg-surface-container">
                <Timer className="w-8 h-8 text-rose-500/60 mb-6" />
                <h4 className="font-body font-bold text-xl uppercase mb-4">Latency Issues</h4>
                <p className="text-on-surface-variant text-sm leading-relaxed">Settlement and due diligence take months, not seconds. Capital is trapped in legal and bureaucratic friction.</p>
              </div>
            </div>
          </div>
        </section>

        {/* Journey of a Proposal */}
        <section className="py-24 px-6 overflow-hidden relative bg-white border-y border-[#03e1ff]/10">
          <div className="pointer-events-none absolute inset-0" aria-hidden="true">
            <div className="absolute inset-0 bg-[linear-gradient(rgba(3,225,255,0.05)_1px,transparent_1px),linear-gradient(90deg,rgba(3,225,255,0.04)_1px,transparent_1px)] bg-[size:42px_42px] opacity-40" />
            <div className="absolute -top-24 -left-24 w-[480px] h-[480px] rounded-full bg-[#03e1ff]/20 blur-[120px] animate-[pulse_8s_ease-in-out_infinite]" />
            <div className="absolute -bottom-28 -right-24 w-[500px] h-[500px] rounded-full bg-[#00ffbd]/18 blur-[130px] animate-[pulse_10s_ease-in-out_infinite]" />
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_25%,rgba(3,225,255,0.16),transparent_36%),radial-gradient(circle_at_80%_65%,rgba(0,255,189,0.12),transparent_34%)]" />
          </div>

          <div className="max-w-7xl mx-auto relative z-10">
            <div className="text-center mb-20">
              <h2 className="font-body font-black text-5xl md:text-6xl uppercase tracking-tighter mb-4 glitch-text-new">The Journey of a <span className="text-[#0284c7]">Proposal</span></h2>
              <p className="text-on-surface-variant max-w-2xl mx-auto">From a single vision to a fully funded decentralized project. Simple, transparent, autonomous.</p>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-8">
              {proposalJourneySteps.map((step, index) => (
                <motion.div
                  key={step.id}
                  initial={{ opacity: 0, y: 18 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true, amount: 0.25 }}
                  transition={{ duration: 0.45, delay: index * 0.08 }}
                  className="group"
                >
                  <article className="h-full bg-surface-container/40 border border-[#03e1ff]/20 rounded-lg overflow-hidden backdrop-blur-[2px] hover:border-[#03e1ff]/45 hover:shadow-[0_0_35px_rgba(3,225,255,0.14)] transition-all duration-500">
                    <div className="relative aspect-[4/5] overflow-hidden">
                      <img
                        src={step.image}
                        alt={step.title}
                        loading="lazy"
                        referrerPolicy="no-referrer"
                        onError={(e) => {
                          const img = e.currentTarget
                          if (img.dataset.fallbackApplied !== 'true') {
                            img.dataset.fallbackApplied = 'true'
                            img.src = `https://picsum.photos/seed/proposal-${index}/900/1100`
                          }
                        }}
                        className="w-full h-full object-cover opacity-60 saturate-75 group-hover:scale-105 group-hover:opacity-85 group-hover:saturate-100 transition-all duration-700"
                      />
                      <div className="absolute inset-0 bg-gradient-to-t from-white/80 via-white/25 to-transparent" />
                      <div className="absolute top-4 left-4 px-2.5 py-1 border border-[#03e1ff]/35 bg-black/60 backdrop-blur-md text-[10px] font-['JetBrains_Mono'] font-bold tracking-[0.2em] text-[#7cf2ff]">
                        STEP {step.id}
                      </div>
                      <span className="absolute bottom-3 right-3 text-[90px] leading-none font-black text-[#03e1ff]/12 group-hover:text-[#03e1ff]/20 transition-colors">
                        {step.id}
                      </span>
                    </div>

                    <div className="p-5 text-center">
                      <h4 className="font-body font-black text-xl uppercase tracking-wide mb-2 text-slate-900 group-hover:text-[#0284c7] transition-colors">
                        {step.title}
                      </h4>
                      <p className="text-on-surface-variant text-sm font-light leading-relaxed">
                        {step.description}
                      </p>
                    </div>
                  </article>
                </motion.div>
              ))}
            </div>
          </div>
        </section>

        <ScrollingFeatures />

        {/* Footer */}
        <footer className="bg-surface-container-lowest border-t border-outline-variant/10 pt-20 pb-32 px-6">
          <div className="max-w-7xl mx-auto">
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-12 mb-20">
              <div className="col-span-2 lg:col-span-2">
                <div className="text-2xl font-black text-[#03e1ff] tracking-tighter mb-6">AURA3</div>
                <p className="text-on-surface-variant text-sm max-w-sm mb-8 font-light">
                  The first truly autonomous capital intelligence protocol. Powered by Ethereum and proprietary sovereign intelligence.
                </p>
                <div className="flex gap-4">
                  <div className="w-10 h-10 border border-outline-variant/20 flex items-center justify-center cursor-pointer hover:border-[#03e1ff] transition-all text-gray-400 hover:text-[#03e1ff]">
                    <Share2 className="w-4 h-4" />
                  </div>
                  <div className="w-10 h-10 border border-outline-variant/20 flex items-center justify-center cursor-pointer hover:border-[#03e1ff] transition-all text-gray-400 hover:text-[#03e1ff]">
                    <Users className="w-4 h-4" />
                  </div>
                </div>
              </div>
              <div>
                <h5 className="font-body font-bold uppercase text-xs tracking-widest text-[#0284c7] mb-6">Protocol</h5>
                <ul className="space-y-4 text-on-surface-variant text-sm">
                  <li><a className="hover:text-[#0284c7] transition-all" href="#">Treasury</a></li>
                  <li><a className="hover:text-[#0284c7] transition-all" href="#">Node Network</a></li>
                  <li><a className="hover:text-[#0284c7] transition-all" href="#">Yield Model</a></li>
                  <li><a className="hover:text-[#0284c7] transition-all" href="#">Analytics</a></li>
                </ul>
              </div>
              <div>
                <h5 className="font-body font-bold uppercase text-xs tracking-widest text-emerald-500 mb-6">Governance</h5>
                <ul className="space-y-4 text-on-surface-variant text-sm">
                  <li><a className="hover:text-emerald-500 transition-all" href="#">V-Token</a></li>
                  <li><a className="hover:text-emerald-500 transition-all" href="#">DAO Portal</a></li>
                  <li><a className="hover:text-emerald-500 transition-all" href="#">Voter Staking</a></li>
                  <li><a className="hover:text-emerald-500 transition-all" href="#">Proposals</a></li>
                </ul>
              </div>
              <div>
                <h5 className="font-body font-bold uppercase text-xs tracking-widest text-purple-500 mb-6">Resources</h5>
                <ul className="space-y-4 text-on-surface-variant text-sm">
                  <li><a className="hover:text-purple-500 transition-all" href="#">Whitepaper</a></li>
                  <li><a className="hover:text-purple-500 transition-all" href="#">Documentation</a></li>
                  <li><a className="hover:text-purple-500 transition-all" href="#">API Access</a></li>
                  <li><a className="hover:text-purple-500 transition-all" href="#">Media Kit</a></li>
                </ul>
              </div>
            </div>
            
            <div className="pt-8 border-t border-outline-variant/10 flex flex-col md:flex-row justify-between items-center gap-6">
              <div className="text-[10px] font-['JetBrains_Mono'] text-on-surface-variant uppercase tracking-widest">
                © 2026 AURA3. ALL RIGHTS RESERVED.
              </div>
              <div className="flex gap-8 text-[10px] font-['JetBrains_Mono'] text-on-surface-variant uppercase tracking-widest">
                <a className="hover:text-[#03e1ff]" href="#">Privacy Policy</a>
                <a className="hover:text-[#03e1ff]" href="#">Terms of Service</a>
                <a className="hover:text-[#03e1ff]" href="#">Legal Disclaimer</a>
              </div>
            </div>
          </div>
        </footer>
      </main>
    </div>
  )
}
