'use client'

import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, MotionConfig, motion, useReducedMotion } from 'framer-motion'
import { clsx } from 'clsx'
import type { Box, Desk, DeskFrame } from './desk/scene'
import { CITED_LINES, HERO_EVALUATION, HERO_FIGURE, HERO_LINES, HERO_PAGE } from './heroData'

// The hero: a WebGL desk fills the section and the copy sits over its dark side. Four steps follow one real
// claim from KrishiMitra AI's deck: TitanOCR reads the page, the claim is cited to its lines, its figure is
// checked against the web, and the rubric score it fed. Without WebGL the page is shown as a flat image.

const STEPS = [
  { label: 'Read', note: 'TitanOCR reads each line with its box', ms: 4200 },
  { label: 'Cite', note: 'The claim points back to its lines', ms: 3800 },
  { label: 'Verify', note: 'Its figure is checked on the web', ms: 4200 },
  { label: 'Score', note: 'A fixed rubric turns evidence into a score', ms: 4200 },
] as const
const EASE = [0.16, 1, 0.3, 1] as const
/** The entrance (camera settles, pages and coins land) plays before the first scan. */
const SCAN_DELAY = 1800
const CITED_BOX: Box = [
  Math.min(...CITED_LINES.map(i => HERO_LINES[i].box[0])), Math.min(...CITED_LINES.map(i => HERO_LINES[i].box[1])),
  Math.max(...CITED_LINES.map(i => HERO_LINES[i].box[2])), Math.max(...CITED_LINES.map(i => HERO_LINES[i].box[3])),
]

function ReadNote({ line, done }: { line: React.Ref<HTMLSpanElement>; done: React.Ref<HTMLSpanElement> }) {
  return (
    <div className="flex items-center gap-2.5 whitespace-nowrap px-3 py-2 font-mono text-[0.7rem]">
      <span className="h-1.5 w-1.5 rounded-full bg-jade-300 shadow-[0_0_0_3px_rgb(63_174_132/.25)]" />
      <span ref={line} className="text-mist">TitanOCR · line 1 of {HERO_LINES.length}</span>
      <span ref={done} className="text-mist-3">p.4</span>
    </div>
  )
}

function CiteNote() {
  return (
    <div className="w-[17.5rem] p-4">
      <p className="flex items-center justify-between font-mono text-[0.62rem] uppercase tracking-[0.08em] text-mist-3">
        <span className="text-jade-300">Claim</span><span>company-reported</span>
      </p>
      <p className="mt-2 font-display text-[1.7rem] font-semibold leading-none tracking-[-0.02em] text-white">
        USD 82.3M <span className="text-[0.95rem] font-normal text-mist-2">TAM, 2025</span>
      </p>
      <p className="mt-3 inline-flex rounded-md bg-jade-400/15 px-2 py-1 font-mono text-[0.66rem] text-jade-200 ring-1 ring-jade-400/30">
        [{HERO_PAGE.cid}] → p.4 · lines {CITED_LINES[0] + 1}–{CITED_LINES[CITED_LINES.length - 1] + 1}
      </p>
    </div>
  )
}

function VerifyNote() {
  return (
    <div className="w-[18.5rem] p-4">
      <p className="font-mono text-[0.62rem] uppercase tracking-[0.08em] text-marigold-300">Market check</p>
      <p className="mt-2 flex items-center gap-2 text-[1rem] font-semibold text-white">
        <span className="h-2 w-2 rounded-full bg-marigold-400 shadow-[0_0_0_4px_rgb(238_170_62/.22)]" /> Not independently sourced
      </p>
      <p className="mt-1.5 text-[0.82rem] leading-snug text-mist-2">
        10 web pages read. The deck cites MarketsandMarkets, so the report shows USD 82.3M as the company&apos;s figure.
      </p>
    </div>
  )
}

function ScoreNote({ on }: { on: boolean }) {
  return (
    <div className="w-[17.5rem] p-4">
      <p className="flex items-center justify-between font-mono text-[0.62rem] uppercase tracking-[0.08em] text-mist-3">
        <span className="text-jade-300">Rubric score</span><span>7 dimensions × 5</span>
      </p>
      <p className="mt-2 flex items-baseline gap-2">
        <span className="font-display text-[2.3rem] font-semibold leading-none text-white">{HERO_EVALUATION.score}</span>
        <span className="font-mono text-[0.72rem] text-mist-2">/ 10 · {HERO_EVALUATION.label}</span>
      </p>
      <ul className="mt-3 grid gap-1.5">
        {HERO_EVALUATION.scores.map((s, i) => (
          <li key={s.label} className="grid grid-cols-[5.6rem_minmax(0,1fr)_1.6rem] items-center gap-2 font-mono text-[0.6rem] text-mist-3">
            <span className="truncate">{s.label}</span>
            <span className="block h-[3px] rounded-full bg-white/10">
              <motion.span className="block h-full rounded-full bg-jade-300" initial={false}
                           animate={{ width: on ? `${s.value * 10}%` : '0%' }} transition={{ duration: 0.7, delay: on ? 0.15 + i * 0.05 : 0, ease: EASE }} />
            </span>
            <span className="text-right text-mist">{s.value.toFixed(1)}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** The callout for the current step, laid out in flow (phones, and when WebGL is unavailable). */
function StaticNote({ step }: { step: number }) {
  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div key={step} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.3 }}
                  className="mt-4 w-fit max-w-full rounded-2xl border border-white/10 bg-night/80 backdrop-blur-md [&>div]:w-auto [&>div]:max-w-[22rem]">
        {step === 0 ? (
          <div className="px-4 py-3 font-mono text-[0.72rem] text-mist-2">
            <span className="text-jade-300">TitanOCR</span> · {HERO_LINES.length} lines on p.4 · confidence 1.00 · {HERO_PAGE.ocrSeconds.toFixed(1)} s for {HERO_PAGE.pages} pages
          </div>
        ) : step === 1 ? <CiteNote /> : step === 2 ? <VerifyNote /> : <ScoreNote on />}
      </motion.div>
    </AnimatePresence>
  )
}

// Where each step's callout points on the page, and where the card goes relative to that point.
const PLACE = [
  { dx: 30, dy: -0.5 },
  { dx: -0.62, dy: 74 },
  { dx: -0.18, dy: 86 },
  { dx: 44, dy: -1.08 },
]
function anchorFor(step: number, reveal: number, figure: Box): [number, number] {
  if (step === 0) {
    const read = HERO_LINES.filter(l => l.box[1] < reveal)
    const box = (read.at(-1) ?? HERO_LINES[0]).box
    return [box[2] + 0.012, (box[1] + box[3]) / 2]
  }
  if (step === 1) return [CITED_BOX[2] - 0.06, CITED_BOX[3] + 0.012]
  if (step === 2) return [(figure[0] + figure[2]) / 2, figure[3] + 0.02]
  return [0.97, 0.06]
}

/** The four steps as one segmented control; the active one slides between them and fills as it plays. */
function StepControl({ step, pick, running, ms, ref }: { step: number; pick: (i: number) => void; running: boolean; ms: number; ref: React.Ref<HTMLDivElement> }) {
  return (
    <div ref={ref} role="group" aria-label="How a claim is checked"
         className="relative z-10 grid w-full grid-cols-4 rounded-2xl border border-white/10 bg-[#081a14]/70 p-1 shadow-[0_20px_50px_-30px_rgb(0_0_0/.9)] backdrop-blur-md sm:w-auto sm:self-start lg:self-end">
      {STEPS.map((s, i) => (
        <button key={s.label} type="button" onClick={() => pick(i)} aria-pressed={step === i} title={s.note}
                className="group relative rounded-xl px-3 pb-3 pt-2 text-left sm:px-4">
          {step === i && (
            <motion.span layoutId="hero-step" transition={{ type: 'spring', stiffness: 380, damping: 34 }}
                         className="absolute inset-0 rounded-xl bg-white/[0.08] ring-1 ring-inset ring-white/10" />
          )}
          <span className="relative flex items-baseline gap-1.5">
            <span className="font-mono text-[0.6rem] text-mist-3">0{i + 1}</span>
            <span className={clsx('text-[0.88rem] font-semibold transition-colors', step === i ? 'text-white' : 'text-mist-2 group-hover:text-white')}>{s.label}</span>
          </span>
          {step === i && (
            <span className="absolute inset-x-3 bottom-1.5 h-[2px] overflow-hidden rounded-full bg-white/10 sm:inset-x-4">
              <motion.span key={`${i}-${running}`} className="block h-full rounded-full bg-jade-300"
                           initial={{ width: running ? '0%' : '100%' }} animate={{ width: '100%' }}
                           transition={{ duration: running ? ms / 1000 : 0, ease: 'linear' }} />
            </span>
          )}
        </button>
      ))}
    </div>
  )
}

export function HeroDesk({ children, footer }: { children: React.ReactNode; footer?: React.ReactNode }) {
  const reduce = useReducedMotion()
  const host = useRef<HTMLElement>(null)
  const canvas = useRef<HTMLCanvasElement>(null)
  const slot = useRef<HTMLDivElement>(null)
  const control = useRef<HTMLDivElement>(null)
  const card = useRef<HTMLDivElement>(null)
  const leader = useRef<SVGPathElement>(null)
  const dot = useRef<SVGGElement>(null)
  const readLine = useRef<HTMLSpanElement>(null)
  const readDone = useRef<HTMLSpanElement>(null)
  const desk = useRef<Desk | null>(null)
  const stepRef = useRef(0)
  const [step, setStep] = useState(0)
  const [mode, setMode] = useState<'loading' | 'gl' | 'static'>('loading')
  const [paused, setPaused] = useState(false)
  const [intro, setIntro] = useState(true)

  useEffect(() => {
    let cancelled = false
    let made: Desk | null = null
    const figure = HERO_FIGURE
    const pos = { x: NaN, y: NaN }
    let lastRead = -1

    const onFrame = (f: DeskFrame) => {
      const el = card.current
      if (!el || !slot.current || !host.current) return
      const s = stepRef.current
      const [u, v] = anchorFor(s, f.reveal, figure)
      const [ax, ay] = f.project(u, v)
      const w = el.offsetWidth
      const h = el.offsetHeight
      const p = PLACE[s]
      let x = ax + (Math.abs(p.dx) < 2 ? p.dx * w : p.dx)
      let y = ay + (Math.abs(p.dy) < 2 ? p.dy * h : p.dy)
      const hostRect = host.current.getBoundingClientRect()
      const left = slot.current.getBoundingClientRect().left - hostRect.left - 48
      const below = control.current ? control.current.getBoundingClientRect().bottom - hostRect.top + 14 : 84
      x = Math.min(Math.max(x, left), f.width - w - 20)
      y = Math.min(Math.max(y, below), f.height - h - 24)
      if (Number.isNaN(pos.x) || reduce) { pos.x = x; pos.y = y } else { pos.x += (x - pos.x) * 0.16; pos.y += (y - pos.y) * 0.16 }
      el.style.transform = `translate3d(${pos.x.toFixed(1)}px, ${pos.y.toFixed(1)}px, 0)`
      const ex = Math.min(Math.max(ax, pos.x), pos.x + w)
      const ey = Math.min(Math.max(ay, pos.y), pos.y + h)
      leader.current?.setAttribute('d', `M ${ax.toFixed(1)} ${ay.toFixed(1)} L ${ex.toFixed(1)} ${ey.toFixed(1)}`)
      dot.current?.setAttribute('transform', `translate(${ax.toFixed(1)} ${ay.toFixed(1)})`)
      if (s === 0) {
        const n = HERO_LINES.filter(l => l.box[1] < f.reveal).length
        if (n !== lastRead && readLine.current && readDone.current) {
          lastRead = n
          const done = f.reveal >= 1
          readLine.current.textContent = done ? `TitanOCR · ${HERO_LINES.length} lines read` : n ? `TitanOCR · line ${n} of ${HERO_LINES.length}` : 'TitanOCR · reading p.4'
          readDone.current.textContent = done ? 'conf 1.00' : n ? 'p.4' : ''
        }
      } else lastRead = -1
    }

    import('./desk/scene')
      .then(({ createDesk }) => {
        if (cancelled || !canvas.current || !host.current || !slot.current) return
        made = createDesk({
          canvas: canvas.current,
          host: host.current,
          slot: slot.current,
          pages: { top: HERO_PAGE.src, under: ['/hero/krishimitra-p6.webp', '/hero/krishimitra-p1.webp'] },
          aspect: HERO_PAGE.width / HERO_PAGE.height,
          lines: HERO_LINES.map(l => l.box),
          cited: CITED_LINES,
          figure,
          reduced: !!reduce,
          scanDelay: SCAN_DELAY / 1000,
          onFrame,
        })
        desk.current = made
        made.setStep(stepRef.current)
        return made.ready.then(() => { if (!cancelled) setMode('gl') })
      })
      .catch(() => { if (!cancelled) setMode('static') })
    return () => {
      cancelled = true
      made?.dispose()
      desk.current = null
    }
  }, [reduce])

  useEffect(() => {
    stepRef.current = step
    desk.current?.setStep(step)
  }, [step])

  // The first Read waits for the entrance to finish before its scan starts.
  const ms = STEPS[step].ms + (intro && step === 0 && mode === 'gl' ? SCAN_DELAY : 0)
  const running = !reduce && !paused && mode !== 'loading'
  useEffect(() => {
    if (!running) return
    const timer = setTimeout(() => { setIntro(false); setStep(s => (s + 1) % STEPS.length) }, ms)
    return () => clearTimeout(timer)
  }, [step, running, ms])
  useEffect(() => {
    if (!paused) return
    const timer = setTimeout(() => setPaused(false), 15000)
    return () => clearTimeout(timer)
  }, [paused, step])
  const pick = (i: number) => { setStep(i); setPaused(true); setIntro(false) }
  const accent = step === 2 ? '#eeaa3e' : '#73c4a3'

  return (
    <MotionConfig reducedMotion="user">
      <section ref={host} className="relative isolate overflow-hidden bg-[#06110d] text-mist">
        <canvas ref={canvas} aria-hidden="true"
                className={clsx('absolute inset-0 -z-20 h-full w-full transition-opacity duration-[1600ms] ease-out', mode === 'gl' ? 'opacity-100' : 'opacity-0')} />
        {/* Keep the copy legible: dark on the left (top on phones), a vignette round the edges */}
        <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10 bg-[linear-gradient(180deg,rgb(6_17_13/.95)_0%,rgb(6_17_13/.8)_40%,rgb(6_17_13/0)_62%)] lg:bg-[linear-gradient(90deg,rgb(6_17_13/.96)_0%,rgb(6_17_13/.84)_28%,rgb(6_17_13/.3)_42%,rgb(6_17_13/0)_52%)]" />
        <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(120%_90%_at_70%_55%,transparent_55%,rgb(6_17_13/.7)_100%)]" />
        <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-40 bg-[linear-gradient(180deg,rgb(6_17_13/.75),transparent)]" />

        <div className="mx-auto flex max-w-7xl flex-col px-5 sm:px-8 lg:min-h-[max(800px,100svh)]">
          <div className="grid flex-1 grid-cols-[minmax(0,1fr)] content-center items-center gap-x-6 gap-y-10 pb-10 pt-28 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.08fr)] lg:pb-8 lg:pt-28">
            <div className="relative z-10">{children}</div>
            <motion.div className="flex flex-col" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.8, delay: 0.5, ease: EASE }}>
              <StepControl ref={control} step={step} pick={pick} running={running} ms={ms} />
              <div ref={slot} className="relative mt-5 aspect-[5/4] w-full lg:aspect-[4/3]">
                {mode === 'static' && (
                  // eslint-disable-next-line @next/next/no-img-element -- fixed hero asset
                  <img src={HERO_PAGE.src} alt="Page 4 of the KrishiMitra AI pitch deck"
                       className="absolute inset-x-[4%] top-[12%] w-[92%] rounded-sm shadow-[0_40px_80px_-30px_rgb(0_0_0/.9)] [transform:perspective(1400px)_rotateX(28deg)_rotateZ(-3deg)]" />
                )}
              </div>
              <div className={clsx(mode === 'gl' && 'lg:hidden')}><StaticNote step={step} /></div>
            </motion.div>
          </div>
          {footer && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.8, delay: 0.9 }}
                        className="relative z-10 flex flex-wrap items-center justify-between gap-x-6 gap-y-3 border-t border-white/10 py-5">
              {footer}
            </motion.div>
          )}
        </div>

        {/* Wide screens: the callout floats beside the page, tied to the point it explains */}
        <div aria-live="polite" className={clsx('pointer-events-none absolute inset-0 z-[5] hidden transition-opacity duration-700 lg:block', mode === 'gl' ? 'opacity-100' : 'opacity-0')}>
          <svg className="absolute inset-0 h-full w-full overflow-visible" aria-hidden="true">
            <motion.g key={step} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.4, delay: 0.25 }}>
              <path ref={leader} fill="none" stroke={accent} strokeWidth="1.25" strokeDasharray="3 4" />
              <g ref={dot}>
                <circle r="9" fill={accent} opacity="0.25" className="animate-ping [transform-box:fill-box] [transform-origin:center]" />
                <circle r="4" fill={accent} stroke="#06110d" strokeWidth="2" />
              </g>
            </motion.g>
          </svg>
          <div ref={card} className="absolute left-0 top-0 rounded-2xl border border-white/10 bg-[#081a14]/85 shadow-[0_30px_60px_-30px_rgb(0_0_0/.9)] backdrop-blur-md will-change-transform">
            <AnimatePresence mode="wait" initial={false}>
              <motion.div key={step} initial={{ opacity: 0, y: 6, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -4, scale: 0.98 }} transition={{ duration: 0.3, ease: EASE }}>
                {step === 0 ? <ReadNote line={readLine} done={readDone} /> : step === 1 ? <CiteNote /> : step === 2 ? <VerifyNote /> : <ScoreNote on={step === 3} />}
              </motion.div>
            </AnimatePresence>
          </div>
        </div>
      </section>
    </MotionConfig>
  )
}
