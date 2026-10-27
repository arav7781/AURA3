'use client'

import Link from 'next/link'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { FileText } from 'lucide-react'
import type { Citation, Message } from '@/lib/copilot'
import { BrandMark } from '@/components/Navbar'
import { evidenceHref, ToolCard } from './ToolCard'

/** [c:abc1234] → a page chip that opens the slide; [w:3] → a numbered source link. Unknown refs vanish. */
function linkCitations(text: string, citations: Record<string, Citation>): string {
  return text.replace(/\[([cw]:[a-z0-9]{1,7})\]/g, (_, ref: string) => (citations[ref] ? `[${ref}](#cite-${ref})` : ''))
}

function Markdown({ text, citations }: { text: string; citations: Record<string, Citation> }) {
  return (
    <div className="markdown-content text-[0.95rem] leading-relaxed text-slate-800">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          img: () => null,
          a: ({ href, children }) => {
            const ref = href?.startsWith('#cite-') ? href.slice(6) : null
            const c = ref ? citations[ref] : null
            if (c?.type === 'deck') {
              return (
                <Link href={evidenceHref(c.startup_slug, c.document_id, c.page_no, c.chunk_id)}
                      title={`${c.startup_name}, page ${c.page_no}${c.slide_title ? `: ${c.slide_title}` : ''}`}
                      className="mx-0.5 inline-flex items-center gap-0.5 rounded bg-jade-50 px-1.5 py-px align-baseline text-[0.72rem] font-semibold text-jade-600 no-underline ring-1 ring-jade-200 hover:bg-jade-100">
                  <FileText className="h-3 w-3" />p.{c.page_no}
                </Link>
              )
            }
            if (c?.type === 'web') {
              return (
                <a href={c.url} target="_blank" rel="noopener noreferrer" title={c.title}
                   className="mx-0.5 inline-flex rounded bg-marigold-50 px-1.5 py-px align-baseline text-[0.72rem] font-semibold text-marigold-700 no-underline ring-1 ring-marigold-300 hover:bg-marigold-100">
                  {ref!.slice(2)}
                </a>
              )
            }
            return <a href={href} target="_blank" rel="noopener noreferrer" className="text-jade-600 underline">{children}</a>
          },
        }}
      >
        {linkCitations(text, citations)}
      </ReactMarkdown>
    </div>
  )
}

export function MessageView({ message }: { message: Message }) {
  if (message.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-jade-600 px-4 py-2.5 text-[0.95rem] text-white">{message.content}</div>
      </div>
    )
  }
  const streaming = message.status === 'streaming'
  const empty = message.parts.length === 0
  return (
    <div className="flex gap-3">
      <span className="mt-1 grid h-7 w-7 shrink-0 place-items-center rounded-full bg-ink text-white"><BrandMark className="h-4 w-4" /></span>
      <div className="min-w-0 flex-1 space-y-2.5">
        {empty && streaming && <p className="text-sm text-slate-500">Thinking…</p>}
        {message.parts.map((part, i) => {
          if (part.type === 'tool') return <ToolCard key={part.id} part={part} />
          if (part.type === 'notice') return <p key={i} className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">{part.text}</p>
          return <Markdown key={i} text={part.text} citations={message.citations} />
        })}
        {streaming && !empty && <span className="inline-block h-4 w-1.5 animate-pulse rounded-sm bg-slate-400 align-middle" aria-hidden="true" />}
      </div>
    </div>
  )
}
