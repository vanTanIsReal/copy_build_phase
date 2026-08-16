import { useEffect, useRef, useState } from 'react'
import { Link, useOutletContext } from 'react-router-dom'
import FullCalendar from '@fullcalendar/react'
import dayGridPlugin from '@fullcalendar/daygrid'
import timeGridPlugin from '@fullcalendar/timegrid'
import interactionPlugin from '@fullcalendar/interaction'
// Required for the `timeZone="Asia/Ho_Chi_Minh"` prop below to actually convert event times for
// display - without this plugin, FullCalendar only knows how to display 'local' (the viewer's
// own machine/browser zone) or 'UTC' correctly; any other named IANA zone is silently NOT
// converted, so every event rendered exactly at its raw UTC clock digits (e.g. a 9am Vietnam
// event stored as "...T02:00:00Z" showed as "2am" instead of "9am").
import momentTimezonePlugin from '@fullcalendar/moment-timezone'
import PageHeader from '../components/common/PageHeader'
import NewEventModal from '../components/calendar/NewEventModal'
import ConnectCalendarCard from '../components/calendar/ConnectCalendarCard'
import { useAuth } from '../context/AuthContext'
import {
  listCalendarEvents, deleteCalendarEvent,
  getCalendarConnection, disconnectCalendar,
} from '../api/calendar'
import { getColor } from '../utils/avatar'
import { HANOI_TZ, formatDateTime } from '../utils/datetime'

export default function CalendarPage() {
  const { token } = useAuth()
  const { subscribe } = useOutletContext()
  const [connected, setConnected] = useState(null) // null = not checked yet
  const [events, setEvents] = useState([])
  const [checkingConnection, setCheckingConnection] = useState(true) // initial "are we connected at all" check
  const [eventsLoading, setEventsLoading] = useState(false) // a refresh() in flight - never unmounts FullCalendar
  const [error, setError] = useState('')
  const [selected, setSelected] = useState(null)
  const [newEventOpen, setNewEventOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)

  // Range actually visible in the calendar grid right now - null until FullCalendar has mounted
  // and reported it via onDatesSet. Kept in a ref (not state) purely so refresh() called from
  // elsewhere (disconnect/reconnect, "New event") can reuse the last-known range without also
  // needing to be in that effect's dependency list.
  const visibleRange = useRef(null)

  const refresh = () => {
    setEventsLoading(true); setError('')
    listCalendarEvents(token, visibleRange.current || {})
      .then(list => { setConnected(true); setEvents(list.map(e => ({ ...e, color: getColor(e.id) }))) })
      .catch(err => {
        if (err.status === 409) { setConnected(false); setEvents([]) } // not connected, not an error
        else setError(err.detail?.message || err.detail || 'Could not load Google Calendar events.')
      })
      .finally(() => setEventsLoading(false))
  }

  // Fires on mount AND on every prev/next/today/view-switch - without this, /calendar/events'
  // default range (now -> +60 days, see calendar_routes.py) means events earlier in the CURRENTLY
  // VISIBLE month (e.g. anything before "right now" today) never load at all, even though they're
  // sitting right there in the grid. Refetching with the grid's actual boundaries each time fixes
  // that for every view, not just the initial month.
  //
  // Deliberately NOT gated behind eventsLoading/checkingConnection anywhere in JSX below - if
  // rendering FullCalendar itself depended on a loading flag that only this callback clears,
  // FullCalendar could never mount to fire it in the first place (a real deadlock this page had
  // for a moment: stuck on "Loading calendar..." forever).
  const onDatesSet = (arg) => {
    visibleRange.current = { time_min: arg.start.toISOString(), time_max: arg.end.toISOString() }
    refresh()
  }

  useEffect(() => {
    setCheckingConnection(true)
    getCalendarConnection(token)
      .then(({ connected: isConnected }) => setConnected(isConnected))
      .catch(() => {})
      .finally(() => setCheckingConnection(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  const upsertEvent = (event) => setEvents(prev => [...prev.filter(e => e.id !== event.id), { ...event, color: getColor(event.id) }])
  const removeEvent = (eventId) => setEvents(prev => prev.filter(e => e.id !== eventId))

  // Realtime: each user has their own Google Calendar now, the backend only ever pushes to the
  // owner. Source: this UI, another tab, the agent in chat, or a direct edit in Google Calendar
  // itself (caught by syncToken polling while this user is online).
  useEffect(() => subscribe((data) => {
    if (data.type === 'calendar_event_created' || data.type === 'calendar_event_updated') upsertEvent(data.event)
    if (data.type === 'calendar_event_deleted') removeEvent(data.event_id)
  }), [subscribe])

  const removeSelected = async () => {
    if (!selected || deleting) return
    setDeleting(true)
    try {
      await deleteCalendarEvent(token, selected.id)
      removeEvent(selected.id)
      setSelected(null)
    } catch (err) {
      setError(err.detail?.message || err.detail || 'Could not delete this event.')
    } finally { setDeleting(false) }
  }

  const disconnect = async () => {
    try {
      await disconnectCalendar(token)
      setConnected(false); setEvents([])
    } catch (err) {
      setError(err.detail?.message || err.detail || 'Could not disconnect Google Calendar.')
    }
  }

  const headerAction = connected
    ? <div className="d-flex gap-2">
        <button className="btn btn-light btn-sm" onClick={disconnect}><i className="bi bi-google me-2" />Disconnect</button>
        <button className="btn btn-primary" onClick={() => setNewEventOpen(true)}><i className="bi bi-plus-lg me-2" />New event</button>
      </div>
    : null

  return <div className="page-container calendar-page">
    <PageHeader eyebrow="Schedule" title="Calendar" description="Your Google Calendar events, all in one place." action={headerAction}/>
    {error && <div className="auth-error mb-3">{error}</div>}
    {checkingConnection ? <p className="text-muted small">Loading calendar...</p> : connected === false ? (
      <ConnectCalendarCard onConnected={() => setConnected(true)} />
    ) : (
      <div className="calendar-layout"><section className="content-card calendar-card">
        {eventsLoading && <p className="text-muted small mb-2">Refreshing...</p>}
        <FullCalendar plugins={[dayGridPlugin,timeGridPlugin,interactionPlugin,momentTimezonePlugin]} initialView="dayGridMonth" timeZone={HANOI_TZ} headerToolbar={{left:'prev,next today',center:'title',right:'dayGridMonth,timeGridWeek,timeGridDay'}} events={events} eventClick={(info)=>{ info.jsEvent.preventDefault(); setSelected(info.event) }} datesSet={onDatesSet} height="auto"/>
      </section>
        <aside className="detected-sidebar"><div className="detected-head"><span><i className="bi bi-stars"/></span><div><h3>AI-detected events</h3><p>Active</p></div></div><p className="text-muted small">Orbit đang tự động rà tin nhắn tìm cam kết/lịch hẹn. Khi phát hiện, việc gợi ý sẽ xuất hiện trong <Link to="/tasks">Tasks → AI suggestions</Link> để bạn Accept/Dismiss trước khi tạo event thật.</p></aside>
      </div>
    )}
    {selected && <div className="modal-backdrop-custom" onClick={()=>setSelected(null)}><div className="event-modal" onClick={e=>e.stopPropagation()}><button className="icon-btn modal-close" onClick={()=>setSelected(null)}><i className="bi bi-x-lg"/></button><div className="event-modal-icon"><i className="bi bi-calendar-event"/></div><span className="eyebrow">Event details</span><h3>{selected.title}</h3><div className="event-detail-row"><i className="bi bi-clock"/><span><strong>{formatDateTime(selected.start)}</strong>{selected.end && <small>{' → '}{formatDateTime(selected.end)}</small>}</span></div>{selected.url && <a className="btn btn-primary w-100 mt-3" href={selected.url} target="_blank" rel="noreferrer">Open in Google Calendar</a>}<button className="btn btn-light text-danger w-100 mt-2" onClick={removeSelected} disabled={deleting}><i className="bi bi-trash me-2"/>{deleting?'Deleting...':'Delete event'}</button></div></div>}
    <NewEventModal open={newEventOpen} onClose={() => setNewEventOpen(false)} onCreated={upsertEvent} />
  </div>
}
