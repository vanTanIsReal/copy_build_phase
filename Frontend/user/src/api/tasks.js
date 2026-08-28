import { apiFetch } from './client'

export const listTasks = (token, workspace_id) => {
  const query = workspace_id ? `?workspace_id=${encodeURIComponent(workspace_id)}` : ''
  return apiFetch(`/tasks${query}`, { token })
}

export const createTask = (token, { workspace_id, title, due_at, priority, conversation_id, source, source_message_ids, consent_scope_hash }) =>
  apiFetch('/tasks', { method: 'POST', token, body: { workspace_id, title, due_at, priority, conversation_id, source, source_message_ids, consent_scope_hash } })

export const updateTaskStatus = (token, taskId, status, dueAt) =>
  apiFetch(`/tasks/${taskId}/status`, { method: 'PATCH', token, body: { status, ...(dueAt ? { due_at: dueAt } : {}) } })

export const deleteTask = (token, taskId) =>
  apiFetch(`/tasks/${taskId}`, { method: 'DELETE', token })