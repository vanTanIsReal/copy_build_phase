import { motion } from 'framer-motion'

// "AI đang sống" indicator (design brief Phase 3) - a soft violet glow ring that breathes while
// an agent is thinking/generating, replacing the plain "Đang xử lý..." text bubble. Purely
// decorative/presentational - callers decide when to render it (e.g. PersonalAIChat.jsx's
// `sending` state), no data fetching here.
export default function AILoadingState({ label = 'Đang suy nghĩ...' }) {
  return (
    <div className="d-flex align-items-center gap-3">
      <div className="relative flex h-9 w-9 shrink-0 items-center justify-center">
        <motion.span
          className="absolute inset-0 rounded-full bg-primary/40 blur-md"
          animate={{ opacity: [0.5, 1, 0.5], scale: [0.9, 1.05, 0.9] }}
          transition={{ duration: 1.8, repeat: Infinity, ease: 'easeInOut' }}
        />
        <span className="relative flex h-6 w-6 items-center justify-center rounded-full bg-gradient-to-br from-primary to-violet-400 text-white">
          <i className="bi bi-stars" style={{ fontSize: 11 }} />
        </span>
      </div>
      <span className="text-sm text-muted-foreground">{label}</span>
    </div>
  )
}
