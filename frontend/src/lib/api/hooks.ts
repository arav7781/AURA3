'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from './client'
import type {
  Catalogue, ChunkOut, DocumentOut, EvaluationOut, ExplorerQueryResult, LedgerItem, MapPoint, Plan, RankingRow,
  Reviews, StartupCard, StartupDetail,
} from './types'

export interface CatalogueFilters {
  q?: string
  domain?: string
  stage?: string
  min_score?: number
  sort?: 'score' | 'newest' | 'name' | 'ask'
}

function query(params: object): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '' && value !== null) search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

/** 404 / 403 are answers, not failures: no evaluation yet, or the plan does not include it. */
async function maybe<T>(request: Promise<T>): Promise<T | null> {
  try {
    return await request
  } catch (error) {
    if (error instanceof ApiError && (error.status === 404 || error.status === 409)) return null
    throw error
  }
}

export const useCatalogue = (filters: CatalogueFilters) =>
  useQuery({ queryKey: ['catalogue', filters], queryFn: () => api<Catalogue>(`/api/startups${query(filters)}`), placeholderData: prev => prev })

export const useStartup = (ref: string | undefined) =>
  useQuery({ queryKey: ['startup', ref], queryFn: () => api<StartupDetail>(`/api/startups/${ref}`), enabled: !!ref })

export const useEvaluation = (startupId: string | undefined) =>
  useQuery({
    queryKey: ['evaluation', startupId],
    queryFn: () => maybe(api<EvaluationOut>(`/api/startups/${startupId}/evaluation`)),
    enabled: !!startupId,
  })

export const useEvaluations = (startupId: string | undefined) =>
  useQuery({
    queryKey: ['evaluations', startupId],
    queryFn: () => api<{ items: EvaluationOut[] }>(`/api/startups/${startupId}/evaluations`),
    enabled: !!startupId,
  })

export const useDocuments = (startupId: string | undefined) =>
  useQuery({
    queryKey: ['documents', startupId],
    queryFn: () => api<{ items: DocumentOut[]; can_open: boolean }>(`/api/startups/${startupId}/documents`),
    enabled: !!startupId,
  })

export const useDocument = (documentId: string | undefined) =>
  useQuery({ queryKey: ['document', documentId], queryFn: () => api<DocumentOut>(`/api/documents/${documentId}`), enabled: !!documentId })

export const usePageChunks = (documentId: string | undefined, page: number) =>
  useQuery({
    queryKey: ['page-chunks', documentId, page],
    queryFn: () => api<{ items: ChunkOut[] }>(`/api/documents/${documentId}/pages/${page}/chunks`),
    enabled: !!documentId,
  })

export const useChunkMap = (startupId?: string, enabled = true) =>
  useQuery({
    queryKey: ['chunk-map', startupId ?? 'all'],
    queryFn: () => api<{ points: MapPoint[]; projection: Record<string, unknown> | null }>(`/api/explorer/map${query({ startup_id: startupId })}`),
    enabled,
  })

export const useExplorerQuery = () =>
  useMutation({
    mutationFn: (body: { query: string; startup_id?: string; k?: number }) =>
      api<ExplorerQueryResult>('/api/explorer/query', { method: 'POST', body }),
  })

export const useReviews = (startupId: string | undefined) =>
  useQuery({ queryKey: ['reviews', startupId], queryFn: () => api<Reviews>(`/api/startups/${startupId}/reviews`), enabled: !!startupId })

export const useRankings = () =>
  useQuery({ queryKey: ['rankings'], queryFn: () => api<{ board: RankingRow[]; mine: StartupCard[]; ballots: number; method: string }>('/api/rankings') })

export const usePlans = () =>
  useQuery({ queryKey: ['plans'], queryFn: () => api<{ plans: Plan[]; features: Record<string, string>; demo_payments: boolean; auracoin: { note: string }; startup: { success_fee_bps: number } }>('/api/plans'), staleTime: Infinity })

export const useLedger = () =>
  useQuery({ queryKey: ['ledger'], queryFn: () => api<{ items: LedgerItem[]; next_cursor: number | null }>('/api/me/ledger?limit=100') })

export const usePublicStats = () =>
  useQuery({
    queryKey: ['public-stats'],
    queryFn: () => api<{ startups_published: number; investors: number; ac_supply_minor: number; domains: Record<string, number> }>('/api/public/stats'),
  })

/** Invalidate everything that reflects a startup after an owner action. */
export function useRefreshStartup() {
  const client = useQueryClient()
  return (startupId: string) => Promise.all([
    client.invalidateQueries({ queryKey: ['startup'] }),
    client.invalidateQueries({ queryKey: ['evaluation', startupId] }),
    client.invalidateQueries({ queryKey: ['evaluations', startupId] }),
    client.invalidateQueries({ queryKey: ['documents', startupId] }),
    client.invalidateQueries({ queryKey: ['catalogue'] }),
    client.invalidateQueries({ queryKey: ['me'] }),
  ])
}

export async function uploadDocument(startupId: string, file: File, kind = 'deck') {
  const form = new FormData()
  form.append('file', file)
  form.append('kind', kind)
  const response = await fetch(`/api/startups/${startupId}/documents`, {
    method: 'POST', body: form, headers: { 'X-Aura-CSRF': '1' }, credentials: 'same-origin',
  })
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    throw new ApiError(response.status, data?.error?.code ?? `HTTP_${response.status}`, data?.error?.message ?? 'Upload failed', data?.error?.details ?? {})
  }
  return data as { document_id: string; job_id: string }
}
