import { apiFetch } from './client'

export const chatWithAgent = (
  token,
  {
    message, conversation_id, thread_id, workspace_id, context_limit, scope, messages, quick_action,
    // Multi-agent (Delivery/Quality/Executive) - see src.api.routes._run_specialist_chat.
    // requested_scope defaults server-side to "personal", so omitting these three keeps every
    // existing caller's behavior unchanged.
    requested_scope, target_agent_workspace_id, specialist_action,
  },
) =>
  apiFetch('/chat', {
    method: 'POST',
    token,
    body: {
      message, conversation_id, thread_id, workspace_id, context_limit, scope, messages, quick_action,
      requested_scope, target_agent_workspace_id, specialist_action,
    },
  })

export const resumeAgent = (token, { thread_id, approved, edits }) =>
  apiFetch('/chat/resume', { method: 'POST', token, body: { thread_id, approved, edits } })
