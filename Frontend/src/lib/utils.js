import { clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

// Standard shadcn/ui helper: merge conditional classNames (clsx) then resolve conflicting
// Tailwind utility classes so the last one wins (twMerge) - e.g. cn('p-2', condition && 'p-4')
// correctly drops p-2 instead of emitting both.
export function cn(...inputs) {
  return twMerge(clsx(inputs))
}
