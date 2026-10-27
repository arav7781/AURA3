'use client'

import { Suspense, useEffect, useRef, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useQueryClient } from '@tanstack/react-query'
import { ArrowUp, FileText, Loader2, MessageSquarePlus, Paperclip, Square, Trash2, X } from 'lucide-react'
import { clsx } from 'clsx'
import { RequireRole } from '@/components/auth/RequireRole'
import { BrandMark } from '@/components/Navbar'
import { MessageView } from '@/components/copilot/MessageView'
import { useAuth } from '@/context/AuthContext'
import { api, errorMessage } from '@/lib/api/client'
import { useStartup } from '@/lib/api/hooks'
import { attachFile, useRun, useThread, useThreads, type Thread } from '@/lib/copilot'
import { useJob, type JobState } from '@/lib/useJob'

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
const REVIEW_PROMPT = 'Review my attached deck slide by slide: what works, what an investor will question, and exactly what to change.'
const ACCEPT = '.pdf,.pptx,.ppt,.key,.odp,.docx,.png,.jpg,.jpeg,.webp,.tif,.tiff,.heic'

/** A file attached to the next message: uploaded, then read by TitanOCR before it can be sent. */
interface Pending {
  key: string
  name: string
  documentId?: string
  jobId?: string | null
  status: 'uploading' | 'reading' | 'ready' | 'failed'
  pages?: number | null
  stage?: string | null
  error?: string
}

function PendingChip({ item, onFinish, onRemove }: { item: Pending; onFinish: (key: string, state: JobState) => void; onRemove: (key: string) => void }) {
  const job = useJob(item.status === 'reading' ? item.jobId : null, state => onFinish(item.key, state))
  const busy = item.status === 'uploading' || item.status === 'reading'
  const detail = item.status === 'uploading' ? 'Uploading…'
    : item.status === 'reading' ? (job.message ?? 'TitanOCR is reading it…')
    : item.status === 'failed' ? item.error ?? 'Could not read this file'
    : `${item.pages ?? '?'} pages read · private to you`
  return (
    <div className={clsx('flex w-full max-w-sm items-center gap-2.5 rounded-xl border px-3 py-2',
      item.status === 'failed' ? 'border-rose-200 bg-rose-50' : 'border-line bg-paper-2')}>
      {busy ? <Loader2 className="h-4 w-4 shrink-0 animate-spin text-jade-600" /> : <FileText className={clsx('h-4 w-4 shrink-0', item.status === 'failed' ? 'text-rose-600' : 'text-jade-600')} />}
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-semibold text-ink">{item.name}</span>
        <span className="block truncate font-mono text-[0.62rem] text-ink-3">{detail}</span>
        {item.status === 'reading' && (
          <span className="mt-1 block h-[3px] overflow-hidden rounded-full bg-black/5">
            <span className="block h-full rounded-full bg-jade-500 transition-[width] duration-500" style={{ width: `${Math.max(6, job.pct)}%` }} />
          </span>
        )}
      </span>
      <button type="button" onClick={() => onRemove(item.key)} aria-label={`Remove ${item.name}`} className="rounded-md p-1 text-ink-3 hover:bg-black/5 hover:text-ink">
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  )
}

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
  const picker = useRef<HTMLInputElement>(null)
  const [files, setFiles] = useState<Pending[]>([])
  const founder = me?.user.role === 'startup'

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
    setFiles([])
    router.replace(id ? `/copilot?thread=${id}` : '/copilot')
  }

  const ensureThread = async () => {
    if (activeId) return activeId
    const created = await api<Thread>('/api/copilot/threads', { method: 'POST', body: { startup: focusSlug ?? undefined } })
    followed.current = null
    setActiveId(created.id)
    router.replace(`/copilot?thread=${created.id}`)
    return created.id
  }

  const patchFile = (key: string, change: Partial<Pending>) => setFiles(list => list.map(f => (f.key === key ? { ...f, ...change } : f)))

  const attach = async (picked: FileList | null | undefined) => {
    if (!picked?.length) return
    setError(null)
    for (const file of Array.from(picked).slice(0, 3)) {
      const key = `${file.name}-${file.size}-${file.lastModified}`
      if (files.some(f => f.key === key)) continue
      setFiles(list => [...list, { key, name: file.name, status: 'uploading' }])
      try {
        const thread = await ensureThread()
        const out = await attachFile(thread, file)
        const ready = out.document.status === 'ready'
        patchFile(key, {
          documentId: out.document_id, jobId: out.job_id, name: out.document.filename,
          status: ready ? 'ready' : out.document.status === 'failed' ? 'failed' : 'reading',
          pages: out.document.page_count, error: out.document.error ?? undefined,
        })
      } catch (err) {
        patchFile(key, { status: 'failed', error: errorMessage(err) })
      }
    }
    if (picker.current) picker.current.value = ''
  }

  const finishReading = async (key: string, state: JobState) => {
    const item = files.find(f => f.key === key)
    if (state.status === 'failed' || !item?.documentId) {
      patchFile(key, { status: 'failed', error: state.error ?? 'TitanOCR could not read this file' })
      return
    }
    const doc = await api<{ status: string; page_count: number | null; error: string | null }>(`/api/documents/${item.documentId}`).catch(() => null)
    patchFile(key, doc?.status === 'ready' ? { status: 'ready', pages: doc.page_count } : { status: 'failed', error: doc?.error ?? 'TitanOCR could not read this file' })
  }

  const ready = files.filter(f => f.status === 'ready' && f.documentId)
  const reading = files.some(f => f.status === 'uploading' || f.status === 'reading')

  const send = async (text: string) => {
    const content = text.trim() || (ready.length ? REVIEW_PROMPT : '')
    if (!content || run.running || reading) return
    setError(null)
    const sending = files
    try {
      const id = await ensureThread()
      setDraft('')
      setFiles([])
      await run.send(id, content, ready.map(f => f.documentId!))
      followed.current = 'sent'
    } catch (err) {
      setError(errorMessage(err))
      setDraft(text)
      setFiles(sending)
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
                {founder
                  ? 'The copilot reads your deck and evaluation, compares you with startups in your domain, checks the web and cites every slide it uses. Attach a new draft and it reviews it slide by slide.'
                  : 'The copilot searches startups, opens the documents they submitted, reads exact slides, checks the web and cites every page it uses.'}
              </p>
              {founder && (
                <button type="button" onClick={() => picker.current?.click()}
                        className="mt-6 inline-flex items-center gap-2 rounded-xl border border-jade-600/30 bg-jade-50 px-4 py-2.5 text-sm font-semibold text-jade-700 hover:border-jade-600/60">
                  <Paperclip className="h-4 w-4" /> Attach your current pitch deck
                  <span className="font-mono text-[0.62rem] font-normal text-jade-700/70">PDF · PPTX · images</span>
                </button>
              )}
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

        <div className="border-t border-slate-200 bg-white px-4 py-3 sm:px-8"
             onDragOver={founder ? e => e.preventDefault() : undefined}
             onDrop={founder ? e => { e.preventDefault(); attach(e.dataTransfer.files) } : undefined}>
          {files.length > 0 && (
            <div className="mx-auto mb-2 flex max-w-3xl flex-wrap gap-2">
              {files.map(f => <PendingChip key={f.key} item={f} onFinish={finishReading} onRemove={key => setFiles(list => list.filter(x => x.key !== key))} />)}
            </div>
          )}
          <form className="mx-auto flex max-w-3xl items-end gap-2" onSubmit={e => { e.preventDefault(); send(draft) }}>
            {founder && (
              <>
                <input ref={picker} type="file" accept={ACCEPT} multiple hidden onChange={e => attach(e.target.files)} />
                <button type="button" onClick={() => picker.current?.click()} disabled={run.running} aria-label="Attach a file" title="Attach your pitch deck (PDF, PPTX or images)"
                        className="grid h-12 w-12 shrink-0 place-items-center rounded-full border border-slate-300 text-slate-600 hover:border-jade-600 hover:text-jade-700 disabled:opacity-40">
                  <Paperclip className="h-5 w-5" />
                </button>
              </>
            )}
            <textarea
              value={draft}
              onChange={e => setDraft(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(draft) } }}
              rows={1}
              maxLength={4000}
              placeholder={ready.length ? 'Ask about the attached file, or send to get a slide-by-slide review…'
                : focus.data ? `Ask about ${focus.data.name}…`
                : founder ? 'Ask about your deck, your evaluation or your market…' : 'Ask about startups, their documents, scores or markets…'}
              className="max-h-40 min-h-[48px] flex-1 resize-none rounded-2xl border border-slate-300 px-4 py-3 text-[0.95rem] focus:border-jade-600 focus:outline-none focus:ring-2 focus:ring-jade-600/20"
            />
            {run.running ? (
              <button type="button" onClick={run.stop} aria-label="Stop" className="grid h-12 w-12 place-items-center rounded-full bg-slate-900 text-white hover:bg-black">
                <Square className="h-4 w-4 fill-current" />
              </button>
            ) : (
              <button type="submit" disabled={(!draft.trim() && !ready.length) || reading} aria-label="Send" className="grid h-12 w-12 place-items-center rounded-full bg-jade-600 text-white hover:bg-jade-700 disabled:opacity-40">
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
