'use client'

import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { ArrowDown, ArrowUpRight } from 'lucide-react'
import { clsx } from 'clsx'
import { CITED_LINES, HERO_EVALUATION, HERO_LINES, HERO_PAGE } from './heroData'

const STEPS = ['Read', 'Cite', 'Verify', 'Score'] as const
type Step = 0 | 1 | 2 | 3
const VIEW_W = 1000
const VIEW_H = (VIEW_W * HERO_PAGE.height) / HERO_PAGE.width
const EASE = [0.16, 1, 0.3, 1] as const

const DESK = {
  background: [
    'repeating-linear-gradient(90deg, rgb(0 0 0 / .13) 0 1px, transparent 1px 7px)',
    'repeating-linear-gradient(90deg, rgb(255 226 196 / .04) 0 2px, transparent 2px 23px)',
    'repeating-linear-gradient(90deg, rgb(0 0 0 / .32) 0 2px, transparent 2px 190px)',
    'radial-gradient(42% 52% at 72% 52%, rgb(255 214 170 / .14), transparent 70%)',
    'radial-gradient(70% 80% at 70% 40%, var(--color-desk-hi) 0%, var(--color-desk-mid) 55%, var(--color-desk-lo) 100%)',
  ].join(','),
}
const SHADE = {
  background: [
    'linear-gradient(90deg, rgb(16 10 5 / .86) 0%, rgb(16 10 5 / .62) 30%, rgb(16 10 5 / .14) 52%, rgb(16 10 5 / 0) 62%)',
    'linear-gradient(0deg, rgb(16 10 5 / .45) 0%, rgb(16 10 5 / 0) 24%)',
    'linear-gradient(180deg, rgb(16 10 5 / .55) 0, rgb(16 10 5 / 0) 150px)',
  ].join(','),
}

/** The headline is read too: each word gets its own box and on-screen coordinates, then they fade. */
function ReadHeadline({ lines, animate }: { lines: string[]; animate: boolean }) {
  const ref = useRef<HTMLHeadingElement>(null)
  const [boxes, setBoxes] = useState<{ x: number; y: number; w: number; h: number }[]>([])
  useLayoutEffect(() => {
    if (!animate || !ref.current) return
    const root = ref.current.getBoundingClientRect()
    const measured = [...ref.current.querySelectorAll<HTMLElement>('[data-word]')].map(word => {
      const r = word.getBoundingClientRect()
      return { x: r.left - root.left, y: r.top - root.top, w: r.width, h: r.height }
    })
    queueMicrotask(() => setBoxes(measured))
  }, [animate])
  return (
    <h1 ref={ref} className="relative mb-6 font-display text-[clamp(3.1rem,7vw,7.2rem)] font-[820] leading-[0.9] tracking-[-0.048em] text-hero-ink [text-shadow:0_2px_30px_rgb(0_0_0/.35)]">
      {lines.map(line => (
        <span key={line} className="block pb-[0.04em]">
          {line.split(' ').map((word, i) => (
            <span key={i}>{i > 0 && ' '}<span data-word className="inline-block">{word}</span></span>
          ))}
        </span>
      ))}
      {boxes.map((b, i) => (
        <motion.span key={i} aria-hidden="true" className="pointer-events-none absolute rounded border-[1.5px] border-hero-accent bg-[rgb(163_180_255/.12)]"
                     style={{ left: b.x - 4, top: b.y + b.h * 0.08, width: b.w - 10, height: b.h * 0.86 }}
                     initial={{ opacity: 0, scaleX: 0.4 }} animate={{ opacity: [0, 1, 1, 0], scaleX: 1 }}
                     transition={{ duration: 3.2, delay: 0.5 + i * 0.12, times: [0, 0.12, 0.75, 1], ease: EASE }}>
          <span className="absolute -top-5 left-0 whitespace-nowrap font-mono text-[0.62rem] font-medium text-hero-accent">
            {Math.round(b.x)},{Math.round(b.y)}
          </span>
        </motion.span>
      ))}
    </h1>
  )
}

function Tag({ x, y, tone = 'cobalt', children }: { x: number; y: number; tone?: 'cobalt' | 'amber'; children: React.ReactNode }) {
  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.4, ease: EASE }}
                className={clsx('absolute z-10 inline-flex -translate-y-[calc(100%+6px)] items-baseline gap-2 whitespace-nowrap rounded-md px-2 py-1.5 font-mono text-[clamp(0.5rem,0.75vw,0.66rem)] font-medium shadow-[0_8px_20px_-8px_rgb(10_20_50/.6)]',
                  tone === 'cobalt' ? 'bg-cobalt text-[#fbfbfc]' : 'bg-[#c77700] text-white')}
                style={{ left: `${x * 100}%`, top: `${y * 100}%` }}>
      {children}
    </motion.div>
  )
}

export function DeskHero({ signedInHome }: { signedInHome: string | null }) {
  const reduce = useReducedMotion()
  const [step, setStep] = useState<Step>(0)
  const [paused, setPaused] = useState(false)

  useEffect(() => {
    if (reduce || paused) return
    const timer = setInterval(() => setStep(s => ((s + 1) % STEPS.length) as Step), 3800)
    return () => clearInterval(timer)
  }, [reduce, paused])

  useEffect(() => {
    if (!paused) return
    const timer = setTimeout(() => setPaused(false), 15000) // a picked step stays up a while, then the loop resumes
    return () => clearTimeout(timer)
  }, [paused, step])

  const pick = (i: number) => {
    setStep(i as Step)
    setPaused(true)
  }

  const highlight = (i: number) =>
    step === 0 ? 1 : step === 1 || step === 2 ? (CITED_LINES.includes(i) ? 1 : 0.18) : 0.12
  const first = HERO_LINES[CITED_LINES[0]].box

  return (
    <section className="relative isolate overflow-hidden bg-desk-lo text-hero-ink">
      <div className="absolute inset-0 -z-10" style={DESK} aria-hidden="true" />
      <div className="pointer-events-none absolute inset-0 z-[1]" style={SHADE} aria-hidden="true" />

      <div className="relative z-[2] mx-auto grid min-h-[max(700px,100svh)] max-w-7xl items-center gap-10 px-5 pb-12 pt-28 sm:px-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,0.98fr)] lg:gap-14">
        <div className="min-w-0">
          <p className="mb-7 inline-flex items-center gap-3 font-mono text-[0.72rem] font-medium uppercase tracking-[0.06em] text-hero-ink-3">
            <span className="h-[1.5px] w-8 bg-hero-accent" aria-hidden="true" />
            AI due diligence for Indian startups
          </p>
          <ReadHeadline lines={['Diligence', 'that shows', 'its work.']} animate={!reduce} />
          <p className="mb-9 max-w-[33ch] text-[clamp(1.06rem,1.3vw,1.26rem)] leading-[1.55] text-hero-ink-2">
            AURA3 reads every pitch deck with TitanOCR, researches and scores it against a fixed rubric, and links
            each claim to the exact line on the slide. Investors review, rank and back startups with AuraCoin.
          </p>
          <div className="flex flex-wrap items-center gap-3">
            {signedInHome ? (
              <Link href={signedInHome} className="group inline-flex h-[54px] items-center gap-3 rounded-full bg-cobalt-bright pl-6 pr-3 text-base font-semibold text-[#fbfbfe] transition-colors hover:bg-[#4560ff]">
                Go to your dashboard <span className="grid h-7 w-7 place-items-center rounded-full bg-white/15"><ArrowUpRight className="h-4 w-4" /></span>
              </Link>
            ) : (
              <>
                <Link href="/register?role=investor" className="group inline-flex h-[54px] items-center gap-3 rounded-full bg-cobalt-bright pl-6 pr-3 text-base font-semibold text-[#fbfbfe] transition-colors hover:bg-[#4560ff]">
                  Start investing <span className="grid h-7 w-7 place-items-center rounded-full bg-white/15 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5"><ArrowUpRight className="h-4 w-4" /></span>
                </Link>
                <Link href="/register?role=startup" className="inline-flex h-[54px] items-center gap-3 rounded-full border border-[rgb(255_240_225/.34)] bg-[rgb(20_12_6/.28)] pl-6 pr-3 text-base font-semibold text-hero-ink transition-colors hover:border-[rgb(255_240_225/.7)]">
                  List your startup <span className="grid h-7 w-7 place-items-center rounded-full bg-white/10"><ArrowUpRight className="h-4 w-4" /></span>
                </Link>
              </>
            )}
            <a href="#how" className="inline-flex h-[54px] items-center gap-2 px-3 text-[0.95rem] font-medium text-hero-ink-2 hover:text-hero-ink">
              See how it works <ArrowDown className="h-4 w-4" />
            </a>
          </div>
          {!signedInHome && (
            <p className="mt-5 font-mono text-[0.7rem] text-hero-ink-3">
              Demo: <Link href="/login" className="underline decoration-hero-ink-3/50 underline-offset-4 hover:text-hero-ink">sign in with a seeded account</Link>, 25 startups and 6 investors inside.
            </p>
          )}
        </div>

        <div className="relative h-[min(calc(100svh-170px),660px)] min-h-[420px]">
          <ol aria-label="Show a step" className="absolute left-1/2 top-0 z-20 flex -translate-x-1/2 gap-0.5 rounded-full bg-[rgb(16_10_6/.66)] p-1 shadow-[inset_0_1px_0_rgb(255_255_255/.08),0_12px_30px_-12px_rgb(0_0_0/.6)]">
            {STEPS.map((label, i) => (
              <li key={label}>
                <button type="button" onClick={() => pick(i)} aria-pressed={step === i}
                        className={clsx('rounded-full px-3.5 py-2 font-mono text-[0.68rem] font-medium transition-colors duration-300',
                          step === i ? 'bg-[#fbfbfc] text-ink' : 'text-[rgb(255_238_218/.62)] hover:text-hero-ink')}>
                  {label}
                </button>
              </li>
            ))}
          </ol>

          <div className="absolute inset-0 flex items-center justify-center [perspective:1800px]">
            <motion.div
              className="relative w-[94%] max-w-[660px] [transform-style:preserve-3d]"
              initial={reduce ? false : { opacity: 0, y: 60, rotateX: 34, rotateY: -22, rotateZ: 12 }}
              animate={{ opacity: 1, y: 0, rotateX: 20, rotateY: -15, rotateZ: 5 }}
              transition={{ duration: 1.4, ease: EASE }}
            >
              {/* eslint-disable-next-line @next/next/no-img-element -- fixed-size hero asset, rendered in 3D */}
              <img src={HERO_PAGE.src} alt="Page 4 of the KrishiMitra AI pitch deck: market opportunity" width={HERO_PAGE.width} height={HERO_PAGE.height}
                   className="block h-auto w-full rounded-[3px] shadow-[0_44px_80px_-28px_rgb(0_0_0/.85),0_18px_30px_-18px_rgb(0_0_0/.6)]" />
              <svg viewBox={`0 0 ${VIEW_W} ${VIEW_H}`} preserveAspectRatio="none" className="absolute inset-0 h-full w-full overflow-visible" aria-hidden="true">
                <defs>
                  <linearGradient id="beam" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0" stopColor="#2f48d8" stopOpacity="0" />
                    <stop offset=".8" stopColor="#2f48d8" stopOpacity=".14" />
                    <stop offset="1" stopColor="#2f48d8" stopOpacity=".55" />
                  </linearGradient>
                </defs>
                {HERO_LINES.map((line, i) => {
                  const [x0, y0, x1, y1] = line.box
                  return (
                    <motion.rect key={i} x={x0 * VIEW_W - 4} y={y0 * VIEW_H - 3} width={(x1 - x0) * VIEW_W + 8} height={(y1 - y0) * VIEW_H + 6} rx={3}
                                 fill="rgb(47 72 216 / .13)" stroke="#2f48d8" strokeWidth={1.4} vectorEffect="non-scaling-stroke"
                                 initial={{ opacity: 0 }} animate={{ opacity: highlight(i) }}
                                 transition={{ duration: 0.45, delay: step === 0 && !reduce ? 0.25 + i * 0.13 : 0 }} />
                  )
                })}
                {step === 0 && !reduce && (
                  <motion.g key="beam" initial={{ y: -VIEW_H * 0.35 }} animate={{ y: VIEW_H }} transition={{ duration: 1.6, ease: 'linear' }}>
                    <rect x={0} y={-VIEW_H * 0.3} width={VIEW_W} height={VIEW_H * 0.3} fill="url(#beam)" />
                    <rect x={0} y={-3} width={VIEW_W} height={4} fill="#2f48d8" />
                  </motion.g>
                )}
              </svg>
              <div className="absolute inset-0">
                <AnimatePresence mode="wait">
                  {step === 0 && <Tag key="read" x={HERO_LINES[0].box[0]} y={HERO_LINES[0].box[1]}>line 1 <i className="not-italic opacity-70">conf 1.00 · digital</i></Tag>}
                  {step === 1 && <Tag key="cite" x={first[0]} y={first[1]}>{HERO_PAGE.cid} <i className="not-italic opacity-70">p.4 · cited in the report</i></Tag>}
                  {step === 2 && <Tag key="verify" x={first[0]} y={first[1]} tone="amber">Deck claim USD 82.3M (2025) <i className="not-italic opacity-80">no independent source</i></Tag>}
                </AnimatePresence>
              </div>
            </motion.div>
          </div>

          <AnimatePresence mode="wait">
            <motion.div key={step} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.45, ease: EASE }}
                        className="absolute right-0 top-[12%] z-20 grid w-[min(15.5rem,62vw)] gap-1 rounded-xl bg-[#fbfbfc] px-4 py-3.5 text-ink shadow-[0_18px_40px_-16px_rgb(0_0_0/.65)] sm:-right-2">
              {step === 0 && <><b className="text-[1.5rem] font-[650] leading-none tracking-[-0.015em]">{HERO_LINES.length} lines</b><span className="font-mono text-[0.66rem] leading-snug text-ink-3">on this slide · {HERO_PAGE.pages} pages read in {HERO_PAGE.ocrSeconds.toFixed(1)} s on the CPU</span></>}
              {step === 1 && <><b className="text-[1.15rem] font-[650] leading-tight">Every claim is cited</b><span className="font-mono text-[0.66rem] leading-snug text-ink-3">click a citation in the report and this box lights up</span></>}
              {step === 2 && <><b className="text-[1.15rem] font-[650] leading-tight">Checked against the web</b><span className="font-mono text-[0.66rem] leading-snug text-ink-3">10 sources read · the TAM is flagged as the company&apos;s own figure</span></>}
              {step === 3 && (
                <>
                  <span className="flex items-baseline gap-2"><b className="text-[1.9rem] font-[650] leading-none tracking-[-0.02em]">{HERO_EVALUATION.score}</b><span className="font-mono text-[0.7rem] text-ink-3">/ 10 · {HERO_EVALUATION.label}</span></span>
                  <ul className="mt-1.5 grid gap-1">
                    {HERO_EVALUATION.scores.map(s => (
                      <li key={s.label} className="grid grid-cols-[6.5rem_1fr_1.6rem] items-center gap-2 font-mono text-[0.6rem] text-ink-3">
                        <span className="truncate">{s.label}</span>
                        <span className="block h-1.5 rounded-full bg-[#e6e9ee]"><motion.span className="block h-1.5 rounded-full bg-cobalt" initial={{ width: 0 }} animate={{ width: `${s.value * 10}%` }} transition={{ duration: 0.8, ease: EASE }} /></span>
                        <span className="text-right text-ink">{s.value.toFixed(1)}</span>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </motion.div>
          </AnimatePresence>

          <div className="absolute bottom-[10%] left-0 z-20 grid gap-1 rounded-xl bg-[#fbfbfc] px-4 py-3.5 text-ink shadow-[0_18px_40px_-16px_rgb(0_0_0/.65)] sm:-left-2">
            <b className="text-[1.5rem] font-[650] leading-none tracking-[-0.015em]">1.00</b>
            <span className="font-mono text-[0.66rem] text-ink-3">mean OCR confidence · KrishiMitra AI, p.4</span>
          </div>
        </div>
      </div>
    </section>
  )
}
