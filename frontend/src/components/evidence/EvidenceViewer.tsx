'use client'

import { useEffect, useMemo, useState } from 'react'
import { ChevronLeft, ChevronRight, ShieldAlert } from 'lucide-react'
import { clsx } from 'clsx'
import { useDocument, useDocuments, usePageChunks } from '@/lib/api/hooks'
import type { ChunkOut } from '@/lib/api/types'
import { Badge, Card, EmptyState, LockedFeature, Spinner } from '@/components/ui'
import type { DeckCitation } from '@/components/evaluation/EvaluationReport'

function boxStyle(bbox: number[]) {
  const [x0, y0, x1, y1] = bbox
  return { left: `${x0 * 100}%`, top: `${y0 * 100}%`, width: `${(x1 - x0) * 100}%`, height: `${(y1 - y0) * 100}%` }
}

function tone(chunk: ChunkOut) {
  if (chunk.injection_suspected) return 'border-rose-500 bg-rose-500/10'
  if (chunk.review || (chunk.conf_min ?? 1) < 0.9) return 'border-amber-500 bg-amber-400/10'
  return 'border-sky-500 bg-sky-400/10'
}

/** A deck page as TitanOCR read it: the page image with every chunk's box, and the chunk text alongside. */
export function EvidenceViewer({ startupId, focus }: { startupId: string; focus: DeckCitation | null }) {
  const documents = useDocuments(startupId)
  const ready = (documents.data?.items ?? []).filter(d => d.status === 'ready')
  const [documentId, setDocumentId] = useState<string | undefined>(focus?.documentId)
  const [page, setPage] = useState(focus?.page ?? 1)
  const [selected, setSelected] = useState<string | null>(focus?.chunkId || null)
  const activeId = documentId ?? focus?.documentId ?? ready[0]?.id
  const document = useDocument(documents.data?.can_open ? activeId : undefined)
  const chunks = usePageChunks(documents.data?.can_open ? activeId : undefined, page)
  const pages = document.data?.pages ?? []
  const pageInfo = pages.find(p => p.page_no === page)

  useEffect(() => {
    if (!focus) return
    // Jump to a citation clicked elsewhere (report chip, map point).
    queueMicrotask(() => {
      setDocumentId(focus.documentId)
      setPage(focus.page)
      setSelected(focus.chunkId)
    })
  }, [focus])

  const items = useMemo(() => chunks.data?.items ?? [], [chunks.data])

  if (documents.isPending) return <Spinner />
  if (!documents.data?.can_open) {
    return <LockedFeature title="Deck evidence viewer">See every slide as TitanOCR read it, with the exact box behind each cited number. Angel plan and above.</LockedFeature>
  }
  if (!ready.length) return <EmptyState title="No processed documents yet" />

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        {ready.length > 1 && (
          <select value={activeId} onChange={e => { setDocumentId(e.target.value); setPage(1) }}
                  className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm">
            {ready.map(d => <option key={d.id} value={d.id}>{d.filename}</option>)}
          </select>
        )}
        <span className="text-sm font-semibold text-slate-800 truncate">{document.data?.filename}</span>
        {document.data?.versions?.titanocr && <Badge tone="sky">TitanOCR {document.data.versions.titanocr}</Badge>}
        {document.data?.ocr_ms != null && <Badge>{(document.data.ocr_ms / 1000).toFixed(1)} s</Badge>}
        {document.data?.flags.map(flag => <Badge key={flag} tone={flag === 'DECK_HIDDEN_INSTRUCTIONS' ? 'red' : 'amber'}>{flag.replace(/_/g, ' ').toLowerCase()}</Badge>)}
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div>
          <div className="relative w-full overflow-hidden rounded-lg border border-slate-200 bg-slate-100"
               style={{ aspectRatio: pageInfo ? `${pageInfo.width} / ${pageInfo.height}` : '297 / 210' }}>
            {pageInfo && (
              // eslint-disable-next-line @next/next/no-img-element -- authenticated API image, not a static asset
              <img src={pageInfo.image_url} alt={`Page ${page}${pageInfo.slide_title ? `: ${pageInfo.slide_title}` : ''}`}
                   className="absolute inset-0 h-full w-full object-contain" />
            )}
            {items.map(chunk => (
              <button key={chunk.id} type="button" onClick={() => setSelected(chunk.id)}
                      title={`${chunk.cid} · confidence ${(chunk.conf_min ?? 1).toFixed(2)}`}
                      className={clsx('absolute border-2 rounded-sm transition-opacity', tone(chunk),
                                      selected && selected !== chunk.id ? 'opacity-25' : 'opacity-100',
                                      selected === chunk.id && 'ring-2 ring-offset-1 ring-[#0284c7]')}
                      style={boxStyle(chunk.bbox)} />
            ))}
          </div>
          <div className="mt-3 flex items-center justify-between">
            <button onClick={() => { setPage(p => Math.max(1, p - 1)); setSelected(null) }} disabled={page <= 1}
                    className="inline-flex items-center gap-1 text-sm font-semibold text-slate-700 disabled:opacity-40">
              <ChevronLeft className="w-4 h-4" /> Previous
            </button>
            <span className="text-sm text-slate-600">
              Page {page} of {pages.length || '…'}
              {pageInfo && <> · {pageInfo.origin === 'digital' ? 'digital text' : `OCR (mean confidence ${(pageInfo.mean_confidence ?? 0).toFixed(2)})`}</>}
              {pageInfo && !pageInfo.geom_exact && ' · boxes approximate'}
            </span>
            <button onClick={() => { setPage(p => Math.min(pages.length || p, p + 1)); setSelected(null) }}
                    disabled={!pages.length || page >= pages.length}
                    className="inline-flex items-center gap-1 text-sm font-semibold text-slate-700 disabled:opacity-40">
              Next <ChevronRight className="w-4 h-4" />
            </button>
          </div>
          <div className="mt-3 flex gap-1.5 overflow-x-auto pb-1">
            {pages.map(p => (
              <button key={p.page_no} onClick={() => { setPage(p.page_no); setSelected(null) }} title={p.slide_title ?? undefined}
                      className={clsx('shrink-0 rounded border px-2 py-1 text-xs', p.page_no === page ? 'border-[#0284c7] bg-sky-50 text-sky-800' : 'border-slate-200 text-slate-600 hover:bg-slate-50')}>
                {p.page_no}
              </button>
            ))}
          </div>
          <p className="mt-2 text-xs text-slate-500">
            <span className="inline-block w-2.5 h-2.5 border-2 border-sky-500 rounded-sm align-middle" /> text ·{' '}
            <span className="inline-block w-2.5 h-2.5 border-2 border-amber-500 rounded-sm align-middle" /> low OCR confidence ·{' '}
            <span className="inline-block w-2.5 h-2.5 border-2 border-rose-500 rounded-sm align-middle" /> possible hidden instructions
          </p>
        </div>

        <Card title={pageInfo?.slide_title ?? `Page ${page}`}>
          {chunks.isPending ? <Spinner /> : (
            <ul className="space-y-3">
              {items.map(chunk => (
                <li key={chunk.id}>
                  <button type="button" onClick={() => setSelected(chunk.id)}
                          className={clsx('w-full rounded-lg border p-3 text-left transition-colors',
                                          selected === chunk.id ? 'border-[#0284c7] bg-sky-50' : 'border-slate-200 hover:bg-slate-50')}>
                    <span className="flex flex-wrap items-center gap-1.5 text-[11px] font-mono text-slate-500">
                      {chunk.cid} · conf {(chunk.conf_min ?? 1).toFixed(2)} · {chunk.origin}
                      {chunk.has_table && <Badge>table</Badge>}
                      {chunk.injection_suspected && <Badge tone="red"><ShieldAlert className="w-3 h-3" /> hidden instructions</Badge>}
                    </span>
                    <span className="mt-1.5 block whitespace-pre-wrap text-sm text-slate-800">{chunk.text}</span>
                  </button>
                </li>
              ))}
              {!items.length && <li className="text-sm text-slate-500">No text was found on this page.</li>}
            </ul>
          )}
        </Card>
      </div>
    </div>
  )
}
