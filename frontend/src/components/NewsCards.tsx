'use client'

import { useEffect, useState } from 'react'
import { Newspaper, ExternalLink, TrendingUp, Clock } from 'lucide-react'
import { CardBody, CardContainer, CardItem } from './3d-card'

import { API_BASE } from '@/lib/api'

const CRYPTO_IMAGES = [
  "https://images.unsplash.com/photo-1518544887871-8bcb1c9f1b67?auto=format&fit=crop&w=800&q=80",
  "https://images.unsplash.com/photo-1621761191319-c6fb62004040?auto=format&fit=crop&w=800&q=80",
  "https://images.unsplash.com/photo-1642104704074-907c0698cbd9?auto=format&fit=crop&w=800&q=80",
  "https://images.unsplash.com/photo-1622630998477-20aa696ecb05?auto=format&fit=crop&w=800&q=80",
  "https://images.unsplash.com/photo-1640340434855-6084b1f4901c?auto=format&fit=crop&w=800&q=80",
  "https://images.unsplash.com/photo-1639762681485-074b7f938ba0?auto=format&fit=crop&w=800&q=80",
]

interface NewsArticle {
  article_title?: string
  article_url?: string
  article_photo_url?: string
  source?: string
  post_time_utc?: string
  snippet?: string
  related_symbol?: string
}

const FALLBACK_NEWS: NewsArticle[] = [
  {
    article_title: 'Global equities pause as inflation outlook remains uncertain',
    article_url: 'https://finance.yahoo.com/',
    article_photo_url: CRYPTO_IMAGES[0],
    source: 'Yahoo Finance',
    snippet: 'Macro uncertainty is keeping risk appetite selective across sectors.',
    related_symbol: 'SPY',
  },
  {
    article_title: 'Crypto liquidity improves after renewed institutional interest',
    article_url: 'https://www.coindesk.com/',
    article_photo_url: CRYPTO_IMAGES[1],
    source: 'CoinDesk',
    snippet: 'BTC and ETH flows have picked up alongside derivatives activity.',
    related_symbol: 'BTC',
  },
  {
    article_title: 'Semiconductor leaders stay in focus ahead of earnings cycle',
    article_url: 'https://www.reuters.com/markets/',
    article_photo_url: CRYPTO_IMAGES[2],
    source: 'Reuters',
    snippet: 'Investors are watching AI-related capex trends and forward guidance.',
    related_symbol: 'NVDA',
  },
  {
    article_title: 'Fed signals patience as employment data shows resilience',
    article_url: 'https://www.bloomberg.com/',
    article_photo_url: CRYPTO_IMAGES[3],
    source: 'Bloomberg',
    snippet: 'Markets digesting mixed signals from labor market and CPI data.',
    related_symbol: 'SPX',
  },
  {
    article_title: 'ETF inflows hit monthly record on retail momentum',
    article_url: 'https://finance.yahoo.com/',
    article_photo_url: CRYPTO_IMAGES[4],
    source: 'Yahoo Finance',
    snippet: 'Passive investing continues to absorb volatility as inflows surge.',
    related_symbol: 'QQQ',
  },
  {
    article_title: 'Oil steadies near resistance as OPEC+ holds output steady',
    article_url: 'https://www.reuters.com/',
    article_photo_url: CRYPTO_IMAGES[5],
    source: 'Reuters',
    snippet: 'Energy traders watching demand signals from China and the EU.',
    related_symbol: 'WTI',
  },
]

// ─── Single 3D News Card ─────────────────────────────────────────────────────

function NewsCard3D({ item, index }: { item: NewsArticle; index: number }) {
  const [imgSrc, setImgSrc] = useState(
    item.article_photo_url?.trim()
      ? item.article_photo_url
      : CRYPTO_IMAGES[index % CRYPTO_IMAGES.length]
  )
  const [fallbackCount, setFallbackCount] = useState(0)

  const handleImgError = () => {
    const next = fallbackCount + 1
    setFallbackCount(next)
    if (next === 1) setImgSrc(CRYPTO_IMAGES[(index + 1) % CRYPTO_IMAGES.length])
    else if (next === 2) setImgSrc(`https://picsum.photos/seed/market-${index}/800/600`)
  }

  const formattedDate = item.post_time_utc
    ? new Date(item.post_time_utc).toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      })
    : 'Today'

  return (
    <CardContainer containerClassName="py-0 w-full">
      <CardBody className="relative w-full h-[360px] rounded-2xl border border-slate-200 bg-white hover:border-[#0284c7]/50 hover:shadow-[0_12px_40px_rgba(0,0,0,0.08)] transition-all duration-300 overflow-hidden group/card">

        {/* Image — highest float */}
        <CardItem translateZ={80} className="w-full">
          <div className="relative w-full h-[170px] overflow-hidden rounded-t-2xl">
            <img
              src={imgSrc}
              alt={item.article_title || 'News'}
              onError={handleImgError}
              loading="lazy"
              referrerPolicy="no-referrer"
              className="w-full h-full object-cover opacity-75 group-hover/card:opacity-100 group-hover/card:scale-105 transition-all duration-500"
            />
            {/* Gradient */}
            <div className="absolute inset-0 bg-gradient-to-t from-white via-white/50 to-transparent" />

            {/* Symbol badge */}
            {item.related_symbol && (
              <span className="absolute top-3 left-3 z-10 text-[10px] font-bold font-mono text-[#c084fc] bg-black/75 border border-[#a855f7]/45 px-2.5 py-1 rounded-md tracking-wide">
                ${item.related_symbol}
              </span>
            )}

            {/* Source badge */}
            <span className="absolute top-3 right-3 z-10 text-[9px] font-mono text-[#0284c7] bg-white/90 border border-slate-200 px-2.5 py-1 rounded-md uppercase tracking-widest shadow-sm">
              {item.source || 'News'}
            </span>
          </div>
        </CardItem>

        {/* Title */}
        <CardItem translateZ={50} className="px-4 mt-3 w-full">
          <h3 className="text-[13px] font-semibold text-slate-900 group-hover/card:text-[#0284c7] transition-colors leading-snug line-clamp-2">
            {item.article_title || 'Breaking news...'}
          </h3>
        </CardItem>

        {/* Snippet */}
        {item.snippet && (
          <CardItem translateZ={30} className="px-4 mt-2 w-full">
            <p className="text-[11.5px] text-slate-600 leading-relaxed line-clamp-2">
              {item.snippet}
            </p>
          </CardItem>
        )}

        {/* Footer */}
        <div className="absolute bottom-0 left-0 right-0 px-4 py-3 border-t border-slate-100 flex items-center gap-2 bg-white/80 backdrop-blur-md">
          <CardItem translateZ={20} className="flex items-center gap-2 flex-1 min-w-0">
            <Clock size={11} className="text-slate-400 flex-shrink-0" />
            <span className="text-[10px] font-mono text-slate-500 truncate">
              {formattedDate}
            </span>
          </CardItem>
          <TrendingUp size={11} className="text-emerald-500/60 group-hover/card:text-emerald-500 transition-colors flex-shrink-0" />
          <CardItem
            as="a"
            translateZ={40}
            href={item.article_url || '#'}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 text-[10px] font-mono text-slate-500 hover:text-[#0284c7] transition-colors flex-shrink-0"
          >
            <ExternalLink size={11} />
            <span>Read</span>
          </CardItem>
        </div>
      </CardBody>
    </CardContainer>
  )
}

// ─── Skeleton ────────────────────────────────────────────────────────────────

function SkeletonCard() {
  return (
    <div className="h-[360px] rounded-2xl border border-slate-200 bg-slate-100 animate-pulse" />
  )
}

// ─── Main Export ─────────────────────────────────────────────────────────────

export function NewsCards() {
  const [news, setNews] = useState<NewsArticle[]>([])
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    const fetchNews = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/finance-news/headlines`)
        if (res.ok) {
          const data = await res.json()
          if (data.headlines?.length > 0) {
            const headlines: NewsArticle[] = data.headlines
              .slice(0, 6)
              .map((h: NewsArticle, i: number) => ({
                ...h,
                article_photo_url: h.article_photo_url?.trim()
                  ? h.article_photo_url
                  : CRYPTO_IMAGES[i % CRYPTO_IMAGES.length],
              }))
            setNews(headlines)
            return
          }
        }
      } catch {
        // fall through to fallback
      }
      setNews(FALLBACK_NEWS)
    }
    fetchNews().finally(() => setIsLoading(false))
  }, [])

  return (
    <section className="w-full bg-slate-50 mt-16 pb-10 px-6">

      {/* Header */}
      <div className="flex items-center gap-4 mb-8">
        <div className="w-12 h-12 rounded-xl border border-slate-200 bg-white flex items-center justify-center shadow-sm flex-shrink-0">
          <Newspaper size={22} className="text-[#0284c7]" />
        </div>
        <div>
          <div className="flex items-center gap-3">
            <h2 className="text-sm font-bold text-slate-900 uppercase tracking-widest">
              Live Market Intel
            </h2>
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-400" />
            </span>
          </div>
          <p className="text-[10px] font-mono text-gray-600 uppercase tracking-[0.12em] mt-1">
            Real-time financial headlines · RapidAPI
          </p>
        </div>
      </div>

      {/* Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
        {isLoading
          ? Array.from({ length: 6 }).map((_, i) => <SkeletonCard key={i} />)
          : news.map((item, i) => (
              <NewsCard3D key={i} item={item} index={i} />
            ))}
      </div>
    </section>
  )
}
