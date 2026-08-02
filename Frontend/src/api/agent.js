import { apiFetch } from './client'

export const chatWithAgent = (token, { message, thread_id, messages }) =>
  apiFetch('/chat', { method: 'POST', token, body: { message, thread_id, messages } })
