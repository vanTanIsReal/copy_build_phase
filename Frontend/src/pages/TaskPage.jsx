import PageHeader from '../components/common/PageHeader'
import StatCard from '../components/common/StatCard'
import TaskTable from '../components/task/TaskTable'

const suggestions = [
  { title:'Add conversion numbers to launch deck', source:'Product Launch', confidence:94, due:'Today' },
  { title:'Book Q3 planning room', source:'Leadership', confidence:87, due:'Tomorrow' },
]

export default function TaskPage() {
  return <div className="page-container">
    <PageHeader eyebrow="Workspace" title="My Tasks" description="Stay on top of work, including action items found by Orbit." action={<button className="btn btn-primary rounded-3"><i className="bi bi-plus-lg me-2"/>Add task</button>}/>
    <div className="stats-grid"><StatCard label="Total tasks" value="24" icon="bi-list-task" note="+3 this week"/><StatCard label="Completed" value="14" icon="bi-check2-circle" color="success" note="58% completion"/><StatCard label="Pending" value="7" icon="bi-hourglass-split" color="warning"/><StatCard label="Overdue" value="3" icon="bi-exclamation-circle" color="danger" note="Needs attention"/></div>
    <section className="content-card"><div className="card-toolbar"><div><h3>All tasks</h3><span>24 tasks across your conversations</span></div><div className="toolbar-actions"><div className="mini-search"><i className="bi bi-search"/><input placeholder="Search tasks"/></div><button className="btn btn-light"><i className="bi bi-filter me-2"/>Filter</button></div></div><TaskTable/></section>
    <section className="suggested-section"><div className="section-heading"><div><span className="ai-label"><i className="bi bi-stars"/> AI suggestions</span><h3>Tasks you may have missed</h3><p>Orbit found these action items in your conversations.</p></div><button className="btn btn-light">View all</button></div><div className="suggestion-grid">{suggestions.map(s=><div className="suggestion-card" key={s.title}><div className="suggestion-check"><i className="bi bi-stars"/></div><div className="flex-grow-1"><h4>{s.title}</h4><div className="suggestion-meta"><span><i className="bi bi-chat-left-text"/>{s.source}</span><span><i className="bi bi-calendar3"/>{s.due}</span></div><div className="confidence"><span>AI confidence</span><div><i style={{width:`${s.confidence}%`}}/></div><strong>{s.confidence}%</strong></div></div><div className="suggestion-actions"><button className="btn btn-sm btn-primary">Accept</button><button className="btn btn-sm btn-light">Dismiss</button></div></div>)}</div></section>
  </div>
}
