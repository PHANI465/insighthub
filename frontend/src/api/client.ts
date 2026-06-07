import axios from 'axios'

const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://localhost:8000'

const client = axios.create({
  baseURL: BASE_URL,
  timeout: 120_000, // 2 min — insight generation and RAG can be slow
  headers: { 'Content-Type': 'application/json' },
})

// Inject JWT bearer token on every request
client.interceptors.request.use((config) => {
  const token = localStorage.getItem('insighthub_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// On 401 — clear auth state and redirect to login
client.interceptors.response.use(
  (response) => response,
  (error: unknown) => {
    if (
      axios.isAxiosError(error) &&
      error.response?.status === 401 &&
      window.location.pathname !== '/login'
    ) {
      localStorage.removeItem('insighthub_token')
      localStorage.removeItem('insighthub_user')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  },
)

export default client
