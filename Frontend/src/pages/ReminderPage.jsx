import { useState } from 'react'
import PageHeader from '../components/common/PageHeader'

const seed = [
  {id:1,title:'Product launch call',desc:'Today at 3:30 PM',lead:'30 minutes before',repeat:'Does not repeat',on:true,color:'#526ff5',icon:'bi-camera-video'},
  {id:2,title:'Submit weekly report',desc:'Tomorrow at 4:00 PM',lead:'1 hour before',repeat:'Every Friday',on:true,color:'#8b5cf6',icon:'bi-file-earmark-text'},
  {id:3,title:'Take a screen break',desc:'Weekdays at 2:00 PM',lead:'At time of event',repeat:'Mon – Fri',on:false,color:'#10b981',icon:'bi-cup-hot'},
  {id:4,title:'Northstar proposal deadline',desc:'August 3 at 5:00 PM',lead:'1 day before',repeat:'Does not repeat',on:true,color:'#f59e0b',icon:'bi-alarm'},
]

export default function ReminderPage() {
  const [items,setItems]=useState(seed)
  const toggle=id=>setItems(items.map(x=>x.id===id?{...x,on:!x.on}:x))
  return <div className="page-container"><PageHeader eyebrow="Stay focused" title="Reminders" description="Gentle nudges for everything that matters." action={<button className="btn btn-primary"><i className="bi bi-plus-lg me-2"/>New reminder</button>}/>
    <div className="reminder-layout"><section className="content-card reminder-list"><div className="card-toolbar"><div><h3>Upcoming reminders</h3><span>{items.filter(x=>x.on).length} active reminders</span></div><button className="btn btn-light"><i className="bi bi-sliders me-2"/>Manage</button></div>{items.map(r=><div className={`reminder-row ${!r.on?'disabled':''}`} key={r.id}><div className="reminder-icon" style={{background:`${r.color}12`,color:r.color}}><i className={`bi ${r.icon}`}/></div><div className="reminder-info"><h4>{r.title}</h4><strong>{r.desc}</strong><div><span><i className="bi bi-bell"/>{r.lead}</span><span><i className="bi bi-arrow-repeat"/>{r.repeat}</span></div></div><div className="reminder-controls"><span>{r.on?'Enabled':'Paused'}</span><div className="form-check form-switch"><input className="form-check-input" type="checkbox" checked={r.on} onChange={()=>toggle(r.id)}/></div><button className="icon-btn"><i className="bi bi-three-dots"/></button></div></div>)}</section>
      <aside><div className="notification-preview"><div className="preview-label"><span>Preview</span><i className="bi bi-phone"/></div><div className="phone-notification"><div className="orbit-mini"><i className="bi bi-command"/></div><div><div><strong>Orbit</strong><time>now</time></div><h4>Product launch call</h4><p>Starting in 30 minutes • Product Launch</p></div></div><div className="preview-glow"/></div><div className="reminder-tip"><i className="bi bi-lightbulb"/><div><strong>Smart timing</strong><p>Orbit learns when you usually act on reminders and recommends better times.</p></div></div></aside>
    </div>
  </div>
}
