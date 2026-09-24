'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import { ArrowLeft, Download, FileText, Loader2, RefreshCw } from 'lucide-react'
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
    await apiJson(`/api/startups/${startupId}/analyze`, { method: 'POST' })
    load()
  }

  const download = async () => {
    if (!startup) return
    setDownloading(true)
    try {
      await downloadReportPdf(startupId, `AURA3_${startup.name.replace(/\s+/g, '_')}_Report.pdf`)
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Download failed')
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
            <button onClick={download} disabled={downloading} className="inline-flex items-center justify-center gap-2 bg-[#0284c7] text-white font-bold text-sm rounded-lg px-4 py-2.5 hover:brightness-110 disabled:opacity-60">
              {downloading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
              {downloading ? 'Building PDF…' : 'Download PDF report'}
            </button>
          )}
        </div>
      </div>

      {status.status === 'processing' && <AgentProgress stage={status.stage} />}
      {status.status === 'complete' && status.analysis && <EvaluationReport report={status.analysis} showCompliance={false} />}
      {(status.status === 'failed' || status.status === 'not_started') && (
        <div className="bg-white border border-slate-200 rounded-xl p-8 text-center">
          <p className="text-slate-700 mb-1">{status.status === 'failed' ? 'The evaluation did not finish.' : 'This startup has not been evaluated yet.'}</p>
          {status.error && <p className="text-sm text-rose-600 mb-4">{status.error}</p>}
          <button onClick={rerun} className="inline-flex items-center gap-2 bg-[#0284c7] text-white font-bold text-sm rounded-lg px-4 py-2.5 mt-2">
            <RefreshCw className="w-4 h-4" /> Run AI evaluation
          </button>
        </div>
      )}

      <VentureAnalystChat startupId={startupId} startupName={startup.name} />
    </div>
  )
}
