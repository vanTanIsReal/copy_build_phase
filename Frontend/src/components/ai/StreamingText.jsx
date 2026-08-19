import { motion } from 'framer-motion'
import Markdown from '../common/Markdown'

// Mock "streaming" reveal for LLM output (design brief Phase 3): the full response is already in
// hand (this app has no token-streaming endpoint - CLAUDE.md/ARCHITECTURE.md's agent design is
// request/response, not SSE), so this fakes the effect by fading paragraphs in with a stagger
// instead of the whole bubble popping in at once. Splits on blank lines so multi-line markdown
// (a list, several sentences in one paragraph) stays intact per block rather than breaking mid-list.
export default function StreamingText({ children }) {
  const blocks = String(children ?? '').split(/\n{2,}/).filter(Boolean)
  if (blocks.length <= 1) return <Markdown>{children}</Markdown>

  return (
    <>
      {blocks.map((block, i) => (
        <motion.div
          key={i}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.12, duration: 0.3 }}
        >
          <Markdown>{block}</Markdown>
        </motion.div>
      ))}
    </>
  )
}
