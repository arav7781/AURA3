export const API_BASE = (process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8010').replace(/\/$/, '')

export interface StartupSummary {
  startup_id: string
  name: string
  domain: string
  description: string
  team: string
  stage?: string | null
  funding_required?: string | null
  founder_address?: string | null
  created_at: string
  updated_at: string
  documents: { name: string; chunks: number; indexed: number; uploaded_at: string }[]
  verification: {
    cin?: string | null
    mca_verified?: boolean
    company_status?: string | null
    company_name?: string | null
    directors?: string[]
    source?: string
  }
  compliance_flags: string[]
  analysis_status: 'not_started' | 'processing' | 'complete' | 'failed'
  score?: number | null
  recommendation_label?: string | null
}

export interface AnalysisReport {
  score: number
  recommendationLabel: string
  executiveSummary: string
  marketAnalysis: string
  teamAssessment: string
  riskFactors: string
  recommendation: string
  categoryScores: Record<string, number>
  projectedRevenue: { year: number; revenue: number }[]
  marketSizing: {
    tam_usd_b: number
    sam_usd_b: number
    som_usd_b: number
    cagr_pct: number
    basis: string
    trend: { year: number; size_usd_b: number }[]
  }
  sections: { key: string; title: string; content: string }[]
  sources: { title: string; url: string }[]
  complianceFlags: string[]
  generatedAt?: string
  model?: string
}

export interface AnalysisStatus {
  status: 'not_started' | 'processing' | 'complete' | 'failed'
  stage?: string | null
  error?: string | null
  analysis?: AnalysisReport
}

export async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init)
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const detail = (data as { detail?: unknown }).detail
    throw new Error(typeof detail === 'string' ? detail : `Request failed (${res.status})`)
  }
  return data as T
}

export async function downloadReportPdf(startupId: string, filename: string) {
  const res = await fetch(`${API_BASE}/reports/${startupId}`, { method: 'POST' })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error((data as { detail?: string }).detail || 'Could not generate the PDF report')
  }
  const url = window.URL.createObjectURL(await res.blob())
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.URL.revokeObjectURL(url)
}

export const FLAG_LABELS: Record<string, string> = {
  MCA_NOT_VERIFIED: 'Not verified with MCA',
  NAME_MISMATCH: 'Registered name differs',
  NO_DIRECTORS_FOUND: 'No directors on record',
}

export const flagLabel = (flag: string) =>
  FLAG_LABELS[flag] || flag.replace(/^COMPANY_STATUS_/, 'Company status: ').replace(/_/g, ' ')
