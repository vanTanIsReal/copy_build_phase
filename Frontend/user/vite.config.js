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
      // Same reasoning, for the Tailwind/Shadcn UI primitives under ../src/components/ui and
      // ../src/components/command - all shared code, all otherwise unresolvable from here.
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
    port: 5173,
    fs: { allow: [rootDir, path.resolve(rootDir, '..')] },
  },
  build: { outDir: 'dist' },
})
