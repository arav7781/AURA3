'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { Loader2, ShieldAlert, ShieldCheck } from 'lucide-react'
import { apiJson, API_BASE, type StartupSummary } from '@/lib/api'

const statusChip: Record<StartupSummary['analysis_status'], string> = {
  complete: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  processing: 'bg-sky-50 text-sky-700 border-sky-200',
  failed: 'bg-rose-50 text-rose-700 border-rose-200',
  not_started: 'bg-slate-50 text-slate-600 border-slate-200',
}

export function EvaluationsList({ founderAddress }: { founderAddress?: string }) {
  const [startups, setStartups] = useState<StartupSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const load = () =>
      apiJson<StartupSummary[]>('/startups')
        .then(data => { if (!cancelled) { setStartups(data); setError(null) } })
        .catch(() => { if (!cancelled) setError(`Cannot reach the AURA-3 backend at ${API_BASE}.`) })
    load()
    const timer = setInterval(load, 8000)
    return () => { cancelled = true; clearInterval(timer) }
  }, [])

  if (error) return <p className="p-6 text-sm text-rose-600">{error}</p>
  if (!startups) return <div className="p-10 flex justify-center"><Loader2 className="w-5 h-5 animate-spin text-slate-400" /></div>

  const rows = founderAddress
    ? startups.filter(s => s.founder_address?.toLowerCase() === founderAddress.toLowerCase())
    : startups
  if (rows.length === 0) {
    return <p className="p-6 text-sm text-slate-500">No startups evaluated yet. Founders can submit a pitch deck from the Founder Portal.</p>
  }

  return (
    <ul className="divide-y divide-slate-100">
      {rows.map(s => (
        <li key={s.startup_id}>
          <Link href={`/evaluation/${s.startup_id}`} className="flex items-center gap-4 px-5 py-4 hover:bg-slate-50 transition-colors">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <p className="font-bold text-slate-900 truncate">{s.name}</p>
                {s.verification?.mca_verified && s.compliance_flags.length === 0
                  ? <ShieldCheck className="w-4 h-4 text-emerald-600 shrink-0" aria-label="MCA verified" />
                  : <ShieldAlert className="w-4 h-4 text-amber-500 shrink-0" aria-label="Compliance flags" />}
              </div>
              <p className="text-xs text-slate-500 truncate">{s.domain}{s.stage ? ` · ${s.stage}` : ''}{s.funding_required ? ` · ask ${s.funding_required}` : ''}</p>
            </div>
            {s.score != null && (
              <div className="text-right">
                <p className="text-lg font-black text-slate-900 leading-none">{s.score.toFixed(1)}</p>
                <p className="text-[10px] font-mono text-slate-500">{s.recommendation_label}</p>
              </div>
            )}
            <span className={`text-[10px] font-mono font-bold uppercase px-2 py-1 rounded border ${statusChip[s.analysis_status]}`}>
              {s.analysis_status.replace('_', ' ')}
            </span>
          </Link>
        </li>
      ))}
    </ul>
  )
}
