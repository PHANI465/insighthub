import client from './client'
import type { LoginRequest, TokenResponse } from '../types/api'

export async function login(credentials: LoginRequest): Promise<TokenResponse> {
  const { data } = await client.post<TokenResponse>('/api/auth/token', credentials)
  return data
}

export function logout(): void {
  localStorage.removeItem('insighthub_token')
  localStorage.removeItem('insighthub_user')
}
