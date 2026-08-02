import { apiFetch } from './client'

export const listUsers = (token, search) =>
  apiFetch(`/users${search ? `?search=${encodeURIComponent(search)}` : ''}`, { token })

export const listConversations = (token) => apiFetch('/conversations', { token })

export const createConversation = (token, { type, participant_ids, name }) =>
  apiFetch('/conversations', { method: 'POST', token, body: { type, participant_ids, name } })

export const getMessages = (token, conversationId, { before, limit = 50 } = {}) => {
  const params = new URLSearchParams({ limit: String(limit) })
  if (before) params.set('before', before)
  return apiFetch(`/conversations/${conversationId}/messages?${params.toString()}`, { token })
}

export const sendMessage = (token, conversationId, content) =>
  apiFetch(`/conversations/${conversationId}/messages`, { method: 'POST', token, body: { content } })

export const markRead = (token, conversationId) =>
  apiFetch(`/conversations/${conversationId}/read`, { method: 'POST', token })
