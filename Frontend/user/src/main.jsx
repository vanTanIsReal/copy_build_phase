import React from 'react'
import ReactDOM from 'react-dom/client'
import { GoogleOAuthProvider } from '@react-oauth/google'
import 'bootstrap/dist/css/bootstrap.min.css'
import 'bootstrap-icons/font/bootstrap-icons.css'
import 'bootstrap/dist/js/bootstrap.bundle.min.js'
import '../../src/styles.css'
import '../../src/assistant.css'
// Tailwind loaded LAST, with Preflight off (tailwind.config.js): Tailwind v3 compiles
// `@tailwind utilities` to plain (non-@layer) CSS, so within one page's cascade the file loaded
// last wins same-specificity ties - a Tailwind utility className (e.g. bg-background/80) on an
// element that also carries a legacy styles.css class (e.g. .app-sidebar{background:#fff}) needs
// to load after styles.css to actually apply. Coexists during the incremental migration instead
// of a single flag-day rewrite of the ~40-page styles.css light theme.
import '../../src/tailwind.css'
import UserRouter from './UserRouter'
import { AuthProvider } from '../../src/context/AuthContext'
import { ToastProvider } from '../../src/context/ToastContext'

// Empty clientId just disables the Google button's provider context (GoogleLogin quietly
// no-ops/errors on click instead of crashing at import time) when GOOGLE_OAUTH is unset - dev
// without a Google Cloud OAuth client configured still works for the existing email/password flow.
ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <GoogleOAuthProvider clientId={import.meta.env.VITE_GOOGLE_CLIENT_ID || ''}>
      {/* ToastProvider wraps AuthProvider so AuthContext's own session-check can push a toast too */}
      <ToastProvider>
        <AuthProvider><UserRouter /></AuthProvider>
      </ToastProvider>
    </GoogleOAuthProvider>
  </React.StrictMode>
)
