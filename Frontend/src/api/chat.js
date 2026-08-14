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

// "Delete conversation" - hides it from MY list only, doesn't touch it for other participants
// (see src/services/chat_service.py::hide_conversation). Reappears automatically on new activity.
export const deleteConversation = (token, conversationId) =>
  apiFetch(`/conversations/${conversationId}`, { method: 'DELETE', token })

// Leaves a group for good - only valid for type "group" (backend 400s for "direct").
export const leaveConversation = (token, conversationId) =>
  apiFetch(`/conversations/${conversationId}/leave`, { method: 'POST', token })

export const addConversationMembers = (token, conversationId, userIds) =>
  apiFetch(`/conversations/${conversationId}/members`, { method: 'POST', token, body: { user_ids: userIds } })

export const getAiPermission = (token, conversationId) =>
  apiFetch(`/conversations/${conversationId}/ai-permission`, { token })

export const setAiPermission = (token, conversationId, granted) =>
  apiFetch(`/conversations/${conversationId}/ai-permission`, { method: 'PUT', token, body: { granted } })
