import { apiFetch } from './client'

// Backend-wide daily token budget (src/services/usage_service.py::get_usage_summary) - there is
// no per-user credit allowance in this app, so this reflects the whole workspace's usage today.
export const getUsageStatus = (token) => apiFetch('/usage/status', { token })
