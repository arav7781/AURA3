// Real output for the hero: TitanOCR's lines on page 4 of the seeded KrishiMitra AI deck (boxes are
// fractions of the page), and the evaluation AURA3 published for it.

export const HERO_PAGE = {
  src: '/hero/krishimitra-p4.webp',
  width: 1754,
  height: 1241,
  cid: 'c:32qwuis',
  ocrSeconds: 5.5,
  pages: 11,
}

export const HERO_LINES: { text: string; box: [number, number, number, number] }[] = [
  { text: "04 \u00b7 MARKET", box: [0.05939, 0.12926, 0.15935, 0.14437] },
  { text: "Market Opportunity (TAM / SAM / SOM)", box: [0.05939, 0.14605, 0.80272, 0.19809] },
  { text: "TAM \u2014 India agriculture IoT: USD 82.3M in 2025,", box: [0.09502, 0.28783, 0.47407, 0.31134] },
  { text: "projected USD 154.8M by 2030 at 13.5% CAGR (Source:", box: [0.09502, 0.3198, 0.52392, 0.3433] },
  { text: "MarketsandMarkets, India Agriculture IoT Market", box: [0.09502, 0.35176, 0.47868, 0.37526] },
  { text: "2025-2030)", box: [0.09502, 0.38373, 0.19187, 0.40723] },
  { text: "SAM \u2014 Marathi/Hindi smallholder segment", box: [0.09502, 0.4862, 0.43316, 0.5097] },
  { text: "(Maharashtra, Karnataka, MP): USD 24.7M in 2025", box: [0.09502, 0.51816, 0.48624, 0.54166] },
  { text: "(company estimate)", box: [0.09502, 0.55012, 0.24915, 0.57363] },
  { text: "SOM \u2014 3-year obtainable share of SAM: USD 3.7M in", box: [0.09502, 0.65259, 0.50761, 0.6761] },
  { text: "2028 (company projection)", box: [0.09502, 0.68456, 0.30494, 0.70806] },
  { text: "India agriculture IoT CAGR: 13.5% (2025-2030)", box: [0.09502, 0.78703, 0.47184, 0.81053] },
  { text: "(Source: MarketsandMarkets)", box: [0.09502, 0.81899, 0.32784, 0.8425] },
]

/** The cited claim: the TAM sentence spans these lines. */
export const CITED_LINES = [2, 3, 4, 5]

/** Where "USD 82.3M in 2025" sits on the page (from the PDF's text layer), for the market check. */
export const HERO_FIGURE: [number, number, number, number] = [0.31984, 0.2932, 0.47409, 0.31672]

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
