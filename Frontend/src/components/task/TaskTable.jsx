import { tasks } from '../../data/mockData'

const priorityClass = { High: 'danger', Medium: 'warning', Low: 'info' }
const statusClass = { Completed: 'success', Overdue: 'danger', Pending: 'secondary', 'In progress': 'primary' }

export default function TaskTable() {
  return (
    <div className="table-responsive task-table-wrap"><table className="table task-table align-middle mb-0"><thead><tr><th><input type="checkbox"/></th><th>Task</th><th>Deadline</th><th>Priority</th><th>Status</th><th>Source</th><th/></tr></thead><tbody>
      {tasks.map(task => <tr key={task.id}><td><input type="checkbox" defaultChecked={task.status==='Completed'}/></td><td><strong className={task.status==='Completed'?'text-decoration-line-through text-muted':''}>{task.title}</strong></td><td><span className={task.status==='Overdue'?'text-danger':''}><i className="bi bi-calendar3 me-2"/>{task.due}</span></td><td><span className={`soft-badge ${priorityClass[task.priority]}`}><i/>{task.priority}</span></td><td><span className={`status-badge ${statusClass[task.status]}`}>{task.status}</span></td><td><span className="source-pill"><i className="bi bi-chat-left-text"/>{task.source}</span></td><td><div className="dropdown"><button className="icon-btn" data-bs-toggle="dropdown"><i className="bi bi-three-dots"/></button><ul className="dropdown-menu dropdown-menu-end"><li><button className="dropdown-item"><i className="bi bi-pencil me-2"/>Edit</button></li><li><button className="dropdown-item"><i className="bi bi-check2 me-2"/>Complete</button></li><li><button className="dropdown-item text-danger"><i className="bi bi-trash me-2"/>Delete</button></li></ul></div></td></tr>)}
    </tbody></table></div>
  )
}
