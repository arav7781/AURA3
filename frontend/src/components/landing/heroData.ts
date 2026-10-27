// Real output for the hero: TitanOCR's lines on page 4 of the seeded KrishiMitra AI deck (boxes are
// fractions of the page), and the evaluation AURA3 published for it.

export const HERO_PAGE = {
  src: '/hero/krishimitra-p4.webp',
  width: 1754,
  height: 1241,
  cid: 'c:higtc4h',
  ocrSeconds: 6.0,
  pages: 11,
}

export const HERO_LINES: { text: string; box: [number, number, number, number] }[] = [
  { text: 'Market Opportunity (TAM / SAM / SOM)', box: [0.0677, 0.0554, 0.63905, 0.09905] },
  { text: 'TAM — India agriculture IoT: USD 82.3M in 2025, projected USD 154.8M by 2030', box: [0.09383, 0.17795, 0.91287, 0.20984] },
  { text: 'at 13.5% CAGR (Source: MarketsandMarkets, India Agriculture IoT Market', box: [0.09383, 0.22324, 0.84007, 0.25514] },
  { text: '2025-2030)', box: [0.09383, 0.26853, 0.20924, 0.30043] },
  { text: 'SAM — Marathi/Hindi smallholder segment (Maharashtra, Karnataka, MP): USD', box: [0.09383, 0.32977, 0.8952, 0.36167] },
  { text: '24.7M in 2025 (company estimate)', box: [0.09383, 0.37507, 0.44126, 0.40696] },
  { text: 'SOM — 3-year obtainable share of SAM: USD 3.7M in 2028 (company projection)', box: [0.09383, 0.43631, 0.91159, 0.4682] },
  { text: 'India agriculture IoT CAGR: 13.5% (2025-2030) (Source: MarketsandMarkets)', box: [0.09383, 0.49755, 0.87395, 0.52945] },
]

/** The cited claim: the TAM sentence spans these lines. */
export const CITED_LINES = [1, 2, 3]

export const HERO_EVALUATION = {
  score: 6.2,
  label: 'Hold',
  scores: [
    { label: 'Business model', value: 7.3 },
    { label: 'Traction', value: 6.7 },
    { label: 'Product', value: 6.0 },
    { label: 'Market', value: 6.0 },
    { label: 'Team', value: 6.0 },
    { label: 'Execution risk', value: 6.0 },
    { label: 'Moat', value: 5.3 },
  ],
}
