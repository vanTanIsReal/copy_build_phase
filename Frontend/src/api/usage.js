import { apiFetch } from './client'

export const getUsageStatus = (token) => apiFetch('/usage/status', { token })
