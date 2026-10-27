'use client'

import Link from 'next/link'
import { motion } from 'framer-motion'
import { ArrowDown, ArrowRight, Bot, FileText, Network, ShieldCheck, Trophy } from 'lucide-react'
import { HeroDesk } from '@/components/landing/HeroDesk'
import { BrandMark, Wordmark } from '@/components/Navbar'
import { useAuth, getDashboardPath } from '@/context/AuthContext'
import { usePublicStats } from '@/lib/api/hooks'
import { formatAC } from '@/lib/format'

const EASE = [0.16, 1, 0.3, 1] as const
const RISE = { hidden: { opacity: 0, y: 18 }, show: { opacity: 1, y: 0, transition: { duration: 0.8, ease: EASE } } }
const LINE = { hidden: { y: '110%' }, show: { y: '0%', transition: { duration: 1, ease: EASE } } }
const REVEAL = { initial: { opacity: 0, y: 22 }, whileInView: { opacity: 1, y: 0 }, viewport: { once: true, margin: '-60px' }, transition: { duration: 0.7, ease: [0.16, 1, 0.3, 1] as const } }

const LEDGER = [
  { n: '01', title: 'Read every page', text: 'Decks, slides and scans are read by TitanOCR. Each line keeps its box on the page, its confidence, and a flag if it hides instructions for an AI.', receipt: '11 pages · 6.0 s · conf 1.00' },
  { n: '02', title: 'Research like an analyst', text: 'An agent searches the market, checks the deck’s own figures against what it finds, and records every source it read.', receipt: 'deck [c:…] · web [w:n]' },
  { n: '03', title: 'Score on a fixed rubric', text: 'Seven anchored dimensions, five independent judgments each. The overall is computed, never guessed; registry problems cap the label.', receipt: 'σ 0.16 over 5 runs' },
  { n: '04', title: 'Decide together', text: 'Investors review and rank, then vote quadratically and pledge AuraCoin into escrow that is released milestone by milestone.', receipt: 'n votes = n² AC' },
]

const FEATURES = [
  { icon: ShieldCheck, title: 'Registry checks', text: 'Every CIN is checked against the MCA record. Struck-off companies are capped at Pass and name mismatches at Hold.' },
  { icon: FileText, title: 'Hidden-instruction detection', text: 'White-on-white prompts and speaker notes aimed at an AI evaluator are found, flagged and shown to investors.' },
  { icon: Network, title: 'An index you can watch', text: 'Dense and keyword retrieval over an HNSW index. The embedding map shows where a deck sits and how a question was answered.' },
  { icon: Trophy, title: 'Community ranking', text: 'A weighted Borda count over every investor’s top ten, shown next to the AI score so disagreements are visible.' },
]

/** Concentric rings behind the hero and the pricing band: the brand mark's aura, at scale. */
function Aura({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 800 800" className={className} aria-hidden="true" fill="none">
      {[120, 210, 300, 390].map((r, i) => (
        <circle key={r} cx="400" cy="400" r={r} stroke="rgb(232 240 236)" strokeOpacity={0.07 - i * 0.012} strokeWidth="1.2"
                strokeDasharray={i % 2 ? '2 10' : undefined} />
      ))}
    </svg>
  )
}

function Figures() {
  const stats = usePublicStats()
  const d = stats.data
  const figures = [
    { value: d?.startups_published ?? '—', label: 'startups with cited, rubric-scored evaluations' },
    { value: d?.investors ?? '—', label: 'investors reviewing and ranking' },
    { value: d ? Object.keys(d.domains).length : '—', label: 'domains, agritech to insurtech' },
    { value: d ? formatAC(d.ac_supply_minor, { compact: true }) : '—', label: 'AuraCoin issued with plans' },
  ]
  return (
    <dl className="grid divide-line sm:grid-cols-2 sm:divide-x lg:grid-cols-4">
      {figures.map(f => (
        <div key={f.label} className="px-0 py-5 sm:px-6 first:pl-0">
          <dt className="sr-only">{f.label}</dt>
          <dd className="font-display text-[clamp(2.4rem,4vw,3.3rem)] font-semibold leading-none tracking-[-0.02em] text-ink">{f.value}</dd>
          <dd className="mt-2 max-w-[22ch] text-[0.95rem] text-ink-3">{f.label}</dd>
        </div>
      ))}
    </dl>
  )
}

function CopilotPreview() {
  return (
    <div className="rounded-2xl border border-line bg-white p-5 shadow-[0_30px_60px_-40px_rgb(15_26_22/.45)]">
      <div className="ml-auto w-fit max-w-[88%] rounded-2xl rounded-br-md bg-jade-600 px-4 py-2.5 text-[0.95rem] text-white">
        What has KrishiMitra AI submitted, and is its TAM verified?
      </div>
      <div className="mt-4 flex flex-wrap gap-1.5">
        {['Profile', 'Submitted documents', 'Searched documents · “TAM”', 'Web search'].map(t => (
          <span key={t} className="rounded-md border border-line bg-paper-2 px-2 py-1 font-mono text-[0.65rem] text-ink-3">✓ {t}</span>
        ))}
      </div>
      <div className="mt-3 flex items-center gap-3 rounded-xl border border-line bg-paper-2 p-3">
        <FileText className="h-5 w-5 text-jade-600" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-[0.9rem] font-semibold text-ink">KrishiMitra_AI_Pitch_Deck.pdf</p>
          <p className="font-mono text-[0.62rem] text-ink-3">deck · 11 pages · read in 6.0 s</p>
        </div>
        <span className="rounded-md bg-jade-50 px-2.5 py-1 text-xs font-semibold text-jade-700">Open</span>
        <span className="rounded-md border border-line px-2.5 py-1 text-xs font-semibold text-ink-2">Download</span>
      </div>
      <p className="mt-4 text-[0.95rem] leading-relaxed text-ink-2">
        One document, the 11-page deck. It puts the TAM at <b className="text-ink">USD 82.3M in 2025</b>
        <span className="mx-1 inline-flex items-center gap-0.5 rounded bg-jade-50 px-1.5 py-px align-baseline text-[0.72rem] font-semibold text-jade-700 ring-1 ring-jade-200"><FileText className="h-3 w-3" />p.4</span>
        citing MarketsandMarkets; other research firms size the market very differently
        <span className="mx-1 inline-flex rounded bg-marigold-50 px-1.5 py-px align-baseline text-[0.72rem] font-semibold text-marigold-700 ring-1 ring-marigold-300">3</span>,
        so treat it as the company&apos;s figure.
      </p>
    </div>
  )
}

export default function LandingPage() {
  const { me } = useAuth()
  const home = me ? getDashboardPath(me.user.role) : null
  const stats = usePublicStats()

  return (
    <div className="bg-paper text-ink">
      <HeroDesk
        footer={
          <>
            <p className="flex flex-wrap gap-x-6 gap-y-1 font-mono text-[0.7rem] text-mist-3">
              <span><b className="font-medium text-mist">{stats.data?.startups_published ?? 25}</b> startups, every score cited</span>
              <span><b className="font-medium text-mist">{stats.data ? Object.keys(stats.data.domains).length : 12}</b> domains</span>
              <span><b className="font-medium text-mist">{stats.data?.investors ?? 6}</b> investors ranking</span>
              {!home && <Link href="/login" className="text-mist-2 underline decoration-white/25 underline-offset-4 hover:text-white">Try a demo account</Link>}
            </p>
            <a href="#how" className="group inline-flex items-center gap-2 font-mono text-[0.7rem] text-mist-3 hover:text-white">
              How it works <ArrowDown className="h-3.5 w-3.5 transition-transform group-hover:translate-y-0.5" />
            </a>
          </>
        }
      >
        <motion.div initial="hidden" animate="show" variants={{ show: { transition: { staggerChildren: 0.08, delayChildren: 0.05 } } }}>
          <motion.p variants={RISE} className="inline-flex items-center gap-2.5 font-mono text-[0.7rem] uppercase tracking-[0.12em] text-mist-2">
            <span className="h-1.5 w-1.5 rounded-full bg-jade-400 shadow-[0_0_0_4px_rgb(63_174_132/.2)]" /> Evidence-first venture investing · India
          </motion.p>
          <h1 className="mt-7 font-display text-[clamp(3.3rem,6.8vw,7.1rem)] font-semibold leading-[0.9] tracking-[-0.035em] text-white">
            {[<>Every claim,</>, <>traced to</>, <>its <em className="italic text-jade-300">source</em>.</>].map((line, i) => (
              <span key={i} className="-mb-[0.12em] block overflow-hidden pb-[0.12em]">
                <motion.span variants={LINE} className="block">{line}</motion.span>
              </span>
            ))}
          </h1>
          <motion.p variants={RISE} className="mt-8 max-w-[34ch] text-[clamp(1.06rem,1.3vw,1.24rem)] leading-[1.55] text-mist-2">
            AURA3 reads every pitch deck line by line, checks its numbers against the market and scores it on a fixed
            rubric. Every claim links back to the slide it came from.
          </motion.p>
          <motion.div variants={RISE} className="mt-9 flex flex-wrap items-center gap-3">
            {home ? (
              <Link href={home} className="group inline-flex h-[3.25rem] items-center gap-2 rounded-xl bg-jade-400 px-6 font-semibold text-night transition-colors hover:bg-jade-300">
                Go to your dashboard <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
              </Link>
            ) : (
              <>
                <Link href="/register?role=investor" className="group inline-flex h-[3.25rem] items-center gap-2 rounded-xl bg-jade-400 px-6 font-semibold text-night transition-colors hover:bg-jade-300">
                  Explore startups <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
                </Link>
                <Link href="/register?role=startup" className="inline-flex h-[3.25rem] items-center rounded-xl border border-white/15 bg-night/40 px-6 font-semibold text-white backdrop-blur-sm transition-colors hover:border-white/35">
                  List your startup
                </Link>
              </>
            )}
          </motion.div>
        </motion.div>
      </HeroDesk>

      <section className="border-b border-line bg-paper-2">
        <div className="mx-auto max-w-7xl px-5 py-10 sm:px-8"><Figures /></div>
      </section>

      <section id="how" className="mx-auto max-w-7xl scroll-mt-20 px-5 py-[clamp(64px,9vw,110px)] sm:px-8">
        <motion.div {...REVEAL} className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)] lg:gap-16">
          <div>
            <p className="font-mono text-[0.72rem] text-jade-700">How a deck becomes a decision</p>
            <h2 className="mt-3 font-display text-[clamp(2.2rem,4vw,3.4rem)] font-semibold leading-[1.02] tracking-[-0.02em]">A ledger of evidence, not a vibe check.</h2>
            <p className="mt-4 max-w-[46ch] text-[1.05rem] leading-relaxed text-ink-2">Each step leaves a receipt: the line it read, the page it cited, the source it checked, the rubric it applied.</p>
          </div>
          <ol className="divide-y divide-line border-y border-line">
            {LEDGER.map(row => (
              <li key={row.n} className="grid gap-2 py-6 sm:grid-cols-[3rem_minmax(0,1fr)_auto] sm:gap-6">
                <span className="font-mono text-[0.8rem] text-jade-700">{row.n}</span>
                <div>
                  <h3 className="font-display text-[1.35rem] font-semibold tracking-[-0.01em]">{row.title}</h3>
                  <p className="mt-1.5 max-w-[56ch] text-[0.97rem] leading-relaxed text-ink-2">{row.text}</p>
                </div>
                <span className="self-start whitespace-nowrap rounded-md bg-paper-2 px-2 py-1 font-mono text-[0.68rem] text-ink-3 ring-1 ring-line">{row.receipt}</span>
              </li>
            ))}
          </ol>
        </motion.div>
      </section>

      <section className="border-y border-line bg-paper-2">
        <div className="mx-auto grid max-w-7xl grid-cols-[minmax(0,1fr)] items-center gap-12 px-5 py-[clamp(64px,9vw,110px)] sm:px-8 lg:grid-cols-2">
          <motion.div {...REVEAL}>
            <p className="inline-flex items-center gap-2 font-mono text-[0.72rem] text-jade-700"><Bot className="h-4 w-4" /> Investor copilot</p>
            <h2 className="mt-3 font-display text-[clamp(2.2rem,4vw,3.4rem)] font-semibold leading-[1.02] tracking-[-0.02em]">Ask anything about any startup.</h2>
            <p className="mt-4 max-w-[50ch] text-[1.05rem] leading-relaxed text-ink-2">
              The copilot finds startups, pulls up the documents they submitted, reads the exact slides, compares
              companies and checks the web. You see every tool it uses, and every claim links to its page.
            </p>
            <Link href={me ? '/copilot' : '/login?next=/copilot'} className="mt-7 inline-flex h-11 items-center gap-2 rounded-xl bg-ink px-5 font-semibold text-white hover:bg-black">
              Open the copilot <ArrowRight className="h-4 w-4" />
            </Link>
          </motion.div>
          <motion.div {...REVEAL} transition={{ ...REVEAL.transition, delay: 0.1 }}><CopilotPreview /></motion.div>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-5 py-[clamp(64px,9vw,110px)] sm:px-8">
        <motion.h2 {...REVEAL} className="max-w-3xl font-display text-[clamp(2.2rem,4vw,3.4rem)] font-semibold leading-[1.02] tracking-[-0.02em]">Built to be checked, not trusted.</motion.h2>
        <div className="mt-10 grid gap-4 sm:grid-cols-2">
          {FEATURES.map((f, i) => (
            <motion.div key={f.title} {...REVEAL} transition={{ ...REVEAL.transition, delay: i * 0.06 }}
                        className="rounded-2xl border border-line bg-white p-6">
              <span className="grid h-10 w-10 place-items-center rounded-xl bg-jade-50 text-jade-700"><f.icon className="h-5 w-5" /></span>
              <h3 className="mt-4 text-[1.1rem] font-semibold">{f.title}</h3>
              <p className="mt-1.5 max-w-[48ch] text-[0.97rem] leading-relaxed text-ink-2">{f.text}</p>
            </motion.div>
          ))}
        </div>
      </section>

      <section className="relative isolate overflow-hidden bg-night text-mist">
        <div className="absolute inset-0 -z-10 bg-[radial-gradient(50%_80%_at_85%_50%,rgb(31_150_112/.25),transparent_70%)]" aria-hidden="true" />
        <Aura className="absolute -right-56 top-1/2 -z-10 h-[46rem] w-[46rem] -translate-y-1/2" />
        <div className="mx-auto flex max-w-7xl flex-col gap-8 px-5 py-20 sm:px-8 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h2 className="font-display text-[clamp(2.2rem,4vw,3.4rem)] font-semibold leading-[1.02] tracking-[-0.02em] text-white">Founders list free. Investors subscribe.</h2>
            <p className="mt-4 max-w-[54ch] text-[1.05rem] text-mist-2">
              Scout is free. Angel (₹4,999/month) and Syndicate (₹24,999/month) add full reports, deck evidence, voting and
              monthly AuraCoin. Founders pay 2% of each tranche released to them, nothing before.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Link href="/pricing" className="inline-flex h-12 items-center gap-2 rounded-xl bg-jade-400 px-5 font-semibold text-night hover:bg-jade-300">See plans <ArrowRight className="h-4 w-4" /></Link>
            {!me && <Link href="/register?role=startup" className="inline-flex h-12 items-center rounded-xl border border-white/15 px-5 font-semibold text-white hover:border-white/35">List your startup</Link>}
          </div>
        </div>
      </section>

      <footer className="bg-paper">
        <div className="mx-auto flex max-w-7xl flex-col gap-3 px-5 py-8 sm:flex-row sm:items-center sm:justify-between sm:px-8">
          <span className="inline-flex items-center gap-2 text-ink"><BrandMark className="h-5 w-5 text-jade-600" /><Wordmark className="text-[1.1rem]" /></span>
          <span className="font-mono text-[0.68rem] text-ink-3">Decks read by TitanOCR · AI analysis, not investment advice · AuraCoin is a closed-loop credit</span>
        </div>
      </footer>
    </div>
  )
}
