'use client'

import { useMemo, useState } from 'react'
import { Search } from 'lucide-react'
import { useChunkMap, useExplorerQuery } from '@/lib/api/hooks'
import type { MapPoint } from '@/lib/api/types'
import { errorMessage } from '@/lib/api/client'
import { Badge, Button, Card, EmptyState, Spinner } from '@/components/ui'
import type { DeckCitation } from '@/components/evaluation/EvaluationReport'

const COLOURS = ['#0284c7', '#059669', '#d97706', '#7c3aed', '#e11d48', '#0d9488', '#4f46e5', '#ca8a04', '#db2777', '#475569', '#16a34a', '#ea580c']
const W = 640
const H = 420
const PAD = 18

/** Deck chunks laid out by meaning (UMAP of their 1024-d embeddings). A query lands among its nearest
 * neighbours, with lines to the chunks the HNSW index returns. */
export function EmbeddingMap({ startupId, allStartups, onOpen }: {
  startupId?: string
  allStartups: boolean
  onOpen?: (citation: DeckCitation) => void
}) {
  const map = useChunkMap(allStartups ? undefined : startupId)
  const explore = useExplorerQuery()
  const [text, setText] = useState('')
  const [hover, setHover] = useState<MapPoint | null>(null)
  const points = useMemo(() => map.data?.points ?? [], [map.data])

  const { scale, colourOf, domains } = useMemo(() => {
    const xs = points.map(p => p.x)
    const ys = points.map(p => p.y)
    const [minX, maxX, minY, maxY] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)]
    const domainList = [...new Set(points.map(p => p.domain))].sort()
    return {
      scale: (x: number, y: number) => ({
        cx: PAD + ((x - minX) / (maxX - minX || 1)) * (W - 2 * PAD),
        cy: H - PAD - ((y - minY) / (maxY - minY || 1)) * (H - 2 * PAD),
      }),
      colourOf: (domain: string) => COLOURS[domainList.indexOf(domain) % COLOURS.length],
      domains: domainList,
    }
  }, [points])

  if (map.isPending) return <Spinner label="Loading the embedding map" />
  if (!points.length) return <EmptyState title="No chunks on the map yet">The map appears once documents are processed.</EmptyState>

  const result = explore.data
  const placed = result?.point ? scale(result.point.x, result.point.y) : null
  const neighbours = new Set(result?.neighbours.map(n => n.chunk_id) ?? [])

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <div>
        <form className="flex gap-2 mb-3" onSubmit={e => { e.preventDefault(); if (text.trim().length > 1) explore.mutate({ query: text.trim(), startup_id: allStartups ? undefined : startupId }) }}>
          <input value={text} onChange={e => setText(e.target.value)} placeholder="Ask the index, e.g. “unit economics and payback”"
                 className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm" />
          <Button busy={explore.isPending}><Search className="w-4 h-4" /> Place</Button>
        </form>
        <div className="relative rounded-lg border border-slate-200 bg-white">
          <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img" aria-label="Embedding map of deck chunks">
            {placed && result?.neighbours.map(n => {
              if (n.x == null || n.y == null) return null
              const to = scale(n.x, n.y)
              return <line key={n.chunk_id} x1={placed.cx} y1={placed.cy} x2={to.cx} y2={to.cy} stroke="#0f172a" strokeOpacity={0.25 + n.similarity * 0.5} strokeWidth={1} />
            })}
            {points.map(p => {
              const { cx, cy } = scale(p.x, p.y)
              const mine = !startupId || p.startup_id === startupId
              return (
                <circle key={p.chunk_id} cx={cx} cy={cy} r={neighbours.has(p.chunk_id) ? 6 : mine ? 4.5 : 3}
                        fill={p.injection_suspected ? '#e11d48' : colourOf(p.domain)} fillOpacity={mine ? 0.9 : 0.25}
                        stroke={neighbours.has(p.chunk_id) ? '#0f172a' : 'white'} strokeWidth={neighbours.has(p.chunk_id) ? 1.5 : 0.8}
                        className="cursor-pointer" onMouseEnter={() => setHover(p)} onMouseLeave={() => setHover(null)}
                        onClick={() => onOpen?.({ documentId: p.document_id, page: p.page_no, chunkId: p.chunk_id })} />
              )
            })}
            {placed && (
              <g transform={`translate(${placed.cx} ${placed.cy})`}>
                <circle r={9} fill="#0f172a" />
                <text textAnchor="middle" dy="4" fontSize="11" fill="white" fontWeight="700">Q</text>
              </g>
            )}
          </svg>
          {hover && (
            <div className="pointer-events-none absolute left-3 top-3 max-w-xs rounded-lg border border-slate-200 bg-white/95 p-3 text-xs shadow-lg">
              <p className="font-bold text-slate-900">{hover.startup_name} · p.{hover.page_no}</p>
              {hover.slide_title && <p className="text-slate-600">{hover.slide_title}</p>}
              <p className="mt-1 text-slate-700">{hover.preview}…</p>
            </div>
          )}
        </div>
        <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-slate-600">
          {domains.map(d => <span key={d} className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-full" style={{ background: colourOf(d) }} />{d}</span>)}
          <span className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-rose-600" />hidden instructions</span>
        </div>
      </div>

      <Card title="How the index answered">
        {explore.isError && <p className="text-sm text-rose-700">{errorMessage(explore.error)}</p>}
        {!result && !explore.isError && (
          <p className="text-sm text-slate-600">
            {points.length} chunks, each embedded with text-embedding-3-large (1024 dimensions) and indexed in Qdrant with
            HNSW. Type a question to place it on the map: lines connect it to its ten nearest chunks, and the list
            shows the hybrid ranking (dense + BM25, fused, then re-ranked).
          </p>
        )}
        {result && (
          <div className="space-y-3">
            <div className="flex flex-wrap gap-1.5">
              {result.ann_recall_at_10 != null && <Badge tone={result.ann_recall_at_10 >= 0.99 ? 'green' : 'amber'}>HNSW recall@10 {result.ann_recall_at_10.toFixed(2)}</Badge>}
              {Object.entries(result.timings_ms).map(([k, v]) => <Badge key={k}>{k} {Math.round(v)} ms</Badge>)}
            </div>
            <ol className="space-y-2">
              {result.hits.slice(0, 6).map((hit, i) => (
                <li key={hit.chunk_id} className="rounded-lg border border-slate-200 p-2.5 text-sm">
                  <p className="text-[11px] font-mono text-slate-500">
                    #{i + 1} · {hit.startup_name} p.{hit.page_no} · dense {hit.ranks.dense ?? '–'} · bm25 {hit.ranks.sparse ?? '–'} · fused {hit.ranks.rrf ?? '–'}
                  </p>
                  <p className="mt-1 line-clamp-3 text-slate-800">{hit.text}</p>
                </li>
              ))}
            </ol>
          </div>
        )}
      </Card>
    </div>
  )
}
