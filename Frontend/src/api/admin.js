import { apiFetch } from './client'

export const getStats = (token) => apiFetch('/admin/stats', { token })

export const updateDailyTokenBudget = (token, dailyTokenBudget) =>
  apiFetch('/admin/settings/budget', { method: 'PATCH', token, body: { daily_token_budget: dailyTokenBudget } })

export const listUsers = (token, q) =>
  apiFetch(`/admin/users${q ? `?q=${encodeURIComponent(q)}` : ''}`, { token })

export const updateUserRole = (token, userId, role) =>
  apiFetch(`/admin/users/${userId}/role`, { method: 'PATCH', token, body: { role } })

export const updateUserStatus = (token, userId, is_active) =>
  apiFetch(`/admin/users/${userId}/status`, { method: 'PATCH', token, body: { is_active } })

export const listConversations = (token) => apiFetch('/admin/conversations', { token })

export const getConversationMessages = (token, conversationId) =>
  apiFetch(`/admin/conversations/${conversationId}/messages`, { token })

export const deleteConversation = (token, conversationId) =>
  apiFetch(`/admin/conversations/${conversationId}`, { method: 'DELETE', token })

export const listTasks = (token, ownerId) =>
  apiFetch(`/admin/tasks${ownerId ? `?owner_id=${encodeURIComponent(ownerId)}` : ''}`, { token })

export const deleteTask = (token, taskId) =>
  apiFetch(`/admin/tasks/${taskId}`, { method: 'DELETE', token })

export const listReminders = (token, ownerId) =>
  apiFetch(`/admin/reminders${ownerId ? `?owner_id=${encodeURIComponent(ownerId)}` : ''}`, { token })

export const deleteReminder = (token, reminderId) =>
  apiFetch(`/admin/reminders/${reminderId}`, { method: 'DELETE', token })

export const listMemories = (token, ownerId) =>
  apiFetch(`/admin/memories${ownerId ? `?owner_id=${encodeURIComponent(ownerId)}` : ''}`, { token })

export const deleteMemory = (token, memoryId) =>
  apiFetch(`/admin/memories/${memoryId}`, { method: 'DELETE', token })

export const getSystemHealth = (token) => apiFetch('/admin/system-health', { token })

export const getAIManagement = (token) => apiFetch('/admin/ai-management', { token })

export const updateAIManagement = (token, { provider, model, temperature }) =>
  apiFetch('/admin/ai-management', { method: 'PATCH', token, body: { provider, model, temperature } })

export const getAIUsage = (token, days = 7) => apiFetch(`/admin/ai-usage?days=${days}`, { token })

export const listAuditLog = (token, { q, actorType, limit, offset } = {}) => {
  const params = new URLSearchParams()
  if (q) params.set('q', q)
  if (actorType) params.set('actor_type', actorType)
  if (limit) params.set('limit', String(limit))
  if (offset) params.set('offset', String(offset))
  const qs = params.toString()
  return apiFetch(`/admin/audit-log${qs ? `?${qs}` : ''}`, { token })
}
