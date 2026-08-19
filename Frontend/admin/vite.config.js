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
      // shared Tailwind/Shadcn UI code (../src/components/ui, ../src/components/command) is
      // otherwise unresolvable. Mirrors ../user/vite.config.js's alias block.
      'lucide-react': path.resolve(rootDir, 'node_modules/lucide-react'),
      cmdk: path.resolve(rootDir, 'node_modules/cmdk'),
      '@radix-ui/react-dialog': path.resolve(rootDir, 'node_modules/@radix-ui/react-dialog'),
      '@radix-ui/react-slot': path.resolve(rootDir, 'node_modules/@radix-ui/react-slot'),
      '@radix-ui/react-tabs': path.resolve(rootDir, 'node_modules/@radix-ui/react-tabs'),
      vaul: path.resolve(rootDir, 'node_modules/vaul'),
      'class-variance-authority': path.resolve(rootDir, 'node_modules/class-variance-authority'),
      clsx: path.resolve(rootDir, 'node_modules/clsx'),
      'tailwind-merge': path.resolve(rootDir, 'node_modules/tailwind-merge'),
    },
  },
  server: {
    port: 5174,
    fs: { allow: [rootDir, path.resolve(rootDir, '..')] },
  },
  build: { outDir: 'dist' },
})
