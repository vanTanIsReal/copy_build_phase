import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useNavigate } from 'react-router-dom'
import { AuthShell } from './LoginPage'
import { requestPasswordReset } from '../api/auth'

export default function ForgotPasswordPage() {
  const { register, handleSubmit, formState: { errors } } = useForm()
  const navigate = useNavigate()
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const onSubmit = async ({ email }) => {
    setError('')
    setSuccess('')
    setSubmitting(true)
    try {
      const data = await requestPasswordReset(email)
      if (data.reset_token) {
        navigate(`/reset-password?token=${encodeURIComponent(data.reset_token)}`)
        return
      }
      setSuccess(data.message || 'If an account exists, you will receive reset instructions.')
    } catch (err) {
      setError(err.detail || 'Could not start password reset')
    } finally {
      setSubmitting(false)
    }
  }

  return <AuthShell title="Forgot your password?" subtitle="Enter your email and we will help you get back in.">
    <form onSubmit={handleSubmit(onSubmit)}>
      {error && <div className="auth-error">{error}</div>}
      {success && <div className="auth-success">{success}</div>}
      <label className="auth-label">Email address</label>
      <div className={`auth-input ${errors.email ? 'invalid' : ''}`}>
        <i className="bi bi-envelope" />
        <input autoFocus placeholder="you@company.com" {...register('email', { required: true, pattern: /^\S+@\S+\.\S+$/ })} />
      </div>
      {errors.email && <small className="text-danger">Enter a valid email address.</small>}
      <button className="btn btn-primary w-100 auth-submit mt-4" disabled={submitting}>
        {submitting ? 'Sending instructions...' : 'Send reset instructions'} <i className="bi bi-arrow-right" />
      </button>
      <p className="auth-switch"><Link to="/login"><i className="bi bi-arrow-left me-1" />Back to sign in</Link></p>
    </form>
  </AuthShell>
}
