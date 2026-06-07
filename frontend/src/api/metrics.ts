import client from './client'
import type {
  KPISummary,
  RevenueTrend,
  CustomerSegmentStat,
  ProductPerformanceRow,
  SupportMetricsRow,
  CampaignROIRow,
} from '../types/api'

export async function getKPISummary(fromDate?: string, toDate?: string): Promise<KPISummary> {
  const params: Record<string, string> = {}
  if (fromDate) params.from_date = fromDate
  if (toDate) params.to_date = toDate
  const { data } = await client.get<KPISummary>('/api/metrics/dashboard', { params })
  return data
}

export async function getRevenueTrend(
  granularity = 'month',
  fromDate?: string,
  toDate?: string,
): Promise<RevenueTrend[]> {
  const params: Record<string, string> = { granularity }
  if (fromDate) params.from_date = fromDate
  if (toDate) params.to_date = toDate
  const { data } = await client.get<RevenueTrend[]>('/api/metrics/revenue', { params })
  return data
}

export async function getCustomerSegments(): Promise<CustomerSegmentStat[]> {
  const { data } = await client.get<CustomerSegmentStat[]>('/api/metrics/customers')
  return data
}

export async function getProductPerformance(
  category?: string,
  limit = 20,
): Promise<ProductPerformanceRow[]> {
  const params: Record<string, string | number> = { limit }
  if (category) params.category = category
  const { data } = await client.get<ProductPerformanceRow[]>('/api/metrics/products', { params })
  return data
}

export async function getSupportMetrics(
  fromDate?: string,
  toDate?: string,
): Promise<SupportMetricsRow[]> {
  const params: Record<string, string> = {}
  if (fromDate) params.from_date = fromDate
  if (toDate) params.to_date = toDate
  const { data } = await client.get<SupportMetricsRow[]>('/api/metrics/support', { params })
  return data
}

export async function getCampaignROI(limit = 20): Promise<CampaignROIRow[]> {
  const { data } = await client.get<CampaignROIRow[]>('/api/metrics/campaigns', {
    params: { limit },
  })
  return data
}
