'use client'

import { useEffect, useState, useRef } from 'react'
import { TrendingUp, Zap, ExternalLink } from 'lucide-react'

import { API_BASE } from '@/lib/api'

const FALLBACK_HEADLINES: NewsItem[] = [
  {
    article_title: 'Markets remain mixed as investors watch inflation and rate signals.',
    source: 'AURA3 Fallback Feed',
    article_url: 'https://finance.yahoo.com/',
    related_symbol: 'SPY',
  },
  {
    article_title: 'Bitcoin volatility rises with renewed institutional inflows.',
    source: 'AURA3 Fallback Feed',
    article_url: 'https://www.coindesk.com/',
    related_symbol: 'BTC',
  },
  {
    article_title: 'AI sector earnings expected to drive near-term tech sentiment.',
    source: 'AURA3 Fallback Feed',
    article_url: 'https://www.reuters.com/markets/',
    related_symbol: 'NVDA',
  },
]

interface NewsItem {
  article_title?: string
  source?: string
  article_url?: string
  related_symbol?: string
  post_time_utc?: string
}

export function NewsTicker() {
  const [headlines, setHeadlines] = useState<NewsItem[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const fetchHeadlines = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/finance-news/headlines`)
        if (res.ok) {
          const data = await res.json()
          if (data.headlines && data.headlines.length > 0) {
            setHeadlines(data.headlines)
          } else {
            setHeadlines(FALLBACK_HEADLINES)
          }
        } else {
          setHeadlines(FALLBACK_HEADLINES)
        }
      } catch {
        setHeadlines(FALLBACK_HEADLINES)
      } finally {
        setIsLoading(false)
      }
    }

    fetchHeadlines()
  }, [])

  if (isLoading || headlines.length === 0) return null

  // Duplicate headlines for seamless infinite scroll
  const doubledHeadlines = [...headlines, ...headlines]

  return (
    <div className="w-full bg-white/90 backdrop-blur-md border-b border-slate-200 overflow-hidden relative z-40">
      <div className="flex items-center">
        {/* Fixed label */}
        <div className="flex items-center gap-1.5 px-5 py-2.5 bg-gradient-to-r from-slate-100 to-transparent border-r border-slate-200 shrink-0">
          <Zap className="w-4 h-4 text-[#0284c7] animate-pulse" />
          <span className="text-[11px] font-bold font-mono text-[#0284c7] uppercase tracking-widest whitespace-nowrap">
            Live Markets
          </span>
        </div>

        {/* Scrolling headlines */}
        <div className="flex-1 overflow-hidden relative">
          <div
            ref={scrollRef}
            className="flex items-center gap-0 animate-marquee whitespace-nowrap"
            style={{
              animation: `marquee ${Math.max(headlines.length * 4, 30)}s linear infinite`,
            }}
          >
            {doubledHeadlines.map((item, i) => (
              <a
                key={i}
                href={item.article_url || '#'}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2.5 px-6 py-2.5 hover:bg-slate-50 transition-colors group shrink-0"
              >
                {item.related_symbol && (
                  <span className="text-[11px] font-bold font-mono text-purple-700 bg-purple-100 px-2 py-0.5 rounded-sm border border-purple-200">
                    {item.related_symbol}
                  </span>
                )}
                <span className="text-[12px] font-medium text-slate-700 group-hover:text-[#0284c7] transition-colors truncate max-w-[450px]">
                  {item.article_title || 'Breaking news...'}
                </span>
                <TrendingUp className="w-3 h-3 text-emerald-600 shrink-0" />
                <span className="text-[10px] text-slate-500 font-mono shrink-0">
                  {item.source || ''}
                </span>
              </a>
            ))}
          </div>
        </div>
      </div>

      <style jsx>{`
        @keyframes marquee {
          0% { transform: translateX(0); }
          100% { transform: translateX(-50%); }
        }
        .animate-marquee {
          animation: marquee 60s linear infinite;
        }
        .animate-marquee:hover {
          animation-play-state: paused;
        }
      `}</style>
    </div>
  )
}
