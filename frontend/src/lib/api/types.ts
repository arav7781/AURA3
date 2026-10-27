// Shapes returned by the AURA-3 API (backend/aura/api/routes).

export type Stage = 'pre_seed' | 'seed' | 'series_a' | 'series_b'
export type Recommendation = 'Strong Buy' | 'Buy' | 'Hold' | 'Pass' | 'Insufficient data'

export interface StartupCard {
  id: string
  slug: string
  name: string
  domain: string
  stage: Stage
  one_liner: string
  hq_city: string | null
  ask_inr: number | null
  pre_money_inr: number | null
  ai_score: number | null
  recommendation: Recommendation | null
  mca_status: string | null
  compliance_flags: string[]
  status: 'draft' | 'published'
  published_at: string | null
}

export interface TeamMember { name: string; role: string; background?: string }

export interface RoundTerms {
  ask_inr: number
  pre_money_inr: number
  min_raise_pct: number
  use_of_funds: { category: string; pct: number }[]
  tranches: { pct: number; title: string; criteria?: string | null; due_days?: number | null }[]
}

export interface StartupDetail extends StartupCard {
  legal_name: string | null
  sub_domain: string | null
  description: string
  profile: {
    team?: TeamMember[]
    competitors?: { name: string; positioning: string }[]
    gtm?: { channels: string[]; target: string }
    round?: RoundTerms
    traction_as_of?: string
  }
  hq_state: string | null
  founded_year: number | null
  cin: string | null
  mca: {
    cin?: string | null
    mca_verified?: boolean
    company_status?: string | null
    company_name?: string | null
    directors?: string[]
    state?: string | null
    source?: string | null
    reason?: string
  }
  latest_evaluation_id: string | null
  is_owner: boolean
}

export interface Catalogue {
  items: StartupCard[]
  facets: { domains: Record<string, number>; stages: Record<string, number> }
}

export interface Citation {
  cid: string
  chunk_id: string
  document_id: string
  page_no: number
  bbox: number[]
}

export type MetricKind = 'reported' | 'source_forecast' | 'company_reported' | 'company_estimate' | 'company_forecast'

export interface Metric {
  value: number
  unit: string
  kind: MetricKind
  year: number | null
  period: string
  quote: string
  source_url: string | null
  source_title: string
  retrieved_at: string | null
  market: string
  geography: string
  citation: Citation | null
  low_confidence: boolean
}

export interface Claim extends Metric {
  currency: string
  normalised: number
  check: { status: 'unverified' | 'consistent' | 'differs' | 'different_period' | 'different_currency'; source_value?: number; ratio?: number }
}

export type ReportCitation =
  | { type: 'deck'; chunk_id: string; document_id: string; page_no: number; slide_title: string | null; bbox: number[] }
  | { type: 'web'; url: string; title: string }

export interface Report {
  score: number | null
  recommendationLabel: Recommendation
  executiveSummary: string
  categoryScores: Record<string, number>
  complianceFlags: string[]
  generatedAt: string | null
  model: string | null
  rubricVersion: string | null
  citations: Record<string, ReportCitation>
  redacted: boolean
  marketAnalysis?: string
  scoreRationales?: Record<string, string>
  scoreSpread?: Record<string, number>
  projectedRevenue?: (Metric & { revenue: number; metric: string })[]
  revenueCurrency?: string | null
  revenueMetric?: string | null
  dataGaps?: string[]
  researchStatus?: 'sources_found' | 'unavailable'
  marketSizing?: {
    tam_usd_b: number | null
    sam_usd_b: number | null
    som_usd_b: number | null
    cagr_pct: number | null
    evidence: Record<string, Metric>
    claims: Record<string, Claim>
    trend: (Metric & { size_usd_b: number })[]
    basis: string
  }
  sections?: { key: string; title: string; content: string }[]
  sources?: { title: string; url: string; snippet: string; retrieved_at: string }[]
  rewrites?: number
}

export interface EvaluationOut {
  id: string
  version: number
  status: 'queued' | 'running' | 'complete' | 'failed'
  stage: string | null
  error: string | null
  visibility: 'private' | 'published'
  job_id: string | null
  source: string
  created_at: string
  completed_at: string | null
  report: Report | null
  score?: number | null  // list endpoint only
  recommendation?: Recommendation | null
}

export interface DocumentPage {
  page_no: number
  width: number
  height: number
  origin: string
  mean_confidence: number | null
  review_required: boolean
  geom_exact: boolean
  slide_title: string | null
  image_url: string
}

export interface DocumentOut {
  id: string
  startup_id: string
  kind: string
  filename: string
  size_bytes: number
  status: 'uploaded' | 'processing' | 'ready' | 'failed'
  visibility: string
  page_count: number | null
  review_required: boolean
  flags: string[]
  versions: Record<string, string>
  ocr_ms: number | null
  error: string | null
  job_id: string | null
  created_at: string
  pages?: DocumentPage[]
  chunk_count?: number
}

export interface ChunkLine { bbox: number[]; text?: string; conf?: number }

export interface ChunkOut {
  id: string
  cid: string
  document_id: string
  page_no: number
  slide_title: string | null
  text: string
  bbox: number[]
  geom_exact: boolean
  origin: string
  conf_min: number | null
  conf_mean: number | null
  review: boolean
  has_table: boolean
  injection_suspected: boolean
  lines?: ChunkLine[]
}

export interface MapPoint {
  chunk_id: string
  cid: string
  startup_id: string
  startup_name: string
  domain: string
  document_id: string
  page_no: number
  slide_title: string | null
  preview: string
  x: number
  y: number
  origin: string
  review: boolean
  injection_suspected: boolean
}

export interface ExplorerQueryResult {
  query: string
  point: { x: number; y: number } | null
  neighbours: { chunk_id: string; cid: string; similarity: number; x: number | null; y: number | null; page_no: number; startup_name: string }[]
  ann_recall_at_10: number | null
  hits: { chunk_id: string; cid: string; startup_name: string; page_no: number; slide_title: string | null; text: string; ranks: Record<string, number | null>; scores: Record<string, number | null> }[]
  timings_ms: Record<string, number>
}

export interface ReviewOut {
  id: string
  team: number
  market: number
  product: number
  traction: number
  note: string
  average: number
  reviewer: { name: string; plan?: string | null }
  created_at: string
}

export interface Reviews {
  items: ReviewOut[]
  summary: { count: number; team?: number; market?: number; product?: number; traction?: number; average?: number }
  mine: ReviewOut | null
}

export interface RankingRow extends StartupCard {
  community_score: number
  community_rank: number
  rankers: number
  ai_rank: number | null
  rank_gap: number | null
}

export interface LedgerItem {
  id: number
  tx_id: string
  kind: string
  account: string
  amount_minor: number
  memo: string | null
  ref_type: string | null
  ref_id: string | null
  created_at: string
}

export interface Plan {
  id: 'scout' | 'angel' | 'syndicate'
  name: string
  price_inr_month: number
  monthly_ac: number
  welcome_ac: number
  copilot_daily: number | null
  sandbox_daily: number
  features: string[]
  blurb: string
}
