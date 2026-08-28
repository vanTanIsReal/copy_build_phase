import { apiFetch } from './client'

export const listAssistantThreads = (token) => apiFetch('/assistant/threads', { token })

export const getAssistantThreadMessages = (token, threadId) =>
  apiFetch(`/assistant/threads/${threadId}/messages`, { token })
