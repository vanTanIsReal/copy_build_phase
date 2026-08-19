import { Skeleton } from '../ui/skeleton'

// Generic table-body skeleton: `rows` rows x `cols` cells, each a single Skeleton bar. Used
// wherever a page currently shows <p>Loading...</p> above a <table>.
export default function TableRowsSkeleton({ rows = 5, cols = 4 }) {
  return (
    <table className="table mb-0">
      <tbody>
        {Array.from({ length: rows }).map((_, r) => (
          <tr key={r}>
            {Array.from({ length: cols }).map((_, c) => (
              <td key={c} className="p-3">
                <Skeleton className={`h-3.5 ${c === 0 ? 'w-2/3' : 'w-1/2'}`} />
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}
