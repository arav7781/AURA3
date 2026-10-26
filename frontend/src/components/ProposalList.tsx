'use client'

import { useProposals } from '@/hooks/useProposals'
import Link from 'next/link'
import { formatEther } from 'viem'
import { Zap, Loader2 } from 'lucide-react'
import { StartupAvatar } from '@/components/StartupAvatar'
import { CurrencyDisplay } from '@/components/CurrencyDisplay'
import { motion, Variants } from 'framer-motion'
import { ProposalCard } from '@/components/ProposalCard'

const containerVars: Variants = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.1 } }
}

const itemVars: Variants = {
  hidden: { opacity: 0, y: 15 },
  show: { opacity: 1, y: 0, transition: { type: 'spring', stiffness: 300, damping: 24 } }
}

export function ProposalList({
  filterFounder,
  source,
}: {
  filterFounder?: `0x${string}`
  source?: 'founder' | 'investor' | 'startup'
}) {
  const { proposals, isLoading } = useProposals()

  if (isLoading) {
    return (
      <div className="flex flex-col justify-center items-center py-20 gap-4">
        <Loader2 className="w-6 h-6 text-[#03e1ff] animate-spin" />
        <p className="text-[10px] font-bold font-mono text-sky-300 uppercase tracking-widest">Awaiting Chain Response...</p>
      </div>
    )
  }

  const filtered = filterFounder
    ? proposals.filter(p => p.founder.toLowerCase() === filterFounder.toLowerCase())
    : proposals

  if (filtered.length === 0) {
    return (
      <div className="border border-[#111] bg-[#050505] text-sky-300 text-[10px] font-bold font-mono p-12 text-center uppercase tracking-widest">
        <Zap className="w-8 h-8 text-sky-200 mx-auto mb-4" />
        No active data streams found
      </div>
    )
  }

  return (
    <motion.div variants={containerVars} initial="hidden" animate="show" className="flex flex-col gap-2 max-w-5xl mx-auto w-full">
      {filtered.map((proposal) => (
        <ProposalCard key={proposal.id} proposal={proposal} itemVars={itemVars} source={source} />
      ))}
    </motion.div>
  )
}
