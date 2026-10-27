'use client'

import { Suspense, useEffect, useRef, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useQueryClient } from '@tanstack/react-query'
import { ArrowUp, MessageSquarePlus, Square, Trash2 } from 'lucide-react'
import { clsx } from 'clsx'
import { RequireRole } from '@/components/auth/RequireRole'
import { BrandMark } from '@/components/Navbar'
import { MessageView } from '@/components/copilot/MessageView'
import { useAuth } from '@/context/AuthContext'
import { api, errorMessage } from '@/lib/api/client'
import { useStartup } from '@/lib/api/hooks'
import { useRun, useThread, useThreads, type Thread } from '@/lib/copilot'

export default function CopilotPage() {
  return (
    <RequireRole>
      <Suspense>
        <Copilot />
      </Suspense>
    </RequireRole>
  )
}

const INVESTOR_IDEAS = [
  'Which agritech startups have the strongest traction?',
  'What documents has KrishiMitra AI submitted, and is its market size verified?',
  'Compare OpsPilot, Kirana Cloud and Nyaya AI',
  'Which startups have registry or compliance red flags?',
  'Is NeoCredit Score’s deck trustworthy?',
]
const FOUNDER_IDEAS = [
  'What are the weakest parts of my pitch deck?',
  'Explain my AI evaluation and how to improve my score',
  'How does my traction compare with other startups in my domain?',
  'What market data should my market slide cite?',
]

function Copilot() {
  const router = useRouter()
  const params = useSearchParams()
  const client = useQueryClient()
  const { me } = useAuth()
  const threads = useThreads()
  const [activeId, setActiveId] = useState<string | null>(params.get('thread'))
  const thread = useThread(activeId)
  const run = useRun(activeId)
  const [draft, setDraft] = useState(params.get('q') ?? '')
  const [error, setError] = useState<string | null>(null)
  const focusSlug = !activeId ? params.get('startup') : null
  const focus = useStartup(focusSlug ?? undefined)
  const scroller = useRef<HTMLDivElement>(null)
  const followed = useRef<string | null>(null)

  // Reattach to a run still going in this conversation (page reload, coming back to a tab).
  const activeRun = thread.data?.active_run_id ?? null
  useEffect(() => {
    if (activeRun && activeId && followed.current !== activeRun && !run.running) {
      followed.current = activeRun
      run.follow(activeRun, activeId)
    }
  }, [activeRun, activeId, run])

  const messages = [...(thread.data?.messages ?? []), ...(run.live ? [run.live] : [])]
  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: 'smooth' })
  }, [messages.length, run.live?.parts.length])

  const open = (id: string | null) => {
    setActiveId(id)
    setError(null)
    router.replace(id ? `/copilot?thread=${id}` : '/copilot')
  }

  const send = async (text: string) => {
    const content = text.trim()
    if (!content || run.running) return
    setError(null)
    try {
      let id = activeId
      if (!id) {
        const created = await api<Thread>('/api/copilot/threads', { method: 'POST', body: { startup: focusSlug ?? undefined } })
        id = created.id
        followed.current = null
        setActiveId(id)
        router.replace(`/copilot?thread=${id}`)
      }
      setDraft('')
      await run.send(id, content)
      followed.current = 'sent'
    } catch (err) {
      setError(errorMessage(err))
      setDraft(content)
    }
  }

  const remove = async (id: string) => {
    await api(`/api/copilot/threads/${id}`, { method: 'DELETE' }).catch(() => undefined)
    await client.invalidateQueries({ queryKey: ['copilot-threads'] })
    if (id === activeId) open(null)
  }

  const ideas = me?.user.role === 'startup' ? FOUNDER_IDEAS : INVESTOR_IDEAS
  const quota = me?.entitlements.quotas?.copilot

  return (
    <div className="mx-auto grid h-[calc(100svh-3.5rem)] max-w-7xl grid-cols-1 md:grid-cols-[17rem_minmax(0,1fr)]">
      <aside className="hidden flex-col border-r border-slate-200 md:flex">
        <div className="p-3">
          <button onClick={() => open(null)} className="flex w-full items-center justify-center gap-2 rounded-xl bg-ink px-3 py-2.5 text-sm font-semibold text-white hover:bg-black">
            <MessageSquarePlus className="h-4 w-4" /> New conversation
          </button>
        </div>
        <ul className="flex-1 space-y-0.5 overflow-y-auto px-2 pb-3">
          {(threads.data?.items ?? []).map(t => (
            <li key={t.id} className="group flex items-center">
              <button onClick={() => open(t.id)}
                      className={clsx('min-w-0 flex-1 truncate rounded-lg px-3 py-2 text-left text-sm', t.id === activeId ? 'bg-slate-100 font-semibold text-slate-900' : 'text-slate-600 hover:bg-slate-50')}>
                {t.title}
              </button>
              <button onClick={() => remove(t.id)} aria-label={`Delete ${t.title}`} className="p-1.5 text-slate-300 opacity-0 hover:text-rose-600 group-hover:opacity-100">
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </li>
          ))}
        </ul>
        {quota && quota.limit != null && (
          <p className="border-t border-slate-200 px-4 py-3 font-mono text-[0.65rem] text-slate-500">{quota.used} of {quota.limit} questions used today</p>
        )}
      </aside>

      <section className="flex min-h-0 flex-col">
        <div ref={scroller} className="flex-1 overflow-y-auto px-4 py-6 sm:px-8">
          {messages.length === 0 ? (
            <div className="mx-auto mt-[8vh] max-w-2xl text-center">
              <span className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-ink text-white"><BrandMark className="h-6 w-6" /></span>
              <h1 className="mt-5 font-display text-[clamp(1.9rem,3.5vw,2.6rem)] font-semibold leading-tight tracking-[-0.02em] text-ink">
                {focus.data ? `Ask about ${focus.data.name}` : me?.user.role === 'startup' ? 'Improve your pitch' : 'Ask about any startup'}
              </h1>
              <p className="mx-auto mt-2 max-w-lg text-slate-600">
                The copilot searches startups, opens the documents they submitted, reads exact slides, checks the web and cites
                every page it uses.
              </p>
              <div className="mt-7 flex flex-wrap justify-center gap-2">
                {(focus.data
                  ? [`What has ${focus.data.name} submitted?`, `What are the biggest risks in ${focus.data.name}?`, `Summarise ${focus.data.name}'s traction with citations`]
                  : ideas).map(idea => (
                  <button key={idea} onClick={() => send(idea)} className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm text-slate-700 hover:border-jade-600/50 hover:text-ink">
                    {idea}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="mx-auto max-w-3xl space-y-6">
              {messages.map(m => <MessageView key={m.id} message={m} />)}
            </div>
          )}
        </div>

        <div className="border-t border-slate-200 bg-white px-4 py-3 sm:px-8">
          <form className="mx-auto flex max-w-3xl items-end gap-2" onSubmit={e => { e.preventDefault(); send(draft) }}>
            <textarea
              value={draft}
              onChange={e => setDraft(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(draft) } }}
              rows={1}
              maxLength={4000}
              placeholder={focus.data ? `Ask about ${focus.data.name}…` : 'Ask about startups, their documents, scores or markets…'}
              className="max-h-40 min-h-[48px] flex-1 resize-none rounded-2xl border border-slate-300 px-4 py-3 text-[0.95rem] focus:border-jade-600 focus:outline-none focus:ring-2 focus:ring-jade-600/20"
            />
            {run.running ? (
              <button type="button" onClick={run.stop} aria-label="Stop" className="grid h-12 w-12 place-items-center rounded-full bg-slate-900 text-white hover:bg-black">
                <Square className="h-4 w-4 fill-current" />
              </button>
            ) : (
              <button type="submit" disabled={!draft.trim()} aria-label="Send" className="grid h-12 w-12 place-items-center rounded-full bg-jade-600 text-white hover:bg-jade-700 disabled:opacity-40">
                <ArrowUp className="h-5 w-5" />
              </button>
            )}
          </form>
          {error && <p className="mx-auto mt-2 max-w-3xl text-sm text-rose-700">{error}</p>}
          <p className="mx-auto mt-1.5 max-w-3xl text-center font-mono text-[0.62rem] text-slate-400">AI analysis from platform data and the web, with citations. Not investment advice.</p>
        </div>
      </section>
    </div>
  )
}
