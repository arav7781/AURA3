'use client'

import { useEffect, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { FileText, Globe, Quote, Gauge } from 'lucide-react'
import { clsx } from 'clsx'
import { CITED_LINES, HERO_EVALUATION, HERO_LINES, HERO_PAGE } from './heroData'

// One claim followed from the slide it was read on to the score it fed: real output for KrishiMitra AI.

const STEPS = [
  { key: 'read', label: 'Read', note: 'TitanOCR reads every line, with its box' },
  { key: 'cite', label: 'Cite', note: 'The claim keeps a pointer to its line' },
  { key: 'verify', label: 'Verify', note: 'Checked against the web, not trusted' },
  { key: 'score', label: 'Score', note: 'A fixed rubric turns evidence into a score' },
] as const
const EASE = [0.16, 1, 0.3, 1] as const
const CROP = 0.58 // show the top of the slide, where the market lines are
const CLAIM = HERO_LINES[CITED_LINES[0]]

function Slide({ step, reduce }: { step: number; reduce: boolean | null }) {
  return (
    <div className="relative overflow-hidden rounded-lg bg-white" style={{ aspectRatio: `${HERO_PAGE.width} / ${HERO_PAGE.height * CROP}` }}>
      <div className="absolute inset-x-0 top-0" style={{ aspectRatio: `${HERO_PAGE.width} / ${HERO_PAGE.height}` }}>
        {/* eslint-disable-next-line @next/next/no-img-element -- fixed hero asset */}
        <img src={HERO_PAGE.src} alt="Page 4 of the KrishiMitra AI pitch deck" className="absolute inset-0 h-full w-full" />
        {HERO_LINES.map((line, i) => {
          const [x0, y0, x1, y1] = line.box
          const cited = CITED_LINES.includes(i)
          return (
            <motion.span key={i} className="absolute rounded-[3px] border"
                         style={{ left: `${x0 * 100 - 0.6}%`, top: `${y0 * 100 - 0.8}%`, width: `${(x1 - x0) * 100 + 1.2}%`, height: `${(y1 - y0) * 100 + 1.6}%` }}
                         initial={false}
                         animate={{
                           opacity: step === 0 ? 1 : cited ? 1 : 0.15,
                           borderColor: cited && step >= 1 ? 'rgb(21 123 91)' : 'rgb(31 150 112 / .7)',
                           backgroundColor: cited && step >= 1 ? 'rgb(31 150 112 / .2)' : 'rgb(31 150 112 / .08)',
                         }}
                         transition={{ duration: 0.4, delay: step === 0 && !reduce ? i * 0.09 : 0 }} />
          )
        })}
      </div>
    </div>
  )
}

function Node({ active, icon: Icon, title, meta, children, className }: {
  active: boolean
  icon: typeof FileText
  title: string
  meta: string
  children: React.ReactNode
  className?: string
}) {
  return (
    <motion.div animate={{ y: active ? -4 : 0, opacity: active ? 1 : 0.86 }} transition={{ duration: 0.5, ease: EASE }}
                className={clsx('rounded-2xl border bg-paper-2 p-3.5 text-ink shadow-[0_24px_60px_-28px_rgb(0_0_0/.8)] transition-[border-color,box-shadow] duration-500',
                  active ? 'border-jade-400 ring-4 ring-jade-400/20' : 'border-white/0', className)}>
      <div className="mb-2.5 flex items-center justify-between gap-3">
        <span className="inline-flex items-center gap-1.5 text-[0.8rem] font-semibold text-ink"><Icon className="h-3.5 w-3.5 text-jade-600" />{title}</span>
        <span className="truncate font-mono text-[0.62rem] text-ink-3">{meta}</span>
      </div>
      {children}
    </motion.div>
  )
}

function ClaimBody({ step }: { step: number }) {
  return (
    <>
      <p className="font-display text-[1.55rem] font-semibold leading-none tracking-[-0.02em]">USD 82.3M <span className="text-[0.95rem] font-normal text-ink-3">TAM, 2025</span></p>
      <p className="mt-2 line-clamp-2 text-[0.8rem] leading-snug text-ink-2">“{CLAIM.text}”</p>
      <p className={clsx('mt-2 inline-flex rounded-md px-1.5 py-0.5 font-mono text-[0.62rem] transition-colors', step >= 1 ? 'bg-jade-50 text-jade-700' : 'bg-black/5 text-ink-3')}>
        {HERO_PAGE.cid} → p.4, line 2
      </p>
    </>
  )
}

function CheckBody({ step }: { step: number }) {
  return (
    <>
      <p className="flex items-center gap-2 text-[0.95rem] font-semibold">
        <span className={clsx('h-2.5 w-2.5 rounded-full', step >= 2 ? 'bg-marigold-400 shadow-[0_0_0_4px_rgb(238_170_62/.2)]' : 'bg-black/15')} />
        Not independently sourced
      </p>
      <p className="mt-1.5 text-[0.8rem] leading-snug text-ink-2">10 web pages read. The deck cites MarketsandMarkets, so the report shows it as the company&apos;s figure.</p>
    </>
  )
}

function ScoreBody({ step, reduce }: { step: number; reduce: boolean | null }) {
  return (
    <>
      <p className="flex items-baseline gap-2"><span className="font-display text-[2rem] font-semibold leading-none">{HERO_EVALUATION.score}</span><span className="font-mono text-[0.7rem] text-ink-3">/ 10 · {HERO_EVALUATION.label}</span></p>
      <ul className="mt-2.5 grid gap-1">
        {HERO_EVALUATION.scores.map((s, i) => (
          <li key={s.label} className="grid grid-cols-[5.6rem_1fr_1.5rem] items-center gap-2 font-mono text-[0.6rem] text-ink-3">
            <span className="truncate">{s.label}</span>
            <span className="block h-1 rounded-full bg-black/[0.07]">
              <motion.span className="block h-1 rounded-full bg-jade-500" initial={false}
                           animate={{ width: step >= 3 ? `${s.value * 10}%` : '0%' }} transition={{ duration: reduce ? 0 : 0.7, delay: reduce ? 0 : i * 0.05, ease: EASE }} />
            </span>
            <span className="text-right text-ink">{s.value.toFixed(1)}</span>
          </li>
        ))}
      </ul>
    </>
  )
}

// In the diagram's 1000 × 1200 box: from the cited line on the slide to the claim, then to the check and the score.
const LINKS = [
  'M 360 178 C 430 300, 470 360, 548 376',
  'M 600 590 C 560 610, 520 600, 474 612',
  'M 470 712 C 505 735, 525 752, 562 768',
]

export function EvidenceTrail() {
  const reduce = useReducedMotion()
  const [step, setStep] = useState(reduce ? 3 : 0)
  const [paused, setPaused] = useState(false)

  useEffect(() => {
    if (reduce || paused) return
    const timer = setInterval(() => setStep(s => (s + 1) % STEPS.length), 3400)
    return () => clearInterval(timer)
  }, [reduce, paused])
  useEffect(() => {
    if (!paused) return
    const timer = setTimeout(() => setPaused(false), 15000)
    return () => clearTimeout(timer)
  }, [paused, step])
  const pick = (i: number) => { setStep(i); setPaused(true) }

  return (
    <div>
      {/* Wide screens: the trail as a diagram */}
      <div className="relative hidden aspect-[10/12] lg:block">
        <svg viewBox="0 0 1000 1200" preserveAspectRatio="none" className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden="true">
          {LINKS.map((d, i) => (
            <g key={i}>
              <path d={d} fill="none" stroke="rgb(232 240 236 / .14)" strokeWidth="2" strokeDasharray="4 6" vectorEffect="non-scaling-stroke" />
              <motion.path d={d} fill="none" stroke="#3fae84" strokeWidth="2.5" strokeLinecap="round" vectorEffect="non-scaling-stroke"
                           initial={false} animate={{ pathLength: step > i ? 1 : 0, opacity: step > i ? 1 : 0 }}
                           transition={{ duration: reduce ? 0 : 0.8, ease: EASE }} />
            </g>
          ))}
        </svg>
        <Node active={step === 0} icon={FileText} title="Pitch deck · KrishiMitra AI" meta={`p.4 · ${HERO_LINES.length} lines · conf 1.00`}
              className="absolute left-0 top-0 w-[70%]">
          <Slide step={step} reduce={reduce} />
        </Node>
        <Node active={step === 1} icon={Quote} title="Claim" meta="company-reported" className="absolute left-[54%] top-[27%] w-[46%]">
          <ClaimBody step={step} />
        </Node>
        <Node active={step === 2} icon={Globe} title="Market check" meta="web research" className="absolute left-[3%] top-[46%] w-[44%]">
          <CheckBody step={step} />
        </Node>
        <Node active={step === 3} icon={Gauge} title="Rubric score" meta="7 dimensions × 5 judgments" className="absolute left-[56%] top-[59%] w-[44%]">
          <ScoreBody step={step} reduce={reduce} />
        </Node>
      </div>

      {/* Phones and tablets: the same trail, stacked */}
      <div className="space-y-3 lg:hidden">
        <Node active={step === 0} icon={FileText} title="Pitch deck · KrishiMitra AI" meta="p.4"><Slide step={step} reduce={reduce} /></Node>
        <Node active={step === 1} icon={Quote} title="Claim" meta="company-reported"><ClaimBody step={step} /></Node>
        <Node active={step === 2} icon={Globe} title="Market check" meta="web research"><CheckBody step={step} /></Node>
        <Node active={step === 3} icon={Gauge} title="Rubric score" meta="7 dimensions"><ScoreBody step={step} reduce={reduce} /></Node>
      </div>

      <ol className="relative mt-6 grid grid-cols-4 gap-2" aria-label="Steps">
        {STEPS.map((s, i) => (
          <li key={s.key}>
            <button type="button" onClick={() => pick(i)} aria-pressed={step === i} className="group w-full text-left">
              <span className="block h-[3px] overflow-hidden rounded-full bg-white/10">
                <motion.span className="block h-full bg-jade-400" initial={false}
                             animate={{ width: step > i ? '100%' : step === i ? (paused || reduce ? '100%' : ['0%', '100%']) : '0%' }}
                             transition={{ duration: step === i && !paused && !reduce ? 3.4 : 0.3, ease: 'linear' }} />
              </span>
              <span className="mt-2 flex items-baseline gap-1.5">
                <span className="font-mono text-[0.65rem] text-mist-3">0{i + 1}</span>
                <span className={clsx('text-[0.9rem] font-semibold transition-colors', step === i ? 'text-white' : 'text-mist-2 group-hover:text-white')}>{s.label}</span>
              </span>
              <AnimatePresence initial={false}>
                {step === i && (
                  <motion.span initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="mt-0.5 hidden text-[0.75rem] leading-snug text-mist-3 sm:block">
                    {s.note}
                  </motion.span>
                )}
              </AnimatePresence>
            </button>
          </li>
        ))}
      </ol>
    </div>
  )
}
