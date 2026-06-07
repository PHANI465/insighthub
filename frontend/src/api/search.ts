import client from './client'
import type { SearchRequest, SearchResponse } from '../types/api'

export async function search(request: SearchRequest): Promise<SearchResponse> {
  const { data } = await client.post<SearchResponse>('/api/search', request, {
    timeout: 60_000,
  })
  return data
}
