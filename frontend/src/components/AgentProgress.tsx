'use client'

import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { API_BASE } from '@/lib/api'

const STEPS = [
  'Analyst agent is planning research',
  'Researching the market and reading documents',
  'Grading research quality',
  'Scoring the startup and sizing the market',
  'Writing the 11-section investor report',
]

// Shows which LangGraph node is running, plus the live agent log stream from the backend.
export function AgentProgress({ stage }: { stage?: string | null }) {
  const [logs, setLogs] = useState<string[]>([])

  useEffect(() => {
    let socket: { disconnect: () => void } | null = null
    import('socket.io-client').then(({ io }) => {
      const s = io(API_BASE)
      s.on('log_stream', (data: { message?: string }) => {
        if (data?.message?.startsWith('Evaluation')) setLogs(prev => [...prev, data.message!].slice(-12))
      })
      socket = s
    })
    return () => socket?.disconnect()
  }, [])

  const activeIndex = stage?.startsWith('Refining') ? 0 : STEPS.findIndex(step => step === stage)

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
      <p className="text-[11px] font-mono uppercase tracking-widest text-[#0284c7] mb-4">Multi-agent evaluation running</p>
      <ol className="space-y-2.5 mb-5">
        {STEPS.map((step, i) => {
          const done = activeIndex > i
          const active = activeIndex === i
          return (
            <li key={step} className={`flex items-center gap-3 text-sm ${done ? 'text-emerald-700' : active ? 'text-slate-900 font-semibold' : 'text-slate-400'}`}>
              {active ? <Loader2 className="w-4 h-4 animate-spin text-[#0284c7]" /> : <span className={`w-4 h-4 rounded-full border-2 ${done ? 'bg-emerald-500 border-emerald-500' : 'border-slate-300'}`} />}
              {step}
            </li>
          )
        })}
        {stage?.startsWith('Refining') && <li className="text-sm text-amber-700 pl-7">{stage}</li>}
      </ol>
      {logs.length > 0 && (
        <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 font-mono text-[11px] text-slate-700 max-h-48 overflow-y-auto space-y-1">
          {logs.map((line, i) => <p key={i} className="break-words"><span className="text-[#0284c7] mr-1.5">$</span>{line}</p>)}
        </div>
      )}
    </div>
  )
}
