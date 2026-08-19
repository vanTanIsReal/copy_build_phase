// Shadcn-style config (CSS variables drive the palette - see ../src/tailwind.css). Content globs
// cover this app's own src/ AND the shared ../src/ (Frontend/src/) - both apps' Tailwind builds
// must scan the shared component/page tree or classes used only there get purged.
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import animate from 'tailwindcss-animate'

const rootDir = path.dirname(fileURLToPath(import.meta.url))

/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ['class'],
  content: [
    path.resolve(rootDir, 'index.html'),
    path.resolve(rootDir, 'src/**/*.{js,jsx}'),
    path.resolve(rootDir, '../src/**/*.{js,jsx}'),
  ],
  theme: {
    container: { center: true, padding: '1rem' },
    extend: {
      colors: {
        border: 'hsl(var(--border) / <alpha-value>)',
        input: 'hsl(var(--input) / <alpha-value>)',
        ring: 'hsl(var(--ring) / <alpha-value>)',
        background: 'hsl(var(--background) / <alpha-value>)',
        foreground: 'hsl(var(--foreground) / <alpha-value>)',
        primary: { DEFAULT: 'hsl(var(--primary) / <alpha-value>)', foreground: 'hsl(var(--primary-foreground) / <alpha-value>)' },
        secondary: { DEFAULT: 'hsl(var(--secondary) / <alpha-value>)', foreground: 'hsl(var(--secondary-foreground) / <alpha-value>)' },
        destructive: { DEFAULT: 'hsl(var(--destructive) / <alpha-value>)', foreground: 'hsl(var(--destructive-foreground) / <alpha-value>)' },
        muted: { DEFAULT: 'hsl(var(--muted) / <alpha-value>)', foreground: 'hsl(var(--muted-foreground) / <alpha-value>)' },
        accent: { DEFAULT: 'hsl(var(--accent) / <alpha-value>)', foreground: 'hsl(var(--accent-foreground) / <alpha-value>)' },
        popover: { DEFAULT: 'hsl(var(--popover) / <alpha-value>)', foreground: 'hsl(var(--popover-foreground) / <alpha-value>)' },
        card: { DEFAULT: 'hsl(var(--card) / <alpha-value>)', foreground: 'hsl(var(--card-foreground) / <alpha-value>)' },
      },
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
      },
      boxShadow: {
        // The "violet glow" the design brief asks for on primary surfaces/buttons.
        glow: '0 0 24px -4px hsl(var(--primary) / 0.45)',
        'glow-sm': '0 0 12px -2px hsl(var(--primary) / 0.4)',
      },
      keyframes: {
        'accordion-down': { from: { height: '0' }, to: { height: 'var(--radix-accordion-content-height)' } },
        'accordion-up': { from: { height: 'var(--radix-accordion-content-height)' }, to: { height: '0' } },
      },
      animation: {
        'accordion-down': 'accordion-down 0.2s ease-out',
        'accordion-up': 'accordion-up 0.2s ease-out',
      },
    },
  },
  // Tailwind's Preflight resets margins/font sizes/etc the same elements Bootstrap 5 already
  // resets, differently - loading both would visually break every still-Bootstrap page during
  // the incremental migration. Off for now; flip to true once every page listed in
  // Frontend/README.md's migration tracker is on Tailwind and `bootstrap` is removed from
  // package.json (last step of this migration, not part of Phase 1).
  corePlugins: { preflight: false },
  plugins: [animate],
}
