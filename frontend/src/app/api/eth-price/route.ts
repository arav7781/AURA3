// ETH/USD price with server-side caching and provider fallbacks.
let cachedPrice: { ethereum: { usd: number } } | null = null
let lastFetchTime = 0
const CACHE_DURATION = 60_000 // 60 seconds

const PROVIDERS: { name: string; url: string; read: (data: any) => number }[] = [
  {
    name: 'coingecko',
    url: 'https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd',
    read: data => data?.ethereum?.usd,
  },
  {
    name: 'coinbase',
    url: 'https://api.coinbase.com/v2/prices/ETH-USD/spot',
    read: data => Number(data?.data?.amount),
  },
  {
    name: 'kraken',
    url: 'https://api.kraken.com/0/public/Ticker?pair=ETHUSD',
    read: data => Number(data?.result?.XETHZUSD?.c?.[0]),
  },
]

export async function GET() {
  const now = Date.now()
  if (cachedPrice && now - lastFetchTime < CACHE_DURATION) {
    return Response.json(cachedPrice)
  }

  for (const provider of PROVIDERS) {
    try {
      const res = await fetch(provider.url, { signal: AbortSignal.timeout(5000) })
      if (!res.ok) continue
      const usd = provider.read(await res.json())
      if (Number.isFinite(usd) && usd > 0) {
        cachedPrice = { ethereum: { usd } }
        lastFetchTime = now
        return Response.json(cachedPrice)
      }
    } catch {
      // Blocked, timed out or not JSON (e.g. a proxy login page): try the next provider.
    }
  }

  if (cachedPrice) return Response.json(cachedPrice)
  return Response.json({ error: 'ETH price unavailable from all providers' }, { status: 503 })
}
