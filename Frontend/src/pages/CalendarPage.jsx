import { useState } from 'react'
import FullCalendar from '@fullcalendar/react'
import dayGridPlugin from '@fullcalendar/daygrid'
import timeGridPlugin from '@fullcalendar/timegrid'
import interactionPlugin from '@fullcalendar/interaction'
import PageHeader from '../components/common/PageHeader'
import DetectedEventCard from '../components/calendar/DetectedEventCard'
import { calendarEvents } from '../data/mockData'

export default function CalendarPage() {
  const [event, setEvent] = useState(null)
  return <div className="page-container calendar-page">
    <PageHeader eyebrow="Schedule" title="Calendar" description="Your plans and AI-detected events, all in one place." action={<button className="btn btn-primary"><i className="bi bi-plus-lg me-2"/>New event</button>}/>
    <div className="calendar-layout"><section className="content-card calendar-card"><FullCalendar plugins={[dayGridPlugin,timeGridPlugin,interactionPlugin]} initialView="dayGridMonth" initialDate="2026-08-01" headerToolbar={{left:'prev,next today',center:'title',right:'dayGridMonth,timeGridWeek,timeGridDay'}} events={calendarEvents} eventClick={({event:e})=>setEvent(e)} height="auto"/></section>
      <aside className="detected-sidebar"><div className="detected-head"><span><i className="bi bi-stars"/></span><div><h3>AI-detected events</h3><p>Found in recent chats</p></div><b>3</b></div><DetectedEventCard title="Launch copy review" source="Product Launch" date="31 Jul 11:00 AM" color="#526ff5"/><DetectedEventCard title="Vendor demo" source="Procurement" date="04 Aug 2:30 PM" color="#8b5cf6"/><DetectedEventCard title="Q3 planning session" source="Leadership" date="08 Aug 9:00 AM" color="#10b981"/><button className="btn btn-light w-100 mt-2">Review all events</button></aside>
    </div>
    {event && <div className="modal-backdrop-custom" onClick={()=>setEvent(null)}><div className="event-modal" onClick={e=>e.stopPropagation()}><button className="icon-btn modal-close" onClick={()=>setEvent(null)}><i className="bi bi-x-lg"/></button><div className="event-modal-icon"><i className="bi bi-calendar-event"/></div><span className="eyebrow">Event details</span><h3>{event.title}</h3><div className="event-detail-row"><i className="bi bi-clock"/><span><strong>Thursday, July 30</strong><small>3:30 PM – 4:30 PM</small></span></div><div className="event-detail-row"><i className="bi bi-chat-left-text"/><span><strong>Product Launch</strong><small>Source conversation</small></span></div><button className="btn btn-primary w-100 mt-3">Open event</button></div></div>}
  </div>
}
