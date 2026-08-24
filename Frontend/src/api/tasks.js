import { apiFetch } from './client'

export const listTasks = (token) => apiFetch('/tasks', { token })

export const createTask = (token, { title, due_at, priority, conversation_id, source }) =>
  apiFetch('/tasks', { method: 'POST', token, body: { title, due_at, priority, conversation_id, source } })

export const updateTaskStatus = (token, taskId, status) =>
  apiFetch(`/tasks/${taskId}/status`, { method: 'PATCH', token, body: { status } })

// Accept a suggested task. For a proactive task with a due date this may come back
// { conflict: true, conflicts, alternatives } instead of accepting - see useTaskAccept.
export const acceptTask = (token, taskId, { due_at, force } = {}) =>
  apiFetch(`/tasks/${taskId}/accept`, { method: 'POST', token, body: { due_at: due_at || null, force: Boolean(force) } })

export const deleteTask = (token, taskId) =>
  apiFetch(`/tasks/${taskId}`, { method: 'DELETE', token })
