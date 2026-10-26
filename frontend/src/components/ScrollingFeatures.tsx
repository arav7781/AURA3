'use client'

import Image from 'next/image'
import { useEffect, useRef, useState } from 'react'

interface Feature {
  title: string
  description: string
  code: string
  language: string
}

const features: Feature[] = [
  {
    title: 'Deterministic Governance Engine',
    description:
      'Proposal votes execute with transparent on-chain state transitions, keeping settlement logic auditable and deterministic.',
    code: `const proposalState = await ventureDao.proposals(id)
if (proposalState.forVotes > proposalState.againstVotes) {
  await ventureDao.executeProposal(id)
}
settlement status: executed`,
    language: 'typescript',
  },
  {
    title: 'AI Due-Diligence Pipeline',
    description:
      'FinScope routes startup documents through a structured analysis flow to generate risk, market, and recommendation signals.',
    code: `POST /api/startups/{id}/documents/upload
POST /api/startups/{id}/analyze
GET  /api/startups/{id}/report/status
  => { status: "complete", analysis: {...} }`,
    language: 'http',
  },
  {
    title: 'Investor Exit Liquidity Controls',
    description:
      'Founder-configured exit windows lock valuation and liquidity pool rules, enabling programmable investor exits.',
    code: `await startupContract.openExit(
  parseEther(exitValuationEth),
  { value: parseEther(poolDepositEth) }
)
investors can call: exit()`,
    language: 'solidity',
  },
  {
    title: 'Multi-Layer Security Surface',
    description:
      'Input guardrails, role-based access control, and wallet-signed transactions protect user flows across frontend and backend.',
    code: `if (isPromptBlocked(question)) {
  return { status: 400, detail: 'Blocked by safety policy' }
}
require(msg.sender == founder, 'Unauthorized')`,
    language: 'javascript',
  },
]

export function ScrollingFeatures() {
  const [scrollProgress, setScrollProgress] = useState(0)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handleScroll = () => {
      if (!containerRef.current) return

      const { top, bottom } = containerRef.current.getBoundingClientRect()
      const viewportHeight = window.innerHeight
      const totalHeight = bottom - top
      const visiblePortion = viewportHeight - top
      const progress = Math.max(0, Math.min(1, visiblePortion / totalHeight))

      setScrollProgress(progress)
    }

    handleScroll()
    window.addEventListener('scroll', handleScroll)
    return () => window.removeEventListener('scroll', handleScroll)
  }, [])

  return (
    <section ref={containerRef} className="relative w-full py-24 px-6 bg-slate-50 overflow-hidden">
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute top-0 left-0 w-[520px] h-[520px] bg-gradient-to-br from-[#0284c7]/10 to-transparent rounded-full blur-[120px]" />
        <div className="absolute bottom-0 right-0 w-[520px] h-[520px] bg-gradient-to-tl from-[#00ffbd]/16 to-transparent rounded-full blur-[120px]" />
      </div>

      <div className="relative z-10 max-w-7xl mx-auto">
        <div className="text-center mb-20">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 mb-4 rounded-full bg-[#0284c7]/10 border border-[#0284c7]/30">
            <Image src="/vercel.png" alt="AURA3 Icon" width={14} height={14} className="rounded-sm" />
            <span className="text-[11px] font-mono text-[#0284c7] uppercase tracking-[0.18em]">AURA3 Architecture Stream</span>
          </div>
          <h2 className="text-4xl md:text-5xl font-body font-black uppercase tracking-tight text-slate-900 mb-4 drop-shadow-[0_2px_10px_rgba(2,132,199,0.15)]">
            Neural Feature Matrix
          </h2>
          <p className="text-slate-600 max-w-2xl mx-auto">
            Scroll through the live architecture lens connecting on-chain governance, AI analysis, and programmable execution.
          </p>
        </div>

        <div className="space-y-24">
          {features.map((feature, index) => {
            const isEven = index % 2 === 0
            const isInView = scrollProgress > index / features.length && scrollProgress < (index + 1) / features.length
            const itemProgress = (scrollProgress - index / features.length) * features.length
            const clampedProgress = Math.max(0, Math.min(1, itemProgress))

            return (
              <div
                key={feature.title}
                className={`flex flex-col ${isEven ? 'md:flex-row' : 'md:flex-row-reverse'} gap-8 md:gap-12 items-center`}
              >
                <div
                  className={`flex-1 transition-all duration-700 ${
                    isInView ? 'opacity-100 translate-y-0' : 'opacity-65 translate-y-4'
                  }`}
                  style={{
                    transform: `translateX(${isEven ? -20 * (1 - clampedProgress) : 20 * (1 - clampedProgress)}px)`,
                  }}
                >
                  <div className="mb-4">
                    <span className="inline-block px-3 py-1 rounded-full bg-[#0284c7]/10 border border-[#0284c7]/30 text-[11px] font-mono text-[#0284c7] uppercase tracking-widest">
                      {`Layer ${index + 1}`}
                    </span>
                  </div>
                  <h3 className="text-3xl font-body font-black text-slate-900 mb-4 uppercase tracking-tight">{feature.title}</h3>
                  <p className="text-slate-600 text-lg leading-relaxed mb-6">{feature.description}</p>
                </div>

                <div
                  className={`flex-1 transition-all duration-700 ${
                    isInView ? 'opacity-100 scale-100' : 'opacity-70 scale-95'
                  }`}
                  style={{
                    transform: `translateX(${isEven ? 20 * (1 - clampedProgress) : -20 * (1 - clampedProgress)}px)`,
                  }}
                >
                  <div className="relative">
                    <div className="bg-white border border-slate-200 rounded-lg overflow-hidden shadow-[0_8px_30px_rgb(0,0,0,0.08)]">
                      <div className="bg-slate-50 px-4 py-3 border-b border-slate-200 flex items-center gap-2">
                        <div className="flex gap-2">
                          <div className="w-2.5 h-2.5 rounded-full bg-red-500/70" />
                          <div className="w-2.5 h-2.5 rounded-full bg-yellow-500/70" />
                          <div className="w-2.5 h-2.5 rounded-full bg-green-500/70" />
                        </div>
                        <span className="ml-auto text-[10px] font-mono text-slate-500 uppercase tracking-wider">
                          {feature.language}
                        </span>
                      </div>

                      <div className="p-6 overflow-x-auto bg-white">
                        <pre className="font-mono text-sm text-slate-700 whitespace-pre-wrap break-words leading-relaxed">
                          <code>{feature.code}</code>
                        </pre>
                      </div>

                      <div className="bg-slate-50 px-6 py-2 border-t border-slate-200 text-[10px] font-mono text-slate-500 uppercase tracking-wider">
                        $ node aura3-runtime --sync
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </section>
  )
}
