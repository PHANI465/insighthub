import client from './client'
import type {
  InsightRow,
  InsightDetail,
  GenerateInsightRequest,
  GenerateInsightResponse,
} from '../types/api'

export async function getInsights(limit = 20, category?: string): Promise<InsightRow[]> {
  const params: Record<string, string | number> = { limit }
  if (category) params.category = category
  const { data } = await client.get<InsightRow[]>('/api/insights', { params })
  return data
}

export async function getInsightDetail(insightId: string): Promise<InsightDetail> {
  const { data } = await client.get<InsightDetail>(`/api/insights/${insightId}`)
  return data
}

export async function generateInsights(
  request: GenerateInsightRequest,
): Promise<GenerateInsightResponse> {
  const { data } = await client.post<GenerateInsightResponse>(
    '/api/insights/generate',
    request,
    { timeout: 180_000 }, // 3 min for all 4 categories
  )
  return data
}
