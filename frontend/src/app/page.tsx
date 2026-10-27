'use client'

import Link from 'next/link'
import { motion } from 'framer-motion'
import { ArrowUpRight, Bot, FileSearch, FileText, Fingerprint, Network, ScanText, ShieldCheck, Trophy, Vote } from 'lucide-react'
import { DeskHero } from '@/components/landing/DeskHero'
import { BrandMark } from '@/components/Navbar'
import { useAuth, getDashboardPath } from '@/context/AuthContext'
import { usePublicStats } from '@/lib/api/hooks'
import { formatAC } from '@/lib/format'

const STEPS = [
  { icon: ScanText, n: '01', title: 'TitanOCR reads the deck', text: 'PDFs, PPTX and scans, page by page on the CPU. Every line keeps its box, confidence and origin; hidden text is flagged.', spec: '11 pages · 6.0 s · 1.00 conf' },
  { icon: FileSearch, n: '02', title: 'An agent does the diligence', text: 'It researches the market on the web, checks the deck’s own figures against what it finds, and cites both.', spec: 'deck [c:…] · web [w:n]' },
  { icon: Fingerprint, n: '03', title: 'A rubric, not a vibe', text: 'Seven anchored dimensions, five independent judgments each. The overall score is computed; registry problems cap the label.', spec: 'std 0.16 over 5 runs' },
  { icon: Vote, n: '04', title: 'Investors decide', text: 'Review and rank, then vote quadratically and pledge AuraCoin into escrow released in milestone tranches.', spec: 'n votes = n² AC' },
]

const FEATURES = [
  { icon: ShieldCheck, title: 'Registry checks', text: 'CINs are checked against the MCA record. Struck-off companies are capped at Pass, name mismatches at Hold.' },
  { icon: FileText, title: 'Hidden-instruction detection', text: 'White-on-white text and speaker-note prompts aimed at an AI are found, flagged and shown to investors.' },
  { icon: Network, title: 'An index you can watch', text: 'Hybrid dense + BM25 retrieval over HNSW. The embedding map shows where a deck sits and how a question was answered.' },
  { icon: Trophy, title: 'Community ranking', text: 'A weighted Borda count over every investor’s top ten, shown next to the AI score and the gap between them.' },
]

function Facts() {
  const stats = usePublicStats()
  const d = stats.data
  const facts = [
    { value: d?.startups_published ?? '—', label: 'startups with evidence-backed evaluations' },
    { value: d?.investors ?? '—', label: 'investors reviewing and ranking' },
    { value: d ? Object.keys(d.domains).length : '—', label: 'domains, from agritech to insurtech' },
    { value: d ? formatAC(d.ac_supply_minor, { compact: true }) : '—', label: 'AuraCoin issued with investor plans' },
  ]
  return (
    <ul className="grid gap-x-8 gap-y-10 sm:grid-cols-2 lg:grid-cols-4">
      {facts.map(fact => (
        <li key={fact.label} className="grid gap-2 border-t-2 border-ink pt-4">
          <b className="font-display text-[clamp(2.4rem,4vw,3.4rem)] font-[750] leading-none tracking-[-0.03em] text-ink">{fact.value}</b>
          <span className="text-[0.95rem] text-ink-2">{fact.label}</span>
        </li>
      ))}
    </ul>
  )
}

function CopilotPreview() {
  return (
    <div className="rounded-[14px] border border-rule bg-sheet p-5 shadow-[0_1px_2px_rgb(30_40_70/.06),0_18px_40px_-18px_rgb(30_40_70/.28)]">
      <div className="ml-auto max-w-[85%] rounded-2xl rounded-br-md bg-cobalt px-4 py-3 text-[0.95rem] text-white">
        What has KrishiMitra AI submitted, and is its TAM verified?
      </div>
      <div className="mt-4 flex flex-wrap gap-2 font-mono text-[0.66rem] text-ink-3">
        <span className="rounded-full border border-rule bg-white px-2.5 py-1">list_documents · KrishiMitra AI</span>
        <span className="rounded-full border border-rule bg-white px-2.5 py-1">search_documents · “TAM market size”</span>
        <span className="rounded-full border border-rule bg-white px-2.5 py-1">get_evaluation</span>
      </div>
      <div className="mt-3 rounded-xl border border-rule bg-white p-3">
        <div className="flex items-center gap-3">
          <FileText className="h-5 w-5 text-cobalt" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-[0.9rem] font-semibold text-ink">KrishiMitra_AI_Pitch_Deck.pdf</p>
            <p className="font-mono text-[0.62rem] text-ink-3">deck · 11 pages · read by TitanOCR in 6.0 s</p>
          </div>
          <span className="rounded-full bg-[#eef1fd] px-2.5 py-1 font-mono text-[0.62rem] text-cobalt">open</span>
        </div>
      </div>
      <p className="mt-4 text-[0.95rem] leading-relaxed text-ink-2">
        One document: the 11-page pitch deck. Its TAM is <b className="text-ink">USD 82.3M in 2025</b>
        <span className="mx-1 inline-flex items-center gap-0.5 rounded bg-[#eef1fd] px-1.5 py-px align-baseline text-[0.72rem] font-semibold text-cobalt ring-1 ring-[#cdd5fb]"><FileText className="h-3 w-3" />p.4</span>
        attributed to MarketsandMarkets, but the research did not find an independent source, so the report
        treats it as the company&apos;s own figure.
      </p>
    </div>
  )
}

export default function LandingPage() {
  const { me } = useAuth()
  const home = me ? getDashboardPath(me.user.role) : null
  const reveal = { initial: { opacity: 0, y: 24 }, whileInView: { opacity: 1, y: 0 }, viewport: { once: true, margin: '-80px' }, transition: { duration: 0.7, ease: [0.16, 1, 0.3, 1] as const } }

  return (
    <div className="bg-bench text-ink">
      <DeskHero signedInHome={home} />

      <section className="mx-auto max-w-7xl px-5 py-[clamp(64px,9vw,112px)] sm:px-8">
        <motion.div {...reveal}><Facts /></motion.div>
      </section>

      <section id="how" className="scroll-mt-24 border-y border-rule bg-sheet">
        <div className="mx-auto max-w-7xl px-5 py-[clamp(64px,9vw,112px)] sm:px-8">
          <motion.div {...reveal} className="max-w-3xl">
            <p className="font-mono text-[0.72rem] uppercase tracking-[0.06em] text-ink-3">How a deck becomes a decision</p>
            <h2 className="mt-3 font-display text-[clamp(2.2rem,4.4vw,3.6rem)] font-[780] leading-[0.98] tracking-[-0.035em]">Every number keeps its place on the page.</h2>
            <p className="mt-4 max-w-[60ch] text-[1.1rem] text-ink-2">Nothing in a report is unsourced: a figure points at the line on the slide it came from, or at the web page that backs it.</p>
          </motion.div>
          <ol className="mt-12 grid gap-5 md:grid-cols-2 lg:grid-cols-4">
            {STEPS.map((step, i) => (
              <motion.li key={step.n} {...reveal} transition={{ ...reveal.transition, delay: i * 0.08 }}
                         className="flex flex-col rounded-[14px] border border-rule bg-white p-6">
                <div className="flex items-center justify-between">
                  <step.icon className="h-6 w-6 text-cobalt" />
                  <span className="font-mono text-[0.72rem] text-ink-3">{step.n}</span>
                </div>
                <h3 className="mt-5 text-[1.15rem] font-bold leading-snug">{step.title}</h3>
                <p className="mt-2 flex-1 text-[0.95rem] leading-relaxed text-ink-2">{step.text}</p>
                <p className="mt-5 border-t border-rule pt-3 font-mono text-[0.68rem] text-ink-3">{step.spec}</p>
              </motion.li>
            ))}
          </ol>
        </div>
      </section>

      <section className="mx-auto grid max-w-7xl items-center gap-12 px-5 py-[clamp(64px,9vw,112px)] sm:px-8 lg:grid-cols-2">
        <motion.div {...reveal}>
          <p className="inline-flex items-center gap-2 font-mono text-[0.72rem] uppercase tracking-[0.06em] text-ink-3"><Bot className="h-4 w-4 text-cobalt" /> Investor copilot</p>
          <h2 className="mt-3 font-display text-[clamp(2.2rem,4.4vw,3.6rem)] font-[780] leading-[0.98] tracking-[-0.035em]">Ask anything about any startup.</h2>
          <p className="mt-4 max-w-[52ch] text-[1.1rem] text-ink-2">
            The copilot searches the catalogue, pulls up the documents a startup submitted, reads the exact slides,
            compares companies and checks the web. It shows each tool it uses and cites every slide, so you can open
            the page it is talking about.
          </p>
          <Link href={me ? '/copilot' : '/login?next=/copilot'} className="mt-7 inline-flex h-12 items-center gap-3 rounded-full bg-ink pl-5 pr-2.5 font-semibold text-white hover:bg-black">
            Open the copilot <span className="grid h-7 w-7 place-items-center rounded-full bg-white/15"><ArrowUpRight className="h-4 w-4" /></span>
          </Link>
        </motion.div>
        <motion.div {...reveal} transition={{ ...reveal.transition, delay: 0.1 }}><CopilotPreview /></motion.div>
      </section>

      <section className="border-t border-rule bg-sheet">
        <div className="mx-auto max-w-7xl px-5 py-[clamp(64px,9vw,112px)] sm:px-8">
          <motion.h2 {...reveal} className="max-w-3xl font-display text-[clamp(2.2rem,4.4vw,3.6rem)] font-[780] leading-[0.98] tracking-[-0.035em]">Built to be checked, not trusted.</motion.h2>
          <div className="mt-12 grid gap-px overflow-hidden rounded-[14px] border border-rule bg-rule sm:grid-cols-2">
            {FEATURES.map(feature => (
              <div key={feature.title} className="bg-white p-7">
                <feature.icon className="h-6 w-6 text-cobalt" />
                <h3 className="mt-4 text-[1.15rem] font-bold">{feature.title}</h3>
                <p className="mt-2 max-w-[48ch] text-[0.98rem] leading-relaxed text-ink-2">{feature.text}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="relative isolate overflow-hidden bg-desk-lo text-hero-ink">
        <div className="absolute inset-0 -z-10 bg-[radial-gradient(60%_90%_at_80%_20%,var(--color-desk-hi),var(--color-desk-mid)_55%,var(--color-desk-lo))]" aria-hidden="true" />
        <div className="absolute inset-0 -z-10 bg-[repeating-linear-gradient(90deg,rgb(0_0_0/.13)_0_1px,transparent_1px_7px)]" aria-hidden="true" />
        <div className="mx-auto flex max-w-7xl flex-col gap-8 px-5 py-20 sm:px-8 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h2 className="font-display text-[clamp(2.2rem,4.4vw,3.8rem)] font-[800] leading-[0.95] tracking-[-0.04em]">Founders list free.<br />Investors subscribe.</h2>
            <p className="mt-4 max-w-[52ch] text-[1.08rem] text-hero-ink-2">Scout is free. Angel (₹4,999/month) and Syndicate (₹24,999/month) add full reports, deck evidence, voting and monthly AuraCoin. Founders pay 2% of each tranche released to them.</p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Link href="/pricing" className="inline-flex h-[54px] items-center gap-3 rounded-full bg-cobalt-bright pl-6 pr-3 font-semibold text-white hover:bg-[#4560ff]">
              See plans <span className="grid h-7 w-7 place-items-center rounded-full bg-white/15"><ArrowUpRight className="h-4 w-4" /></span>
            </Link>
            {!me && (
              <Link href="/register?role=startup" className="inline-flex h-[54px] items-center rounded-full border border-[rgb(255_240_225/.34)] px-6 font-semibold text-hero-ink hover:border-[rgb(255_240_225/.7)]">
                List your startup
              </Link>
            )}
          </div>
        </div>
      </section>

      <footer className="border-t border-rule bg-bench">
        <div className="mx-auto flex max-w-7xl flex-col gap-3 px-5 py-8 text-[0.85rem] text-ink-3 sm:flex-row sm:items-center sm:justify-between sm:px-8">
          <span className="inline-flex items-center gap-2 text-ink"><BrandMark className="h-4 w-4" /><b className="font-display">AURA3</b></span>
          <span className="font-mono text-[0.68rem]">Documents read by TitanOCR · AI analysis, not investment advice · AuraCoin is a closed-loop credit</span>
        </div>
      </footer>
    </div>
  )
}
