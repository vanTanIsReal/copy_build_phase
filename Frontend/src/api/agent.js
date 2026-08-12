import { apiFetch } from './client'

export const chatWithAgent = (token, { message, thread_id, messages, conversation_id, scope, quick_action }) =>
  apiFetch('/chat', { method: 'POST', token, body: { message, thread_id, messages, conversation_id, scope, quick_action } })

export const resumeAgent = (token, { thread_id, approved, edits }) =>
  apiFetch('/chat/resume', { method: 'POST', token, body: { thread_id, approved, edits } })
