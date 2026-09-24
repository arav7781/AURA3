'use client'

import { motion, useMotionValue, useSpring, useTransform, Variants } from 'framer-motion'
import Link from 'next/link'
import { ArrowRight } from 'lucide-react'
import { StartupAvatar } from '@/components/StartupAvatar'
import { CurrencyDisplay } from '@/components/CurrencyDisplay'
import { formatEther } from 'viem'
import React from 'react'

export function ProposalCard({
  proposal,
  itemVars,
  source,
}: {
  proposal: any
  itemVars: Variants
  source?: 'founder' | 'investor' | 'startup'
}) {
  const x = useMotionValue(0)
  const y = useMotionValue(0)
  
  const mouseXSpring = useSpring(x, { stiffness: 400, damping: 30 })
  const mouseYSpring = useSpring(y, { stiffness: 400, damping: 30 })
  
  const rotateX = useTransform(mouseYSpring, [-0.5, 0.5], ["15deg", "-15deg"])
  const rotateY = useTransform(mouseXSpring, [-0.5, 0.5], ["-15deg", "15deg"])

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const width = rect.width
    const height = rect.height
    
    const mouseX = e.clientX - rect.left
    const mouseY = e.clientY - rect.top
    
    x.set(mouseX / width - 0.5)
    y.set(mouseY / height - 0.5)
  }

  const handleMouseLeave = () => {
    x.set(0)
    y.set(0)
  }

  const now = Math.floor(Date.now() / 1000)
  const isEnded = Number(proposal.voteEnd) <= now
  const isPassed = proposal.forVotes > proposal.againstVotes

  let badgeColor = 'text-[#03e1ff]'
  let statusText = 'Active'
  
  if (proposal.executed) {
    badgeColor = 'text-[#00ffbd]'
    statusText = 'Executed'
  } else if (isEnded) {
    if (isPassed) {
      badgeColor = 'text-[#00ffbd]'
      statusText = 'Passed'
    } else {
      badgeColor = 'text-red-500'
      statusText = 'Rejected'
    }
  }

  const forVotesNum = Number(formatEther(proposal.forVotes))
  const againstVotesNum = Number(formatEther(proposal.againstVotes))
  const totalVotes = forVotesNum + againstVotesNum
  const forPercent = totalVotes > 0 ? (forVotesNum / totalVotes) * 100 : 0
  const accessNodeHref = source ? `/proposal/${proposal.id}?source=${source}` : `/proposal/${proposal.id}`

  return (
    <motion.div
      variants={itemVars}
      style={{ perspective: 1500 }}
      className="w-full relative py-4"
    >
      <motion.div
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
        style={{
          rotateX,
          rotateY,
          transformStyle: "preserve-3d"
        }}
        className="glass-panel group relative flex flex-col md:flex-row md:flex-wrap items-stretch md:items-center py-6 px-8 gap-8 w-full border border-slate-200 bg-white shadow-[0_4px_24px_rgba(0,0,0,0.06)]"
      >
        {/* Animated Connecting SVG Border Effect */}
        <div className="absolute inset-0 border border-[#0284c7]/0 group-hover:border-[#0284c7]/30 transition-colors duration-500 block pointer-events-none" style={{ transform: "translateZ(-20px)" }} />
        
        {/* Glow backdrop tracking mouse */}
        <motion.div 
          className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-[#0284c7]/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none blur-md"
          style={{ transform: "translateZ(10px)" }}
        />

        <div className="flex items-center gap-6 min-w-[250px] flex-1" style={{ transform: "translateZ(30px)" }}>
          <StartupAvatar seed={proposal.id} size={48} />
          <div className="flex flex-col">
            <h3 className="text-base font-bold text-slate-900 mb-1.5 group-hover:text-[#0284c7] transition-colors drop-shadow-md">{proposal.description}</h3>
            <div className="flex items-center gap-3">
              <span className={`text-[10px] font-bold font-mono tracking-[0.25em] uppercase ${badgeColor} drop-shadow-[0_0_5px_currentColor] border border-current px-2 py-0.5 rounded-sm`}>
                {statusText}
              </span>
              <span className="text-slate-400 text-[10px] font-bold font-mono tracking-[0.2em]">SEQ-{proposal.id}</span>
            </div>
          </div>
        </div>

        <div className="flex items-center justify-end gap-10 shrink-0" style={{ transform: "translateZ(40px)" }}>
          <div className="text-right">
            <p className="text-[10px] font-bold font-mono text-sky-400 uppercase tracking-[0.2em] mb-2 opacity-60">Capital Target</p>
            <CurrencyDisplay value={Number(formatEther(proposal.fundingAmount))} decimals={3} />
          </div>
          <div className="hidden lg:block w-px h-10 bg-slate-200" />
          <div className="text-right">
            <p className="text-[10px] font-bold font-mono text-[#00ffbd] uppercase tracking-[0.2em] mb-2 opacity-60">Valuation Lock</p>
            <CurrencyDisplay value={Number(formatEther(proposal.valuation))} decimals={3} />
          </div>
        </div>

        <div className="shrink-0 ml-0 md:ml-auto flex items-center relative z-20 w-full md:w-auto" style={{ transform: "translateZ(50px)" }}>
          <Link
            href={accessNodeHref}
            className="flex items-center justify-center px-6 py-3 rounded-sm border border-slate-200 group-hover:border-[#0284c7]/60 transition-all bg-white hover:bg-[#0284c7]/5 backdrop-blur-md shadow-[0_2px_10px_rgba(0,0,0,0.05)] group-hover:shadow-[0_4px_20px_rgba(2,132,199,0.15)] overflow-hidden relative w-full md:w-auto"
          >
            <div className="absolute inset-0 opacity-0 hover:opacity-100 bg-[linear-gradient(45deg,transparent_25%,rgba(2,132,199,0.1)_50%,transparent_75%)] bg-[length:250%_250%,100%_100%] animate-[bg-shift_2s_linear_infinite]" />
            <span className="text-[11px] font-bold font-mono text-slate-600 group-hover:text-slate-900 transition-colors tracking-[0.3em] uppercase mr-3 relative z-10">Access Node</span>
            <ArrowRight className="w-4 h-4 text-slate-400 group-hover:text-[#0284c7] group-hover:translate-x-2 transition-transform duration-300 relative z-10" />
          </Link>
        </div>
      </motion.div>
    </motion.div>
  )
}
