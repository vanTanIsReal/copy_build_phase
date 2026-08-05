import { apiFetch } from './client'

export const register = ({ email, password, display_name }) =>
  apiFetch('/auth/register', { method: 'POST', body: { email, password, display_name } })

export const login = ({ email, password }) => apiFetch('/auth/login', { method: 'POST', body: { email, password } })

export const getMe = (token) => apiFetch('/auth/me', { token })

export const requestPasswordReset = (email) =>
  apiFetch('/auth/forgot-password', { method: 'POST', body: { email } })

export const resetPassword = ({ token, password }) =>
  apiFetch('/auth/reset-password', { method: 'POST', body: { token, password } })

export const updateProfile = (token, updates) => apiFetch('/auth/me', { method: 'PATCH', token, body: updates })

export const changePassword = (token, { current_password, new_password }) =>
  apiFetch('/auth/me/password', { method: 'POST', token, body: { current_password, new_password } })
