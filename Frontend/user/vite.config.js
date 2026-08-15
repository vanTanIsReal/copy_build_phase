import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const rootDir = path.dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  plugins: [react()],
  resolve: {
    // Shared source lives one directory above this app (../src). Dependencies imported from
    // there must resolve to this app's own react/react-dom, not a second copy - dedupe forces
    // that, fs.allow below is what lets Vite serve files from ../src at all.
    dedupe: ['react', 'react-dom'],
    alias: {
      // Node's bare-specifier resolution walks UP from the importing file - ../src/... is a
      // sibling of this app's node_modules, not a descendant of it, so a package used only from
      // shared code (react-markdown/remark-gfm, for Markdown.jsx) is otherwise unresolvable no
      // matter how correctly it's listed in this app's package.json. Alias forces it explicitly.
      'react-markdown': path.resolve(rootDir, 'node_modules/react-markdown'),
      'remark-gfm': path.resolve(rootDir, 'node_modules/remark-gfm'),
    },
  },
  server: {
    port: 5173,
    fs: { allow: [rootDir, path.resolve(rootDir, '..')] },
  },
  build: { outDir: 'dist' },
})
