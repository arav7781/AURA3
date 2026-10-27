import Link from 'next/link'
import { MapPin } from 'lucide-react'
import type { StartupCard as Startup } from '@/lib/api/types'
import { formatINR } from '@/lib/format'
import { Badge, FlagBadges, RecommendationBadge, ScoreRing, STAGE_LABELS } from '@/components/ui'

export function StartupCard({ startup }: { startup: Startup }) {
  return (
    <Link href={`/startups/${startup.slug}`}
          className="group flex flex-col rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition hover:border-jade-600/50 hover:shadow-md">
      <div className="flex items-start gap-4">
        <ScoreRing score={startup.ai_score} size={56} />
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-lg font-black text-slate-900 group-hover:text-jade-600">{startup.name}</h3>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            <Badge tone="jade">{startup.domain}</Badge>
            <Badge>{STAGE_LABELS[startup.stage] ?? startup.stage}</Badge>
            <RecommendationBadge label={startup.recommendation} />
          </div>
        </div>
      </div>
      <p className="mt-3 line-clamp-2 text-sm text-slate-600">{startup.one_liner}</p>
      <div className="mt-auto pt-4 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
        <span className="inline-flex items-center gap-1"><MapPin className="w-3 h-3" />{startup.hq_city ?? 'India'}</span>
        {startup.ask_inr && <span>Raising <b className="text-slate-800">{formatINR(startup.ask_inr)}</b>{startup.pre_money_inr ? ` at ${formatINR(startup.pre_money_inr)} pre` : ''}</span>}
      </div>
      {startup.compliance_flags.length > 0 && <div className="mt-3"><FlagBadges flags={startup.compliance_flags} /></div>}
    </Link>
  )
}
