const browserOrigin = window.location.origin
const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || `${browserOrigin}/api/v1`
export const WS_BASE_URL = import.meta.env.VITE_WS_BASE_URL || `${wsProtocol}//${window.location.host}/api/v1/ws`

export class ApiError extends Error {
  constructor(status, detail) {
    super(typeof detail === 'string' ? detail : 'Request failed')
    this.status = status
    this.detail = detail
  }
}

export async function apiFetch(path, { method = 'GET', body, token } = {}) {
  const headers = { 'Content-Type': 'application/json' }
  if (token) headers.Authorization = `Bearer ${token}`
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    const payload = await res.json().catch(() => null)
    throw new ApiError(res.status, payload?.detail || res.statusText)
  }
  if (res.status === 204) return null
  return res.json()
}
