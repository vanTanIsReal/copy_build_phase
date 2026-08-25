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
    // Resolve dependencies imported by ../src from this app's node_modules. Without this alias,
    // Vite starts resolution from the shared source directory and cannot find app dependencies.
    alias: {
      bootstrap: path.resolve(rootDir, 'node_modules/bootstrap'),
      'bootstrap-icons': path.resolve(rootDir, 'node_modules/bootstrap-icons'),
      'framer-motion': path.resolve(rootDir, 'node_modules/framer-motion'),
      'react-hook-form': path.resolve(rootDir, 'node_modules/react-hook-form'),
      'react-router-dom': path.resolve(rootDir, 'node_modules/react-router-dom'),
    },
  },
  server: {
    port: 5174,
    fs: { allow: [rootDir, path.resolve(rootDir, '..')] },
  },
  build: { outDir: 'dist' },
})
