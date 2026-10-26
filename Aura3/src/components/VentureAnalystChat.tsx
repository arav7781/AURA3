'use client'

import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Loader2, Send, Sparkles, X } from 'lucide-react'
import { apiJson } from '@/lib/api'

interface Turn {
  role: 'user' | 'assistant'
  content: string
}

const SUGGESTIONS = [
  'What are the biggest risks in this evaluation?',
  'How does the AI score break down by category?',
  'Is the valuation justified by the traction and market size?',
  'What should I ask the founders before investing?',
]

interface VentureAnalystChatProps {
  startupId: string
  startupName: string
  /** Optional controlled open state so an external CTA can launch the chat. */
  open?: boolean
  onOpenChange?: (open: boolean) => void
}

// Floating "FinScope AI" chat that answers investor questions using the startup's
// documents and its AI evaluation context (served from /chat/{startupId}).
export function VentureAnalystChat({ startupId, startupName, open: controlledOpen, onOpenChange }: VentureAnalystChatProps) {
  const [internalOpen, setInternalOpen] = useState(false)
  const open = controlledOpen ?? internalOpen
  const setOpen = (next: boolean) => {
    if (onOpenChange) onOpenChange(next)
    if (controlledOpen === undefined) setInternalOpen(next)
  }

  const [turns, setTurns] = useState<Turn[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [turns, loading])

  const ask = async (question: string) => {
    const q = question.trim()
    if (!q || loading) return
    const history = turns
    setTurns([...history, { role: 'user', content: q }])
    setInput('')
    setLoading(true)
    try {
      const data = await apiJson<{ answer: string }>(`/chat/${startupId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q, history }),
      })
      setTurns(prev => [...prev, { role: 'assistant', content: data.answer }])
    } catch (err) {
      setTurns(prev => [...prev, { role: 'assistant', content: `⚠️ ${err instanceof Error ? err.message : 'Could not reach FinScope AI.'}` }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col items-end">
      {open && (
        <div className="mb-4 w-[360px] sm:w-[420px] bg-white border border-slate-200 rounded-2xl shadow-2xl flex flex-col overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-200 bg-gradient-to-r from-[#0284c7] to-[#0369a1] flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <Sparkles className="w-5 h-5 text-white" />
              <div>
                <p className="text-sm font-bold text-white leading-none">FinScope AI</p>
                <p className="text-[11px] text-sky-100 mt-1">Ask more about {startupName}</p>
              </div>
            </div>
            <button onClick={() => setOpen(false)} className="text-sky-100 hover:text-white" aria-label="Close chat">
              <X className="w-4 h-4" />
            </button>
          </div>
          <div className="h-[380px] overflow-y-auto p-4 flex flex-col gap-3">
            {turns.length === 0 && (
              <div className="m-auto text-center">
                <p className="text-sm text-slate-500 mb-3">FinScope AI answers from the pitch deck and this startup&apos;s AI evaluation.</p>
                <div className="flex flex-col gap-2">
                  {SUGGESTIONS.map(s => (
                    <button key={s} onClick={() => ask(s)} className="text-xs text-left px-3 py-2 border border-slate-200 rounded-lg hover:border-[#0284c7] hover:text-[#0284c7] text-slate-600">
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {turns.map((t, i) => (
              <div key={i} className={`flex ${t.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 text-[13px] leading-relaxed ${t.role === 'user' ? 'bg-[#0284c7] text-white' : 'bg-slate-100 text-slate-800 markdown-content'}`}>
                  {t.role === 'assistant' ? <ReactMarkdown remarkPlugins={[remarkGfm]}>{t.content}</ReactMarkdown> : t.content}
                </div>
              </div>
            ))}
            {loading && (
              <div className="flex items-center gap-2 text-xs text-slate-500">
                <Loader2 className="w-3.5 h-3.5 animate-spin" /> FinScope AI is analysing the evaluation…
              </div>
            )}
            <div ref={endRef} />
          </div>
          <form onSubmit={e => { e.preventDefault(); ask(input) }} className="p-3 border-t border-slate-200 flex gap-2">
            <input
              value={input}
              onChange={e => setInput(e.target.value)}
              placeholder="Ask about market, team, risks, score…"
              className="flex-1 border border-slate-200 rounded-lg px-3 py-2 text-sm outline-none focus:border-[#0284c7]"
              disabled={loading}
            />
            <button type="submit" disabled={loading || !input.trim()} className="bg-[#0284c7] text-white rounded-lg px-3 disabled:opacity-50" aria-label="Send">
              <Send className="w-4 h-4" />
            </button>
          </form>
        </div>
      )}
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 h-14 rounded-full bg-gradient-to-r from-[#0284c7] to-[#0369a1] text-white shadow-lg px-5 hover:scale-105 transition-transform"
        aria-label="Ask more to FinScope AI"
      >
        {open ? <X className="w-6 h-6" /> : <Sparkles className="w-6 h-6" />}
        {!open && <span className="text-sm font-bold whitespace-nowrap">Ask FinScope AI</span>}
      </button>
    </div>
  )
}
