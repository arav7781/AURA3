'use client'

import { useEffect, useRef, useState } from 'react'

// Follows a background job (ingestion, evaluation) over server-sent events. EventSource reconnects on its
// own and resumes with Last-Event-ID, so a dropped connection replays only what was missed.

export interface JobState {
  status: 'idle' | 'running' | 'done' | 'failed'
  stage: string | null
  pct: number
  message: string | null
  log: { stage: string; message: string | null; pct: number }[]
  result: Record<string, unknown> | null
  error: string | null
}

const IDLE: JobState = { status: 'idle', stage: null, pct: 0, message: null, log: [], result: null, error: null }

export function useJob(jobId: string | null | undefined, onFinish?: (state: JobState) => void): JobState {
  const [state, setState] = useState<JobState>(IDLE)
  const onFinishRef = useRef(onFinish)
  useEffect(() => {
    onFinishRef.current = onFinish
  })

  useEffect(() => {
    if (!jobId) return
    let current: JobState = { ...IDLE, status: 'running' }
    let finished = false
    const update = (next: JobState) => {
      current = next
      setState(next)
    }
    queueMicrotask(() => update(current))
    const source = new EventSource(`/api/jobs/${jobId}/events`)
    const data = (event: Event) => JSON.parse((event as MessageEvent).data).data ?? {}

    source.addEventListener('job_progress', event => {
      const d = data(event)
      update({
        ...current, status: 'running', stage: d.stage ?? current.stage, pct: d.pct ?? current.pct,
        message: d.message ?? null,
        log: d.message ? [...current.log, { stage: d.stage, message: d.message, pct: d.pct ?? current.pct }].slice(-40) : current.log,
      })
    })
    const finish = (next: Partial<JobState>) => {
      finished = true
      source.close()
      update({ ...current, ...next })
      onFinishRef.current?.(current)
    }
    source.addEventListener('job_done', event => finish({ status: 'done', pct: 100, result: data(event).result ?? {} }))
    source.addEventListener('job_error', event => finish({ status: 'failed', error: data(event).message ?? 'The job failed' }))
    source.onerror = () => {
      if (finished) source.close() // otherwise EventSource reconnects by itself
    }
    return () => source.close()
  }, [jobId])

  return jobId ? state : IDLE
}
