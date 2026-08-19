import { Skeleton } from '../ui/skeleton'

// Generic "icon + two lines of text" row skeleton, reused wherever a page currently shows
// <p>Loading...</p> above a list of rows (reminders, task inbox, ...). `count` rows, `padded`
// matches pages whose real rows sit inside a card with p-3-ish spacing.
export default function ListRowSkeleton({ count = 4, className = '' }) {
  return (
    <div className={`p-3 d-flex flex-column gap-3 ${className}`}>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="d-flex align-items-center gap-3">
          <Skeleton className="h-10 w-10 shrink-0 rounded-lg" />
          <div className="flex-grow-1">
            <Skeleton className="h-3.5 w-1/3" />
            <Skeleton className="mt-2 h-3 w-1/2" />
          </div>
        </div>
      ))}
    </div>
  )
}
