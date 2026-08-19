import React from 'react'
import ReactDOM from 'react-dom/client'
import 'bootstrap/dist/css/bootstrap.min.css'
import 'bootstrap-icons/font/bootstrap-icons.css'
import 'bootstrap/dist/js/bootstrap.bundle.min.js'
import '../../src/styles.css'
import './admin.css'
// Tailwind loaded LAST - see the matching comment in Frontend/user/src/main.jsx for why the
// order matters (Tailwind v3 has no native CSS @layer isolation; last-imported wins ties).
import '../../src/tailwind.css'
import { AuthProvider } from '../../src/context/AuthContext'
import { ToastProvider } from '../../src/context/ToastContext'
import AdminRouter from './AdminRouter'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ToastProvider>
      <AuthProvider><AdminRouter /></AuthProvider>
    </ToastProvider>
  </React.StrictMode>
)
