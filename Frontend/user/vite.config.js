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
  },
  server: {
    port: 5173,
    fs: { allow: [rootDir, path.resolve(rootDir, '..')] },
  },
  build: { outDir: 'dist' },
})
