'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import { ArrowLeft, Download, FileText, Loader2, RefreshCw, Sparkles } from 'lucide-react'
import { EvaluationReport, ComplianceBadge } from '@/components/EvaluationReport'
import { VentureAnalystChat } from '@/components/VentureAnalystChat'
import { AgentProgress } from '@/components/AgentProgress'
import { apiJson, downloadReportPdf, type AnalysisStatus, type StartupSummary } from '@/lib/api'

export default function EvaluationPage() {
  const params = useParams()
  const startupId = typeof params.id === 'string' ? params.id : params.id?.[0] || ''
  const [startup, setStartup] = useState<StartupSummary | null>(null)
  const [status, setStatus] = useState<AnalysisStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [downloading, setDownloading] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [chatOpen, setChatOpen] = useState(false)

  const load = useCallback(async () => {
    try {
      const data = await apiJson<AnalysisStatus & { startup: StartupSummary }>(`/api/startups/${startupId}/analysis`)
      setStartup(data.startup)
      setStatus(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load this evaluation')
    }
  }, [startupId])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    if (status?.status !== 'processing') return
    const timer = setInterval(load, 3000)
    return () => clearInterval(timer)
  }, [status?.status, load])

  const rerun = async () => {
    setRefreshing(true)
    setActionError(null)
    try {
      await apiJson(`/api/startups/${startupId}/analyze`, { method: 'POST' })
      await load()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Could not refresh the research')
    } finally {
      setRefreshing(false)
    }
  }

  const download = async () => {
    if (!startup) return
    setDownloading(true)
    setActionError(null)
    try {
      await downloadReportPdf(startupId, `AURA3_${startup.name.replace(/\s+/g, '_')}_Report.pdf`)
      await load()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Download failed')
      await load()
    } finally {
      setDownloading(false)
    }
  }

  if (error) {
    return (
      <div className="max-w-5xl mx-auto px-6 py-16 text-center">
        <p className="text-rose-600 mb-4">{error}</p>
        <Link href="/evaluations" className="text-[#0284c7] hover:underline">Back to evaluations</Link>
      </div>
    )
  }
  if (!startup || !status) {
    return <div className="flex justify-center py-24"><Loader2 className="w-6 h-6 animate-spin text-slate-400" /></div>
  }

  return (
    <div className="max-w-6xl mx-auto px-6 py-10">
      <Link href="/evaluations" className="inline-flex items-center gap-2 text-xs font-mono uppercase tracking-widest text-slate-500 hover:text-[#0284c7] mb-6">
        <ArrowLeft className="w-3.5 h-3.5" /> All evaluations
      </Link>

      <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-6 mb-8">
        <div>
          <p className="text-[11px] font-mono uppercase tracking-widest text-[#0284c7] mb-2">{startup.domain}{startup.stage ? ` · ${startup.stage}` : ''}</p>
          <h1 className="text-4xl font-black text-slate-900 tracking-tight">{startup.name}</h1>
          <p className="text-slate-600 mt-2 max-w-3xl">{startup.description}</p>
          <p className="text-sm text-slate-500 mt-2"><span className="font-semibold text-slate-700">Team:</span> {startup.team}</p>
          {startup.documents.length > 0 && (
            <p className="text-xs text-slate-500 mt-2 flex items-center gap-1.5">
              <FileText className="w-3.5 h-3.5" /> {startup.documents.map(d => `${d.name} (${d.chunks} chunks)`).join(', ')}
            </p>
          )}
        </div>
        <div className="flex flex-col gap-3 min-w-[260px]">
          <ComplianceBadge verified={startup.verification?.mca_verified} flags={startup.compliance_flags} />
          {startup.verification?.cin && (
            <p className="text-[11px] font-mono text-slate-500">
              CIN {startup.verification.cin}{startup.verification.company_name ? ` · ${startup.verification.company_name}` : ''}
              {startup.verification.source === 'sandbox' ? ' · sandbox registry' : ''}
            </p>
          )}
          {status.status === 'complete' && (
            <>
            <button onClick={download} disabled={downloading || refreshing} className="inline-flex items-center justify-center gap-2 bg-[#0284c7] text-white font-bold text-sm rounded-lg px-4 py-2.5 hover:brightness-110 disabled:opacity-60">
              {downloading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
              {downloading ? (status.analysis?.evidenceVersion ? 'Building PDF…' : 'Researching & building PDF…') : 'Download PDF report'}
            </button>
            <button onClick={rerun} disabled={refreshing || downloading} className="inline-flex items-center justify-center gap-2 border border-slate-200 bg-white text-slate-700 font-bold text-sm rounded-lg px-4 py-2.5 hover:bg-slate-50 disabled:opacity-60">
              {refreshing ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
              {refreshing ? 'Starting research…' : 'Refresh research'}
            </button>
            <p className="text-[11px] text-slate-500 max-w-[280px]">PDF uses the displayed research snapshot. Refresh research to search again and update the report.</p>
            </>
          )}
        </div>
      </div>

      {actionError && <p role="alert" className="mb-4 text-sm text-rose-600">{actionError}</p>}
      {status.status === 'processing' && <AgentProgress stage={status.stage} />}
      {status.status === 'complete' && status.analysis && <EvaluationReport report={status.analysis} showCompliance={false} />}
      {status.status === 'complete' && status.analysis && (
        <div className="mt-6 rounded-xl border border-sky-200 bg-gradient-to-r from-sky-50 to-white p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 rounded-full bg-gradient-to-r from-[#0284c7] to-[#0369a1] flex items-center justify-center shrink-0">
              <Sparkles className="w-5 h-5 text-white" />
            </div>
            <div>
              <p className="text-sm font-bold text-slate-900">Want to dig deeper into this evaluation?</p>
              <p className="text-sm text-slate-600">FinScope AI knows {startup.name}&apos;s scores, risks and market context — ask it anything before you invest.</p>
            </div>
          </div>
          <button
            onClick={() => setChatOpen(true)}
            className="inline-flex items-center justify-center gap-2 bg-gradient-to-r from-[#0284c7] to-[#0369a1] text-white font-bold text-sm rounded-lg px-4 py-2.5 hover:brightness-110 whitespace-nowrap"
          >
            <Sparkles className="w-4 h-4" /> Ask more to FinScope AI
          </button>
        </div>
      )}
      {(status.status === 'failed' || status.status === 'not_started') && (
        <div className="bg-white border border-slate-200 rounded-xl p-8 text-center">
          <p className="text-slate-700 mb-1">{status.status === 'failed' ? 'The evaluation did not finish.' : 'This startup has not been evaluated yet.'}</p>
          {status.error && <p className="text-sm text-rose-600 mb-4">{status.error}</p>}
          <button onClick={rerun} disabled={refreshing} className="inline-flex items-center gap-2 bg-[#0284c7] text-white font-bold text-sm rounded-lg px-4 py-2.5 mt-2 disabled:opacity-60">
            <RefreshCw className="w-4 h-4" /> Run AI evaluation
          </button>
        </div>
      )}

      <VentureAnalystChat startupId={startupId} startupName={startup.name} open={chatOpen} onOpenChange={setChatOpen} />
    </div>
  )
}
