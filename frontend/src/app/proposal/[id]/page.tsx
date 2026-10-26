'use client'

import { useParams, useSearchParams } from 'next/navigation'
import { useReadContract, useWriteContract, useAccount } from 'wagmi'
import { VENTUREDAO_ADDRESS, VENTUREDAO_ABI, STARTUPCONTRACT_ABI } from '@/constants/abis'
import { formatEther, parseEther } from 'viem'
import { useState, useEffect } from 'react'
import { Loader2, ThumbsUp, ThumbsDown, Bot, Play, ArrowLeft, Download } from 'lucide-react'
import Link from 'next/link'
import { FounderStartupActions } from '@/components/FounderStartupActions'
import { InvestorStartupActions } from '@/components/InvestorStartupActions'
import { CurrencyDisplay } from '@/components/CurrencyDisplay'
import { useAuth } from '@/context/AuthContext'
import { EvaluationReport } from '@/components/EvaluationReport'
import { VentureAnalystChat } from '@/components/VentureAnalystChat'
import { apiJson, downloadReportPdf, type AnalysisReport, type AnalysisStatus, type StartupSummary } from '@/lib/api'

export default function ProposalDetail() {
  const params = useParams()
  const searchParams = useSearchParams()
  const proposalId = typeof params.id === 'string' ? params.id : params.id?.[0]
  const { address } = useAccount()
  const { userRole } = useAuth()

  const [aiReport, setAiReport] = useState<AnalysisReport | null>(null)
  const [backendStartup, setBackendStartup] = useState<StartupSummary | null>(null)
  const [isReportLoading, setIsReportLoading] = useState(true)

  // Fetch Proposal Details
  const { data: rawProposal, refetch: refetchProposal } = useReadContract({
    address: VENTUREDAO_ADDRESS,
    abi: VENTUREDAO_ABI,
    functionName: 'proposals',
    args: proposalId ? [BigInt(proposalId)] : undefined,
    query: { enabled: !!proposalId }
  })

  // Has Voted
  const { data: hasVoted } = useReadContract({
    address: VENTUREDAO_ADDRESS,
    abi: VENTUREDAO_ABI,
    functionName: 'hasVoted',
    args: proposalId && address ? [BigInt(proposalId), address] : undefined,
    query: { enabled: !!proposalId && !!address }
  })

  const { writeContract: writeVote, isPending: isVoting } = useWriteContract()
  const { writeContract: writeExecute, isPending: isExecuting } = useWriteContract()

  const [isDownloading, setIsDownloading] = useState(false)
  const source = searchParams.get('source')
  const isFounderContext = source === 'founder' || userRole === 'startup'
  const backHref = isFounderContext ? '/founder' : '/investor'
  const backLabel = isFounderContext ? 'Return to Founder Portal' : 'Return to Stream'

  const handleDownloadPDF = async () => {
    if (!backendStartup) return
    try {
      setIsDownloading(true)
      await downloadReportPdf(backendStartup.startup_id, `AURA3_Report_Prop${proposalId}.pdf`)
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to download report.')
    } finally {
      setIsDownloading(false)
    }
  }

  useEffect(() => {
    if (!rawProposal) return
    const p = rawProposal as unknown as [string, bigint, bigint, string]
    const founder = p[0].toLowerCase()
    const description = p[3]
    let cancelled = false

    const findEvaluation = async () => {
      const startups = await apiJson<StartupSummary[]>('/startups')
      const byFounder = startups.filter(s =>
        s.founder_address?.toLowerCase() === founder || s.team?.toLowerCase() === founder)
      const matched =
        byFounder.find(s => description.includes(s.name) || s.description === description) || byFounder[0]
      if (!matched || cancelled) return
      setBackendStartup(matched)
      for (let i = 0; i < 40 && !cancelled; i++) {
        const status = await apiJson<AnalysisStatus>(`/api/startups/${matched.startup_id}/report/status`)
        if (status.status === 'complete' && status.analysis) {
          setAiReport(status.analysis)
          return
        }
        if (status.status !== 'processing') return
        await new Promise(resolve => setTimeout(resolve, 3000))
      }
    }

    findEvaluation()
      .catch(err => console.error('Failed to fetch AI report:', err))
      .finally(() => { if (!cancelled) setIsReportLoading(false) })
    return () => { cancelled = true }
  }, [rawProposal])

  if (!rawProposal) {
    return (
      <div className="flex justify-center items-center py-24">
        <Loader2 className="w-8 h-8 text-emerald-500 animate-spin" />
      </div>
    )
  }

  const p = rawProposal as unknown as [string, bigint, bigint, string, bigint, bigint, bigint, bigint, bigint, boolean, string, string]
  const proposal = {
    founder: p[0],
    fundingAmount: p[1],
    valuation: p[2],
    description: p[3],
    snapshotBlock: p[4],
    voteStart: p[5],
    voteEnd: p[6],
    forVotes: p[7],
    againstVotes: p[8],
    executed: p[9],
    startupContract: p[10],
    startupToken: p[11],
  }

  const now = Math.floor(Date.now() / 1000)
  // Fix voteEnd index reading based on ABI (voteEnd is typicaly block or timestamp, let's assume timestamp = voteEnd)
  const isEnded = Number(proposal.voteEnd) <= now
  const isPassed = proposal.forVotes > proposal.againstVotes

  const handleVote = (support: boolean) => {
    writeVote({
      address: VENTUREDAO_ADDRESS,
      abi: VENTUREDAO_ABI,
      functionName: 'vote',
      args: [BigInt(proposalId!), support],
      chainId: 11155111,
    })
  }

  const handleExecute = () => {
    writeExecute({
      address: VENTUREDAO_ADDRESS,
      abi: VENTUREDAO_ABI,
      functionName: 'executeProposal',
      args: [BigInt(proposalId!)],
      chainId: 11155111,
    })
  }

  return (
    <div className="max-w-6xl mx-auto px-6 py-10">
      <Link href={backHref} className="inline-flex items-center text-[10px] font-bold font-mono text-[#444] hover:text-[#03e1ff] mb-8 uppercase tracking-widest transition-colors group">
        <ArrowLeft className="w-3 h-3 mr-2 group-hover:-translate-x-1 transition-transform" /> 
        {backLabel}
      </Link>
      
      <div className="border border-[#111] bg-black mb-10">
        <div className="p-8 border-b border-[#111] flex justify-between items-start">
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-4">
              <span className="text-[10px] font-bold font-mono text-[#03e1ff] uppercase tracking-tighter bg-[#03e1ff]/5 px-2 py-0.5 border border-[#03e1ff]/20">
                PROPOSAL-{proposalId}
              </span>
              <span className="text-[#333] text-[10px] font-bold font-mono uppercase tracking-tighter">
                Ref: {proposal.snapshotBlock.toString()}
              </span>
            </div>
            <h1 className="text-2xl font-bold text-white mb-4 tracking-tight">{proposal.description}</h1>
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-bold font-mono text-[#444] uppercase">Originator:</span>
              <code className="text-[10px] font-mono text-[#03e1ff]">{proposal.founder}</code>
            </div>
          </div>
          
          <div className="text-right">
            <div className="inline-block p-4 border border-[#111] bg-[#050505] min-w-[140px]">
              <p className="text-[9px] font-bold text-[#444] uppercase mb-1">State</p>
              <p className={`text-xs font-bold font-mono uppercase tracking-widest ${proposal.executed ? 'text-[#00ffbd]' : isEnded ? (isPassed ? 'text-[#03e1ff]' : 'text-red-500') : 'text-yellow-500'}`}>
                {proposal.executed ? 'Executed' : isEnded ? (isPassed ? 'Passed' : 'Rejected') : 'Active'}
              </p>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 lg:grid-cols-4 border-b border-[#111]">
          <div className="p-6 border-r border-[#111]">
            <p className="text-[9px] font-bold text-[#444] uppercase mb-4">Funding Requirement</p>
            <CurrencyDisplay value={Number(formatEther(proposal.fundingAmount))} featured={true} />
          </div>
          <div className="p-6 border-r border-[#111]">
            <p className="text-[9px] font-bold text-[#444] uppercase mb-4">Contract Valuation</p>
            <CurrencyDisplay value={Number(formatEther(proposal.valuation))} featured={true} />
          </div>
          <div className="p-6 border-r border-[#111]">
            <p className="text-[9px] font-bold text-[#444] uppercase mb-2">Consensus "For"</p>
            <p className="text-xl font-mono text-[#00ffbd] leading-none">
              {Number(formatEther(proposal.forVotes)).toFixed(2)}
            </p>
          </div>
          <div className="p-6">
            <p className="text-[9px] font-bold text-[#444] uppercase mb-2">Consensus "Against"</p>
            <p className="text-xl font-mono text-red-500 leading-none">
              {Number(formatEther(proposal.againstVotes)).toFixed(2)}
            </p>
          </div>
        </div>

        <div className="p-10 flex flex-col md:flex-row items-center justify-between gap-8 bg-[#030303]">
          {!isEnded ? (
            <div className="flex gap-4 w-full md:w-auto">
              <button 
                onClick={() => handleVote(true)}
                disabled={hasVoted || isVoting}
                className="flex-1 md:flex-none btn-pro btn-pro-cyan h-12 px-10"
              >
                {isVoting ? <Loader2 className="w-4 h-4 animate-spin" /> : <ThumbsUp className="w-4 h-4 mr-2" />}
                Vote Affirmative
              </button>
              <button 
                onClick={() => handleVote(false)}
                disabled={hasVoted || isVoting}
                className="flex-1 md:flex-none btn-pro btn-pro-outline h-12 px-10 border-red-900/30 text-red-500 hover:bg-red-500/5 hover:border-red-500/50"
              >
                {isVoting ? <Loader2 className="w-4 h-4 animate-spin" /> : <ThumbsDown className="w-4 h-4 mr-2" />}
                Vote Negative
              </button>
            </div>
          ) : isPassed && !proposal.executed ? (
            <button 
              onClick={handleExecute}
              disabled={isExecuting}
              className="w-full md:w-auto btn-pro btn-pro-cyan h-12 px-12"
            >
              {isExecuting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4 mr-2" />}
              Execute Transaction
            </button>
          ) : (
            <div className="text-[10px] font-bold font-mono text-[#333] uppercase spacing-widest">
              Governance window closed for this session.
            </div>
          )}
          
          {!isEnded && hasVoted && (
            <div className="flex items-center gap-2 px-4 py-2 bg-[#00ffbd]/5 border border-[#00ffbd]/20">
              <div className="w-1.5 h-1.5 rounded-full bg-[#00ffbd]" />
              <p className="text-[10px] font-bold font-mono text-[#00ffbd] uppercase">Vote Registered</p>
            </div>
          )}
        </div>
      </div>

      {/* AI Analysis Section */}
      <div className="mt-10 mb-10">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-6 gap-4">
          <div>
            <h2 className="text-xl font-bold text-slate-900 mb-2 uppercase tracking-wide">AI Venture Analysis</h2>
            <p className="text-[10px] font-bold font-mono text-[#00ffbd] uppercase tracking-widest">Generative Intelligence Report</p>
          </div>
          {aiReport && backendStartup && (
            <button 
              onClick={handleDownloadPDF}
              disabled={isDownloading}
              className="btn-pro btn-pro-cyan h-10 px-6 shrink-0 flex items-center justify-center gap-2"
            >
              {isDownloading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
              {isDownloading ? 'Generating PDF...' : 'Download Full PDF Report'}
            </button>
          )}
        </div>

        {isReportLoading ? (
          <div className="p-12 text-center bg-white border border-slate-200 rounded-xl">
            <Loader2 className="w-6 h-6 text-[#0284c7] animate-spin mx-auto mb-4" />
            <p className="text-sm text-slate-500">Loading the AI evaluation…</p>
          </div>
        ) : !aiReport ? (
          <div className="p-12 text-center bg-white border border-dashed border-slate-300 rounded-xl">
            <Bot className="w-8 h-8 text-slate-400 mx-auto mb-4" />
            <p className="text-sm text-slate-500">No AI evaluation is linked to this proposal's founder wallet yet.</p>
          </div>
        ) : (
          <EvaluationReport report={aiReport} />
        )}
      </div>

      {backendStartup && <VentureAnalystChat startupId={backendStartup.startup_id} startupName={backendStartup.name} />}

      {/* Startup Management Section */}
      {proposal.executed && proposal.startupContract !== '0x0000000000000000000000000000000000000000' && (
        <div className="mt-20 pt-20 border-t border-[#111]">
          <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-10 gap-6">
            <div>
              <h2 className="text-xl font-bold text-slate-900 mb-2 uppercase tracking-wide">Technical Operations</h2>
              <p className="text-[10px] font-bold font-mono text-[#444] uppercase tracking-widest">Execute equity claims and manage venture exit windows.</p>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-px bg-[#111] border border-[#111]">
            <FounderStartupActions 
              address={proposal.startupContract as `0x${string}`} 
              valuation={proposal.valuation}
            />
            <InvestorStartupActions 
              address={proposal.startupContract as `0x${string}`} 
              initialValuation={proposal.valuation}
            />
          </div>
        </div>
      )}

      {/* Pre-Execution Placeholder */}
      {!proposal.executed && (
        <div className="mt-10 border border-[#111] border-dashed p-12 text-center bg-white/[0.01]">
           <p className="text-[10px] font-bold font-mono text-[#333] uppercase tracking-[0.2em] max-w-sm mx-auto">
             Data Stream Locked: Awaiting execution confirm to initialize operations.
           </p>
        </div>
      )}
    </div>
  )
}
