'use client'

import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Bot, Loader2, MessageSquare, Send, X } from 'lucide-react'
import { apiJson } from '@/lib/api'

interface Turn {
  role: 'user' | 'assistant'
  content: string
}

const SUGGESTIONS = [
  'What are the biggest risks?',
  'How does it compare with competitors?',
  'Is the valuation justified by traction?',
]

// Floating chat that answers questions about one startup from its documents and AI evaluation.
export function VentureAnalystChat({ startupId, startupName }: { startupId: string; startupName: string }) {
  const [open, setOpen] = useState(false)
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
      setTurns(prev => [...prev, { role: 'assistant', content: `⚠️ ${err instanceof Error ? err.message : 'Could not reach the analyst.'}` }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col items-end">
      {open && (
        <div className="mb-4 w-[360px] sm:w-[420px] bg-white border border-slate-200 rounded-2xl shadow-2xl flex flex-col overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <Bot className="w-5 h-5 text-[#0284c7]" />
              <div>
                <p className="text-sm font-bold text-slate-900 leading-none">Venture Analyst</p>
                <p className="text-[11px] text-slate-500 mt-1">Ask anything about {startupName}</p>
              </div>
            </div>
            <button onClick={() => setOpen(false)} className="text-slate-400 hover:text-slate-700" aria-label="Close chat">
              <X className="w-4 h-4" />
            </button>
          </div>
          <div className="h-[380px] overflow-y-auto p-4 flex flex-col gap-3">
            {turns.length === 0 && (
              <div className="m-auto text-center">
                <p className="text-sm text-slate-500 mb-3">Answers come from the pitch deck and the AI evaluation.</p>
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
                <Loader2 className="w-3.5 h-3.5 animate-spin" /> Analysing documents…
              </div>
            )}
            <div ref={endRef} />
          </div>
          <form onSubmit={e => { e.preventDefault(); ask(input) }} className="p-3 border-t border-slate-200 flex gap-2">
            <input
              value={input}
              onChange={e => setInput(e.target.value)}
              placeholder="Ask about market, team, risks…"
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
        className="w-14 h-14 rounded-full bg-[#0284c7] text-white shadow-lg flex items-center justify-center hover:scale-105 transition-transform"
        aria-label="Chat with the Venture Analyst"
      >
        {open ? <X className="w-6 h-6" /> : <MessageSquare className="w-6 h-6" />}
      </button>
    </div>
  )
}
