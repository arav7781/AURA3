'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api/client'

// Copilot conversations. A question starts a run; its events stream over /api/jobs/{run}/events:
// run_start · token · tool_start · tool_end · message · job_done | job_error.

export type Citation =
  | { type: 'deck'; chunk_id: string; document_id: string; page_no: number; slide_title: string | null; startup_slug: string; startup_name: string }
  | { type: 'web'; url: string; title: string }

export type Part =
  | { type: 'text'; text: string }
  | { type: 'notice'; text: string }
  | { type: 'tool'; id: string; name: string; args: Record<string, unknown>; status: 'running' | 'done' | 'error'; card?: Card | null }

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type Card = { type: string; [key: string]: any }

export interface Message {
  id: string
  seq: number
  role: 'user' | 'assistant'
  content: string
  parts: Part[]
  citations: Record<string, Citation>
  status: 'done' | 'failed' | 'cancelled' | 'streaming'
  run_id: string | null
  created_at: string
}

export interface Thread { id: string; title: string; startup_id: string | null; created_at: string; updated_at: string }

export const useThreads = () =>
  useQuery({ queryKey: ['copilot-threads'], queryFn: () => api<{ items: Thread[] }>('/api/copilot/threads') })

export const useThread = (id: string | null) =>
  useQuery({
    queryKey: ['copilot-thread', id],
    queryFn: () => api<{ thread: Thread; messages: Message[]; active_run_id: string | null }>(`/api/copilot/threads/${id}`),
    enabled: !!id,
  })

/** Sends questions and folds the run's events into a live assistant message. */
export function useRun(threadId: string | null) {
  const client = useQueryClient()
  const [live, setLive] = useState<Message | null>(null)
  const [runId, setRunId] = useState<string | null>(null)
  const source = useRef<EventSource | null>(null)

  const finish = useCallback(async (id: string | null) => {
    source.current?.close()
    source.current = null
    setRunId(null)
    await Promise.all([
      client.invalidateQueries({ queryKey: ['copilot-thread', id] }),
      client.invalidateQueries({ queryKey: ['copilot-threads'] }),
      client.invalidateQueries({ queryKey: ['me'] }),
    ])
    setLive(null)
  }, [client])

  const follow = useCallback((run: string, thread: string) => {
    source.current?.close()
    setRunId(run)
    const draft: Message = {
      id: `live-${run}`, seq: Number.MAX_SAFE_INTEGER, role: 'assistant', content: '', parts: [], citations: {},
      status: 'streaming', run_id: run, created_at: new Date().toISOString(),
    }
    setLive(draft)
    const events = new EventSource(`/api/jobs/${run}/events`)
    source.current = events
    const data = (e: Event) => JSON.parse((e as MessageEvent).data).data
    const update = (fn: (m: Message) => Message) => setLive(m => (m ? fn(m) : m))

    events.addEventListener('token', e => {
      const { text } = data(e)
      update(m => {
        const parts = [...m.parts]
        const last = parts[parts.length - 1]
        if (last?.type === 'text') parts[parts.length - 1] = { ...last, text: last.text + text }
        else parts.push({ type: 'text', text })
        return { ...m, parts }
      })
    })
    events.addEventListener('tool_start', e => {
      const { id, name, args } = data(e)
      update(m => ({ ...m, parts: [...m.parts, { type: 'tool', id, name, args, status: 'running' }] }))
    })
    events.addEventListener('tool_end', e => {
      const { id, ok, card } = data(e)
      update(m => ({ ...m, parts: m.parts.map(p => (p.type === 'tool' && p.id === id ? { ...p, status: ok ? 'done' : 'error', card } : p)) }))
    })
    events.addEventListener('message', e => {
      const { parts, citations } = data(e)
      update(m => ({ ...m, parts, citations }))
    })
    events.addEventListener('job_done', () => finish(thread))
    events.addEventListener('job_error', () => finish(thread))
  }, [finish])

  useEffect(() => () => source.current?.close(), [])

  const send = useCallback(async (thread: string, content: string) => {
    const { run_id } = await api<{ run_id: string }>(`/api/copilot/threads/${thread}/messages`, { method: 'POST', body: { content } })
    await client.invalidateQueries({ queryKey: ['copilot-thread', thread] })
    follow(run_id, thread)
  }, [client, follow])

  const stop = useCallback(async () => {
    if (runId) await api(`/api/copilot/runs/${runId}/cancel`, { method: 'POST' }).catch(() => undefined)
  }, [runId])

  return { live: live && live.run_id === runId ? live : null, running: !!runId, send, stop, follow, threadId }
}
