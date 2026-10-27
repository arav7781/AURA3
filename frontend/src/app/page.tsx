'use client'

import Link from 'next/link'
import { motion } from 'framer-motion'
import { Coins, FileSearch, Network, ScanText, ShieldCheck, Trophy, Vote } from 'lucide-react'
import { useAuth, getDashboardPath } from '@/context/AuthContext'
import { usePublicStats } from '@/lib/api/hooks'
import { formatAC } from '@/lib/format'

const STEPS = [
  { icon: ScanText, title: 'TitanOCR reads the deck', text: 'Every page, scanned or digital, becomes cited passages with the exact box each line came from, and hidden instructions are flagged.' },
  { icon: FileSearch, title: 'An agent does the diligence', text: 'It researches the market, checks the deck’s numbers against what it finds, and scores a fixed rubric. Each claim links to its slide or source.' },
  { icon: Trophy, title: 'Investors review and rank', text: 'Scores sit next to investor reviews and a community ranking, weighted so free accounts cannot swamp paying ones.' },
  { icon: Vote, title: 'Rounds run on AuraCoin', text: 'Quadratic votes and escrowed pledges, released in milestone tranches. No wallet, no gas: a ledger you can audit.' },
]

const FEATURES = [
  { icon: ShieldCheck, title: 'Registry checks', text: 'CINs are checked against the MCA record. Struck-off companies and name mismatches cap the recommendation.' },
  { icon: Network, title: 'Embedding map', text: 'See where a deck sits among all decks by meaning, and watch the HNSW index answer a question live.' },
  { icon: Coins, title: 'AuraCoin', text: 'A closed-loop credit granted with your plan, used to vote and pledge. Never sold, transferred or cashed out.' },
]

export default function LandingPage() {
  const { me } = useAuth()
  const stats = usePublicStats()
  const home = me ? getDashboardPath(me.user.role) : null

  return (
    <div>
      <section className="relative overflow-hidden px-4 sm:px-6 py-20 md:py-28">
        <div className="absolute inset-0 bg-gradient-to-b from-sky-50 via-white to-white" />
        <div className="relative max-w-6xl mx-auto grid gap-12 lg:grid-cols-12 items-center">
          <motion.div className="lg:col-span-7" initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }}>
            <p className="inline-flex items-center gap-2 rounded-full border border-sky-200 bg-white px-3 py-1 text-[11px] font-mono font-bold uppercase tracking-widest text-[#0284c7]">
              Evidence-first startup investing
            </p>
            <h1 className="mt-5 text-5xl md:text-6xl font-black tracking-tight text-slate-900 leading-[1.02]">
              Due diligence you can <span className="text-[#0284c7]">click through</span>.
            </h1>
            <p className="mt-5 text-lg text-slate-600 max-w-xl leading-relaxed">
              AURA3 reads pitch decks with TitanOCR, has an AI analyst research and score them against a fixed rubric,
              and links every claim to the slide or source it came from. Investors review, rank and back startups with
              AuraCoin.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              {home ? (
                <Link href={home} className="rounded-lg bg-[#0284c7] px-6 py-3 font-bold text-white hover:brightness-110">Go to your dashboard</Link>
              ) : (
                <>
                  <Link href="/register?role=investor" className="rounded-lg bg-[#0284c7] px-6 py-3 font-bold text-white hover:brightness-110">I invest</Link>
                  <Link href="/register?role=startup" className="rounded-lg border border-slate-300 bg-white px-6 py-3 font-bold text-slate-800 hover:bg-slate-50">I’m raising</Link>
                  <Link href="/login" className="px-2 py-3 font-bold text-[#0284c7] hover:underline">Sign in with a demo account</Link>
                </>
              )}
            </div>
          </motion.div>
          <motion.div className="lg:col-span-5" initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.1 }}>
            <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <p className="text-[11px] font-mono font-bold uppercase tracking-widest text-slate-500">On the platform now</p>
              <dl className="mt-4 grid grid-cols-2 gap-5">
                <div><dt className="text-xs text-slate-500">Startups published</dt><dd className="text-3xl font-black text-slate-900">{stats.data?.startups_published ?? '—'}</dd></div>
                <div><dt className="text-xs text-slate-500">Investors</dt><dd className="text-3xl font-black text-slate-900">{stats.data?.investors ?? '—'}</dd></div>
                <div><dt className="text-xs text-slate-500">Domains</dt><dd className="text-3xl font-black text-slate-900">{stats.data ? Object.keys(stats.data.domains).length : '—'}</dd></div>
                <div><dt className="text-xs text-slate-500">AuraCoin issued</dt><dd className="text-2xl font-black text-amber-600">{stats.data ? formatAC(stats.data.ac_supply_minor, { compact: true }) : '—'}</dd></div>
              </dl>
              {stats.data && Object.keys(stats.data.domains).length > 0 && (
                <div className="mt-5 flex flex-wrap gap-1.5">
                  {Object.entries(stats.data.domains).sort((a, b) => b[1] - a[1]).map(([domain, n]) => (
                    <span key={domain} className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-700">{domain} · {n}</span>
                  ))}
                </div>
              )}
            </div>
          </motion.div>
        </div>
      </section>

      <section className="px-4 sm:px-6 py-16 bg-white border-y border-slate-100">
        <div className="max-w-6xl mx-auto">
          <h2 className="text-2xl font-black text-slate-900">How it works</h2>
          <ol className="mt-8 grid gap-5 md:grid-cols-2 lg:grid-cols-4">
            {STEPS.map((step, i) => (
              <li key={step.title} className="rounded-xl border border-slate-200 p-5">
                <step.icon className="w-6 h-6 text-[#0284c7]" />
                <p className="mt-3 text-[11px] font-mono font-bold uppercase tracking-widest text-slate-400">Step {i + 1}</p>
                <h3 className="mt-1 font-bold text-slate-900">{step.title}</h3>
                <p className="mt-2 text-sm text-slate-600 leading-relaxed">{step.text}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="px-4 sm:px-6 py-16">
        <div className="max-w-6xl mx-auto grid gap-5 md:grid-cols-3">
          {FEATURES.map(feature => (
            <div key={feature.title} className="rounded-xl border border-slate-200 bg-white p-6">
              <feature.icon className="w-6 h-6 text-[#0284c7]" />
              <h3 className="mt-3 font-bold text-slate-900">{feature.title}</h3>
              <p className="mt-2 text-sm text-slate-600 leading-relaxed">{feature.text}</p>
            </div>
          ))}
        </div>
        <div className="max-w-6xl mx-auto mt-10 flex flex-col items-center gap-3 rounded-2xl bg-slate-900 px-6 py-10 text-center">
          <h2 className="text-2xl font-black text-white">Founders list free. Investors subscribe.</h2>
          <p className="max-w-xl text-slate-300">Scout is free; Angel and Syndicate add full reports, deck evidence, voting and monthly AuraCoin.</p>
          <Link href="/pricing" className="mt-2 rounded-lg bg-white px-5 py-2.5 font-bold text-slate-900 hover:bg-slate-100">See plans</Link>
        </div>
      </section>
    </div>
  )
}
