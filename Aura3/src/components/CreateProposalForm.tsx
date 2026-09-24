'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useAccount, useWriteContract, useWaitForTransactionReceipt } from 'wagmi'
import { parseEther } from 'viem'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ArrowRight, Loader2, Rocket, UploadCloud, Wallet } from 'lucide-react'
import { VENTUREDAO_ADDRESS, VENTUREDAO_ABI } from '@/constants/abis'
import { useEthPrice } from '@/hooks/useEthPrice'
import { AgentProgress } from '@/components/AgentProgress'
import { ComplianceBadge } from '@/components/EvaluationReport'
import { apiJson, API_BASE, type AnalysisReport, type AnalysisStatus, type StartupSummary } from '@/lib/api'

type Unit = 'eth' | 'usd'
type Phase = 'form' | 'registering' | 'uploading' | 'analyzing' | 'done'

const STAGES = ['Idea', 'Pre-seed', 'Seed', 'Series A', 'Series B+']
const DOMAINS = ['Fintech', 'Agritech', 'Healthtech', 'Edtech', 'Climate', 'SaaS / B2B', 'Consumer', 'Web3 / Blockchain', 'Deeptech / AI', 'Logistics', 'Other']

const label = 'block text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1.5'

export function CreateProposalForm({ onSuccess }: { onSuccess: () => void }) {
  const { address, isConnected } = useAccount()
  const ethPrice = useEthPrice()

  const [name, setName] = useState('')
  const [domain, setDomain] = useState('Fintech')
  const [stage, setStage] = useState('Seed')
  const [team, setTeam] = useState('')
  const [description, setDescription] = useState('')
  const [cin, setCin] = useState('')
  const [fundingAmount, setFundingAmount] = useState('')
  const [valuation, setValuation] = useState('')
  const [fundingUnit, setFundingUnit] = useState<Unit>('usd')
  const [valuationUnit, setValuationUnit] = useState<Unit>('usd')
  const [file, setFile] = useState<File | null>(null)

  const [phase, setPhase] = useState<Phase>('form')
  const [stageText, setStageText] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [startup, setStartup] = useState<StartupSummary | null>(null)
  const [report, setReport] = useState<AnalysisReport | null>(null)

  const { data: hash, writeContract, error: writeError, isPending: isConfirmingInWallet } = useWriteContract()
  const { isLoading: isMining, isSuccess } = useWaitForTransactionReceipt({ hash })

  useEffect(() => {
    if (isSuccess) onSuccess()
  }, [isSuccess, onSuccess])

  const toEth = (raw: string, unit: Unit) => {
    const n = Number(raw)
    if (!Number.isFinite(n) || n <= 0) return 0
    if (unit === 'eth') return n
    return ethPrice && ethPrice > 0 ? n / ethPrice : 0
  }
  const toUsd = (raw: string, unit: Unit) => {
    const n = Number(raw)
    if (!Number.isFinite(n) || n <= 0) return 0
    return unit === 'usd' ? n : ethPrice ? n * ethPrice : 0
  }
  const ethString = (n: number) => (Number.isFinite(n) && n > 0 ? n.toFixed(8).replace(/\.?0+$/, '') : '')
  const hint = (value: string, unit: Unit) => {
    const n = Number(value)
    if (!value || !Number.isFinite(n) || n <= 0) return ''
    if (!ethPrice) return ''
    return unit === 'eth'
      ? `≈ $${(n * ethPrice).toLocaleString(undefined, { maximumFractionDigits: 0 })}`
      : `≈ ${(n / ethPrice).toFixed(4)} ETH`
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!file) return
    setError(null)
    try {
      setPhase('registering')
      const fundingUsd = toUsd(fundingAmount, fundingUnit)
      const created = await apiJson<StartupSummary>('/api/startups/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: name.trim(),
          domain,
          stage,
          team: team.trim(),
          description: description.trim(),
          cin: cin.trim() || undefined,
          funding_required: fundingUsd ? `$${Math.round(fundingUsd).toLocaleString()}` : undefined,
          extras: valuation ? `Valuation sought: ${valuation} ${valuationUnit.toUpperCase()}` : undefined,
          founder_address: address,
        }),
      })
      setStartup(created)

      setPhase('uploading')
      const form = new FormData()
      form.append('documents', file)
      await apiJson(`/api/startups/${created.startup_id}/documents/upload`, { method: 'POST', body: form })

      setPhase('analyzing')
      await apiJson(`/api/startups/${created.startup_id}/analyze`, { method: 'POST' })
      for (let i = 0; i < 120; i++) {
        await new Promise(r => setTimeout(r, 2500))
        const status = await apiJson<AnalysisStatus>(`/api/startups/${created.startup_id}/report/status`)
        setStageText(status.stage ?? null)
        if (status.status === 'complete' && status.analysis) {
          setReport(status.analysis)
          setPhase('done')
          return
        }
        if (status.status === 'failed') throw new Error(status.error || 'Analysis failed')
      }
      throw new Error('The evaluation is taking longer than expected — check AI Evaluations shortly.')
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error'
      setError(message === 'Failed to fetch' ? `Cannot reach the AURA-3 backend at ${API_BASE}. Is it running?` : message)
      setPhase('form')
    }
  }

  const confirmOnChain = () => {
    const funding = ethString(toEth(fundingAmount, fundingUnit))
    const value = ethString(toEth(valuation, valuationUnit))
    if (!address || !funding || !value) return
    writeContract({
      address: VENTUREDAO_ADDRESS,
      abi: VENTUREDAO_ABI,
      functionName: 'submitProposal',
      args: [address, parseEther(funding), parseEther(value), `${name.trim()} — ${description.trim()}`.slice(0, 280)],
      chainId: 11155111,
    })
  }

  const unitToggle = (unit: Unit, setUnit: (u: Unit) => void) => (
    <div className="flex border border-slate-200 bg-slate-50 rounded text-[9px] font-mono font-bold">
      {(['usd', 'eth'] as Unit[]).map(u => (
        <button key={u} type="button" onClick={() => setUnit(u)} className={`px-2 py-0.5 uppercase ${unit === u ? 'bg-[#0284c7] text-white' : 'text-slate-500 hover:text-slate-700'}`}>
          {u}
        </button>
      ))}
    </div>
  )

  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
      <div className="px-6 py-4 border-b border-slate-200 bg-slate-50">
        <h2 className="text-[11px] font-bold font-mono text-slate-900 uppercase tracking-widest flex items-center gap-2">
          <Rocket className="w-4 h-4 text-[#0284c7]" /> Submit your startup for AI due diligence
        </h2>
      </div>

      <div className="p-6">
        {phase === 'form' && (
          <form onSubmit={submit} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className={label}>Startup name</label>
                <input required value={name} onChange={e => setName(e.target.value)} className="input-field h-10" placeholder="e.g. KrishiMitra AI" />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className={label}>Domain</label>
                  <select value={domain} onChange={e => setDomain(e.target.value)} className="input-field h-10">
                    {DOMAINS.map(d => <option key={d}>{d}</option>)}
                  </select>
                </div>
                <div>
                  <label className={label}>Stage</label>
                  <select value={stage} onChange={e => setStage(e.target.value)} className="input-field h-10">
                    {STAGES.map(s => <option key={s}>{s}</option>)}
                  </select>
                </div>
              </div>
            </div>

            <div>
              <label className={label}>Describe your startup (what it does, who it serves, traction)</label>
              <textarea required rows={4} value={description} onChange={e => setDescription(e.target.value)} className="input-field py-2.5 resize-y" placeholder="The agents use this with your pitch deck. Mention product, customers, revenue and what you're raising for." />
            </div>

            <div>
              <label className={label}>Team</label>
              <input required value={team} onChange={e => setTeam(e.target.value)} className="input-field h-10" placeholder="Founder names and relevant experience" />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className={`${label} mb-0`}>Funding goal</label>
                  {unitToggle(fundingUnit, setFundingUnit)}
                </div>
                <input type="number" step="any" min="0" required value={fundingAmount} onChange={e => setFundingAmount(e.target.value)} className="input-field h-10" placeholder={fundingUnit === 'usd' ? '1,500,000' : '5'} />
                <p className="mt-1 text-[10px] font-mono text-slate-500">{hint(fundingAmount, fundingUnit)}</p>
              </div>
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className={`${label} mb-0`}>Valuation</label>
                  {unitToggle(valuationUnit, setValuationUnit)}
                </div>
                <input type="number" step="any" min="0" required value={valuation} onChange={e => setValuation(e.target.value)} className="input-field h-10" placeholder={valuationUnit === 'usd' ? '7,000,000' : '25'} />
                <p className="mt-1 text-[10px] font-mono text-slate-500">{hint(valuation, valuationUnit)}</p>
              </div>
              <div>
                <label className={label}>CIN (optional)</label>
                <input value={cin} onChange={e => setCin(e.target.value.toUpperCase())} className="input-field h-10 uppercase" placeholder="U72900KA2021PTC150123" />
                <p className="mt-1 text-[10px] text-slate-500">Checked against the MCA registry</p>
              </div>
            </div>

            <label className="block border-2 border-dashed border-slate-200 rounded-xl p-6 text-center cursor-pointer hover:border-[#0284c7] transition-colors">
              <input type="file" accept=".pdf,.docx,.txt" required onChange={e => setFile(e.target.files?.[0] ?? null)} className="sr-only" />
              <UploadCloud className="w-6 h-6 text-slate-400 mx-auto mb-2" />
              <p className="text-sm text-slate-600">{file ? <span className="font-semibold text-emerald-700">{file.name}</span> : 'Upload your pitch deck (PDF, DOCX or TXT)'}</p>
            </label>

            {error && <p className="text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded-lg px-3 py-2">{error}</p>}

            <button type="submit" className="w-full h-12 bg-[#0284c7] text-white font-bold rounded-lg hover:brightness-110 transition flex items-center justify-center gap-2">
              Analyse with AURA-3 agents <ArrowRight className="w-4 h-4" />
            </button>
          </form>
        )}

        {(phase === 'registering' || phase === 'uploading') && (
          <div className="py-10 text-center text-slate-600">
            <Loader2 className="w-6 h-6 animate-spin text-[#0284c7] mx-auto mb-3" />
            {phase === 'registering' ? 'Registering startup and checking the MCA registry…' : 'Reading your pitch deck and indexing it for the agents…'}
          </div>
        )}

        {phase === 'analyzing' && <AgentProgress stage={stageText} />}

        {phase === 'done' && report && startup && (
          <div className="space-y-5">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-[11px] font-mono uppercase tracking-widest text-slate-500">AI score</p>
                <p className="text-3xl font-black text-slate-900">{report.score.toFixed(1)}<span className="text-base text-slate-400">/10</span> <span className="text-base font-bold text-emerald-700 ml-2">{report.recommendationLabel}</span></p>
              </div>
              <Link href={`/evaluation/${startup.startup_id}`} className="inline-flex items-center gap-2 bg-slate-900 text-white text-sm font-bold rounded-lg px-4 py-2.5 hover:bg-slate-700">
                Open full report <ArrowRight className="w-4 h-4" />
              </Link>
            </div>
            <ComplianceBadge verified={startup.verification?.mca_verified} flags={report.complianceFlags} />
            <div className="text-sm text-slate-700 leading-relaxed markdown-content max-h-72 overflow-y-auto border border-slate-100 rounded-lg p-4">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{report.executiveSummary}</ReactMarkdown>
            </div>

            <div className="border-t border-slate-200 pt-5">
              <p className="text-sm font-bold text-slate-900 mb-1">Publish to the DAO</p>
              <p className="text-xs text-slate-500 mb-3">Creates an on-chain proposal on Sepolia so token holders can vote. Requires MetaMask.</p>
              {isConnected ? (
                <button onClick={confirmOnChain} disabled={isConfirmingInWallet || isMining || toEth(fundingAmount, fundingUnit) <= 0 || toEth(valuation, valuationUnit) <= 0} className="w-full h-11 bg-[#0284c7] text-white font-bold rounded-lg disabled:opacity-60 flex items-center justify-center gap-2">
                  {isConfirmingInWallet ? 'Confirm in wallet…' : isMining ? 'Waiting for confirmation…' : 'Submit proposal on-chain'}
                </button>
              ) : (
                <p className="text-sm text-slate-600 flex items-center gap-2 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2.5">
                  <Wallet className="w-4 h-4 text-slate-500" /> Connect a wallet (top right) to publish this proposal on-chain.
                </p>
              )}
              {isConnected && !ethPrice && (fundingUnit === 'usd' || valuationUnit === 'usd') && (
                <p className="text-xs text-amber-700 mt-2">Live ETH price is unavailable right now, so USD amounts can't be converted to ETH for the on-chain proposal.</p>
              )}
              {writeError && <p className="text-xs text-rose-600 mt-2">{writeError.message.split('\n')[0]}</p>}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
