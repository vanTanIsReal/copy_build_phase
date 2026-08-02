import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useSearchParams } from 'react-router-dom'
import { AuthShell } from './LoginPage'
import { resetPassword } from '../api/auth'

export default function ResetPasswordPage() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token') || ''
  const { register, handleSubmit, watch, formState: { errors } } = useForm()
  const [error, setError] = useState(token ? '' : 'This password reset link is invalid.')
  const [success, setSuccess] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  const onSubmit = async ({ password }) => {
    setError('')
    setSubmitting(true)
    try {
      await resetPassword({ token, password })
      setSuccess(true)
    } catch (err) {
      setError(err.detail || 'This password reset link is invalid or expired.')
    } finally {
      setSubmitting(false)
    }
  }

  return <AuthShell title="Set a new password" subtitle="Choose a strong password for your Orbit account.">
    {success ? (
      <div>
        <div className="auth-success">Your password has been reset successfully.</div>
        <Link className="btn btn-primary w-100 auth-submit mt-3 d-flex align-items-center justify-content-center gap-2" to="/login">Continue to sign in <i className="bi bi-arrow-right" /></Link>
      </div>
    ) : (
      <form onSubmit={handleSubmit(onSubmit)}>
        {error && <div className="auth-error">{error}</div>}
        <label className="auth-label">New password</label>
        <div className={`auth-input ${errors.password ? 'invalid' : ''}`}>
          <i className="bi bi-lock" />
          <input type="password" placeholder="At least 6 characters" {...register('password', { required: true, minLength: 6 })} />
        </div>
        {errors.password && <small className="text-danger">Password must be at least 6 characters.</small>}
        <label className="auth-label mt-3">Confirm new password</label>
        <div className={`auth-input ${errors.confirm ? 'invalid' : ''}`}>
          <i className="bi bi-lock" />
          <input type="password" placeholder="Repeat your new password" {...register('confirm', { required: true, validate: value => value === watch('password') || 'Passwords do not match' })} />
        </div>
        {errors.confirm && <small className="text-danger">{errors.confirm.message || 'Confirm your password.'}</small>}
        <button className="btn btn-primary w-100 auth-submit mt-4" disabled={submitting || !token}>
          {submitting ? 'Updating password...' : 'Update password'} <i className="bi bi-check2" />
        </button>
        <p className="auth-switch"><Link to="/login">Back to sign in</Link></p>
      </form>
    )}
  </AuthShell>
}
