'use client'

import { useRef, useState } from 'react'
import Link from 'next/link'
import { CheckCircle2, Circle, ExternalLink, FileUp, Loader2, Trash2, XCircle } from 'lucide-react'
import { clsx } from 'clsx'
import { RequireRole } from '@/components/auth/RequireRole'
import { Badge, Button, Card, ErrorNote, FlagBadges, RecommendationBadge, ScoreRing, Spinner, STAGE_LABELS } from '@/components/ui'
import { useAuth } from '@/context/AuthContext'
import { api, errorMessage } from '@/lib/api/client'
import { uploadDocument, useDocuments, useEvaluations, useRefreshStartup, useStartup } from '@/lib/api/hooks'
import type { DocumentOut, EvaluationOut, StartupDetail } from '@/lib/api/types'
import { useJob, type JobState } from '@/lib/useJob'

const DOMAINS = ['Agritech', 'Fintech', 'Healthtech', 'Edtech', 'Climate & Energy', 'B2B SaaS', 'Logistics & Mobility',
  'Cybersecurity', 'Consumer & D2C', 'Deeptech & AI', 'Proptech', 'Insurtech']
const INPUT = 'w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm'

export default function FounderPage() {
  return (
    <RequireRole role="startup">
      <FounderPortal />
    </RequireRole>
  )
}

function FounderPortal() {
  const { me } = useAuth()
  const startupId = me?.startup?.id
  const startup = useStartup(startupId)
  const documents = useDocuments(startupId)
  const evaluations = useEvaluations(startupId)
  if (!startupId || startup.isPending) return <Spinner label="Loading your startup" />
  if (startup.isError) return <div className="max-w-3xl mx-auto px-4 py-16"><ErrorNote error={startup.error} /></div>

  const s = startup.data
  const ready = (documents.data?.items ?? []).some(d => d.status === 'ready')
  const latest = evaluations.data?.items[0]
  const complete = (evaluations.data?.items ?? []).some(e => e.status === 'complete')
  const steps = [
    { done: !!(s.one_liner && s.description && s.legal_name), label: 'Company profile' },
    { done: ready, label: 'Pitch deck read by TitanOCR' },
    { done: !!s.mca?.cin, label: 'Registry check' },
    { done: complete, label: 'AI evaluation' },
    { done: s.status === 'published', label: 'Published to investors' },
  ]

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 py-10">
      <div className="mb-8 flex flex-col gap-4 border-b border-slate-200 pb-6 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-[11px] font-mono uppercase tracking-widest text-[#0284c7] mb-2">Founder portal</p>
          <h1 className="text-3xl font-black tracking-tight text-slate-900">{s.name}</h1>
          <p className="mt-1 text-slate-600">Upload your deck, get an evidence-backed AI evaluation, and publish to investors. Listing is free; AURA3 takes 2% of each released tranche.</p>
        </div>
        <Link href={`/startups/${s.slug}`} className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-bold text-slate-800 hover:bg-slate-50">
          View your page <ExternalLink className="w-4 h-4" />
        </Link>
      </div>

      <ol className="mb-8 grid gap-2 sm:grid-cols-5">
        {steps.map((step, i) => (
          <li key={step.label} className={clsx('flex items-center gap-2 rounded-lg border px-3 py-2 text-sm', step.done ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-slate-200 bg-white text-slate-600')}>
            {step.done ? <CheckCircle2 className="w-4 h-4 shrink-0" /> : <Circle className="w-4 h-4 shrink-0" />}
            <span><span className="font-mono text-xs">{i + 1}.</span> {step.label}</span>
          </li>
        ))}
      </ol>

      <div className="space-y-6">
        <ProfileForm startup={s} />
        <DeckSection startupId={s.id} documents={documents.data?.items ?? []} />
        <RegistrySection startup={s} />
        <EvaluationSection startup={s} latest={latest} canRun={ready} />
        <PublishSection startup={s} ready={ready && complete} />
      </div>
    </div>
  )
}

function ProfileForm({ startup: s }: { startup: StartupDetail }) {
  const refresh = useRefreshStartup()
  const [form, setForm] = useState({
    name: s.name, legal_name: s.legal_name ?? '', domain: s.domain, stage: s.stage, one_liner: s.one_liner,
    description: s.description, hq_city: s.hq_city ?? '', hq_state: s.hq_state ?? '',
    founded_year: s.founded_year ? String(s.founded_year) : '',
    ask_crore: s.ask_inr ? String(s.ask_inr / 1e7) : '', pre_crore: s.pre_money_inr ? String(s.pre_money_inr / 1e7) : '',
    team: (s.profile.team ?? []).map(m => `${m.name} | ${m.role}${m.background ? ` | ${m.background}` : ''}`).join('\n'),
  })
  const [state, setState] = useState<{ busy: boolean; error: string | null; saved: boolean }>({ busy: false, error: null, saved: false })
  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setForm(f => ({ ...f, [key]: e.target.value }))

  const save = async (event: React.FormEvent) => {
    event.preventDefault()
    setState({ busy: true, error: null, saved: false })
    const crore = (v: string) => (v.trim() ? Math.round(Number(v) * 1e7) : undefined)
    try {
      await api(`/api/startups/${s.id}`, {
        method: 'PATCH',
        body: {
          name: form.name, legal_name: form.legal_name || undefined, domain: form.domain, stage: form.stage,
          one_liner: form.one_liner, description: form.description, hq_city: form.hq_city || undefined,
          hq_state: form.hq_state || undefined, founded_year: form.founded_year ? Number(form.founded_year) : undefined,
          ask_inr: crore(form.ask_crore), pre_money_inr: crore(form.pre_crore),
          team: form.team.split('\n').map(line => line.split('|').map(p => p.trim())).filter(p => p[0])
            .map(([name, role = '', background = '']) => ({ name, role, background })),
        },
      })
      await refresh(s.id)
      setState({ busy: false, error: null, saved: true })
    } catch (err) {
      setState({ busy: false, error: errorMessage(err), saved: false })
    }
  }

  return (
    <Card title="1 · Company profile">
      <form onSubmit={save} className="grid gap-4 md:grid-cols-2">
        <label className="block"><span className="text-xs font-semibold text-slate-700">Startup name</span><input className={INPUT} value={form.name} onChange={set('name')} required maxLength={120} /></label>
        <label className="block"><span className="text-xs font-semibold text-slate-700">Registered legal name</span><input className={INPUT} value={form.legal_name} onChange={set('legal_name')} placeholder="Acme Technologies Private Limited" /></label>
        <label className="block"><span className="text-xs font-semibold text-slate-700">Domain</span>
          <select className={INPUT} value={form.domain} onChange={set('domain')}>{[...new Set([form.domain, ...DOMAINS])].map(d => <option key={d}>{d}</option>)}</select>
        </label>
        <label className="block"><span className="text-xs font-semibold text-slate-700">Stage</span>
          <select className={INPUT} value={form.stage} onChange={set('stage')}>{Object.entries(STAGE_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
        </label>
        <label className="block md:col-span-2"><span className="text-xs font-semibold text-slate-700">One-liner</span><input className={INPUT} value={form.one_liner} onChange={set('one_liner')} maxLength={240} /></label>
        <label className="block md:col-span-2"><span className="text-xs font-semibold text-slate-700">What you do, for whom, and your traction</span><textarea className={INPUT} rows={4} value={form.description} onChange={set('description')} maxLength={4000} /></label>
        <div className="grid grid-cols-3 gap-3 md:col-span-2">
          <label className="block"><span className="text-xs font-semibold text-slate-700">City</span><input className={INPUT} value={form.hq_city} onChange={set('hq_city')} /></label>
          <label className="block"><span className="text-xs font-semibold text-slate-700">State</span><input className={INPUT} value={form.hq_state} onChange={set('hq_state')} /></label>
          <label className="block"><span className="text-xs font-semibold text-slate-700">Founded</span><input className={INPUT} value={form.founded_year} onChange={set('founded_year')} inputMode="numeric" /></label>
        </div>
        <label className="block"><span className="text-xs font-semibold text-slate-700">Raising (₹ crore)</span><input className={INPUT} value={form.ask_crore} onChange={set('ask_crore')} inputMode="decimal" /></label>
        <label className="block"><span className="text-xs font-semibold text-slate-700">Pre-money valuation (₹ crore)</span><input className={INPUT} value={form.pre_crore} onChange={set('pre_crore')} inputMode="decimal" /></label>
        <label className="block md:col-span-2"><span className="text-xs font-semibold text-slate-700">Team: one per line, as name | role | background</span>
          <textarea className={clsx(INPUT, 'font-mono text-xs')} rows={4} value={form.team} onChange={set('team')} placeholder="Asha Rao | CEO | Ex-Flipkart supply chain lead" />
        </label>
        <div className="md:col-span-2 flex items-center justify-end gap-3">
          {state.error && <span className="text-sm text-rose-700">{state.error}</span>}
          {state.saved && <span className="text-sm text-emerald-700">Saved</span>}
          <Button busy={state.busy}>Save profile</Button>
        </div>
      </form>
    </Card>
  )
}

function JobProgress({ job, title }: { job: JobState; title: string }) {
  if (job.status === 'idle') return null
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
      <div className="flex items-center justify-between text-sm">
        <span className="font-semibold text-slate-800 inline-flex items-center gap-2">
          {job.status === 'running' && <Loader2 className="w-4 h-4 animate-spin text-[#0284c7]" />}
          {job.status === 'done' && <CheckCircle2 className="w-4 h-4 text-emerald-600" />}
          {job.status === 'failed' && <XCircle className="w-4 h-4 text-rose-600" />}
          {title}{job.stage ? ` · ${job.stage}` : ''}
        </span>
        <span className="font-mono text-slate-600">{job.pct}%</span>
      </div>
      <div className="mt-2 h-2 rounded-full bg-white"><div className="h-2 rounded-full bg-[#0284c7] transition-all" style={{ width: `${job.pct}%` }} /></div>
      {job.error && <p className="mt-2 text-sm text-rose-700">{job.error}</p>}
      {job.log.length > 0 && (
        <ul className="mt-3 max-h-40 overflow-y-auto space-y-0.5 font-mono text-[11px] text-slate-600">
          {job.log.map((line, i) => <li key={i}>[{String(line.pct).padStart(3)}%] {line.stage}: {line.message}</li>)}
        </ul>
      )}
    </div>
  )
}

function DeckSection({ startupId, documents }: { startupId: string; documents: DocumentOut[] }) {
  const refresh = useRefreshStartup()
  const input = useRef<HTMLInputElement>(null)
  const [jobId, setJobId] = useState<string | null>(documents.find(d => d.status === 'processing')?.job_id ?? null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const job = useJob(jobId, () => refresh(startupId))

  const upload = async (file: File | undefined) => {
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      const { job_id } = await uploadDocument(startupId, file)
      setJobId(job_id)
      await refresh(startupId)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
      if (input.current) input.current.value = ''
    }
  }
  const remove = async (doc: DocumentOut) => {
    try {
      await api(`/api/documents/${doc.id}`, { method: 'DELETE' })
      await refresh(startupId)
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  return (
    <Card title="2 · Pitch deck">
      <div
        onDragOver={e => e.preventDefault()}
        onDrop={e => { e.preventDefault(); upload(e.dataTransfer.files[0]) }}
        className="rounded-xl border-2 border-dashed border-slate-300 bg-slate-50/60 px-6 py-8 text-center"
      >
        <FileUp className="mx-auto w-6 h-6 text-[#0284c7]" />
        <p className="mt-2 text-sm text-slate-700">Drop a PDF, PPTX, DOCX or image here, or</p>
        <Button className="mt-3" busy={busy} onClick={() => input.current?.click()} type="button">Choose a file</Button>
        <input ref={input} type="file" className="hidden" accept=".pdf,.pptx,.docx,.png,.jpg,.jpeg,.webp,.tif,.tiff"
               onChange={e => upload(e.target.files?.[0])} />
        <p className="mt-2 text-xs text-slate-500">Up to 25 MB. TitanOCR reads every page (scans included), keeps the box behind each line, and checks for hidden instructions.</p>
      </div>
      {error && <p className="mt-3 text-sm text-rose-700">{error}</p>}
      <div className="mt-4"><JobProgress job={job} title="Processing deck" /></div>
      {documents.length > 0 && (
        <ul className="mt-4 divide-y divide-slate-100 rounded-lg border border-slate-200">
          {documents.map(doc => (
            <li key={doc.id} className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm">
              <span className="font-semibold text-slate-900 truncate max-w-[18rem]">{doc.filename}</span>
              <Badge tone={doc.status === 'ready' ? 'green' : doc.status === 'failed' ? 'red' : 'amber'}>{doc.status}</Badge>
              {doc.page_count != null && <span className="text-slate-500">{doc.page_count} pages</span>}
              {doc.ocr_ms != null && <span className="text-slate-500">{(doc.ocr_ms / 1000).toFixed(1)} s OCR</span>}
              <FlagBadges flags={doc.flags} />
              {doc.error && <span className="text-rose-700">{doc.error}</span>}
              <button onClick={() => remove(doc)} className="ml-auto text-slate-400 hover:text-rose-600" aria-label={`Delete ${doc.filename}`}><Trash2 className="w-4 h-4" /></button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

function RegistrySection({ startup: s }: { startup: StartupDetail }) {
  const refresh = useRefreshStartup()
  const [cin, setCin] = useState(s.cin ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const verify = async (event: React.FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api(`/api/startups/${s.id}/verify-mca`, { method: 'POST', body: { cin } })
      await refresh(s.id)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <Card title="3 · Registry check (MCA)">
      <form onSubmit={verify} className="flex flex-wrap gap-2">
        <input value={cin} onChange={e => setCin(e.target.value.toUpperCase())} placeholder="Corporate Identification Number, e.g. U62099MH2024PTC410567"
               className={clsx(INPUT, 'flex-1 min-w-[16rem] font-mono')} maxLength={32} />
        <Button busy={busy} disabled={cin.trim().length < 5}>Check registry</Button>
      </form>
      {error && <p className="mt-2 text-sm text-rose-700">{error}</p>}
      {s.mca?.cin && (
        <div className="mt-3 text-sm text-slate-700">
          <p><b>{s.mca.mca_verified ? 'Active' : s.mca.company_status ?? 'Not verified'}</b>{s.mca.company_name ? ` · registered as ${s.mca.company_name}` : ''}{s.mca.reason ? ` · ${s.mca.reason}` : ''}</p>
          <div className="mt-1"><FlagBadges flags={s.compliance_flags.filter(f => !f.startsWith('DECK_') && !f.startsWith('OCR_'))} /></div>
          <p className="mt-1 text-xs text-slate-500">Registry problems cap the AI recommendation: struck off → Pass; name mismatch or unverified → at most Hold.</p>
        </div>
      )}
    </Card>
  )
}

function EvaluationSection({ startup: s, latest, canRun }: { startup: StartupDetail; latest: EvaluationOut | undefined; canRun: boolean }) {
  const refresh = useRefreshStartup()
  const running = latest && (latest.status === 'queued' || latest.status === 'running')
  const [jobId, setJobId] = useState<string | null>(running ? latest.job_id : null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const job = useJob(jobId, () => refresh(s.id))

  const run = async () => {
    setBusy(true)
    setError(null)
    try {
      const started = await api<{ job_id: string }>(`/api/startups/${s.id}/evaluations`, { method: 'POST' })
      setJobId(started.job_id)
      await refresh(s.id)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  const cancel = async () => {
    if (!latest) return
    try {
      await api(`/api/startups/${s.id}/evaluations/${latest.id}/cancel`, { method: 'POST' })
      await refresh(s.id)
    } catch (err) {
      setError(errorMessage(err))
    }
  }
  const publish = async () => {
    if (!latest) return
    try {
      await api(`/api/startups/${s.id}/evaluations/${latest.id}/publish`, { method: 'POST' })
      await refresh(s.id)
    } catch (err) {
      setError(errorMessage(err))
    }
  }
  const active = job.status === 'running' || running

  return (
    <Card title="4 · AI evaluation" action={
      active
        ? <Button variant="danger" onClick={cancel}>Cancel</Button>
        : <Button busy={busy} disabled={!canRun} onClick={run}>{latest ? 'Run again' : 'Run evaluation'}</Button>
    }>
      {!canRun && <p className="text-sm text-slate-500">Upload a deck first: the evaluation reads it page by page and cites what it uses.</p>}
      {error && <p className="mb-3 text-sm text-rose-700">{error}</p>}
      <JobProgress job={job} title="Evaluating" />
      {latest?.status === 'complete' && !active && (
        <div className="mt-2 flex flex-wrap items-center gap-5">
          <ScoreRing score={latest.score} size={72} />
          <div className="space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <RecommendationBadge label={latest.recommendation} />
              <Badge>v{latest.version}</Badge>
              <Badge tone={latest.visibility === 'published' ? 'green' : 'slate'}>{latest.visibility === 'published' ? 'Visible to investors' : 'Private'}</Badge>
            </div>
            <div className="flex flex-wrap gap-2">
              <Link href={`/startups/${s.slug}`} className="text-sm font-bold text-[#0284c7] hover:underline">Read the full report</Link>
              {latest.visibility !== 'published' && s.status === 'published' && <button onClick={publish} className="text-sm font-bold text-[#0284c7] hover:underline">Publish this version</button>}
            </div>
          </div>
        </div>
      )}
      {latest?.status === 'failed' && !active && <p className="mt-2 text-sm text-rose-700">The last evaluation did not finish: {latest.error}</p>}
      <p className="mt-4 text-xs text-slate-500">
        About a minute. An analyst agent researches your market on the web, a fixed rubric scores seven dimensions
        (five independent judgments each), and every claim in the report links to a slide or a web source. Five runs a day.
      </p>
    </Card>
  )
}

function PublishSection({ startup: s, ready }: { startup: StartupDetail; ready: boolean }) {
  const refresh = useRefreshStartup()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const publish = async () => {
    setBusy(true)
    setError(null)
    try {
      await api(`/api/startups/${s.id}/publish`, { method: 'POST' })
      await refresh(s.id)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <Card title="5 · Publish">
      {s.status === 'published' ? (
        <p className="text-sm text-emerald-800">
          <CheckCircle2 className="inline w-4 h-4 mr-1" />Investors can see {s.name}, its deck evidence and the published evaluation.
        </p>
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-slate-600">Publishing lists you in the investor catalogue with your deck, evaluation and registry status.</p>
          <Button busy={busy} disabled={!ready} onClick={publish}>Publish</Button>
        </div>
      )}
      {error && <p className="mt-2 text-sm text-rose-700">{error}</p>}
    </Card>
  )
}
