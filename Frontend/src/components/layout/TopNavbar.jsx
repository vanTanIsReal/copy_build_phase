import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'

const destinations = [
  { label: 'Orbit Assistant', keywords: 'ai ask assistant agent orbit', path: '/assistant', icon: 'bi-stars' },
  { label: 'Chats', keywords: 'messages conversations people groups', path: '/chat', icon: 'bi-chat-dots' },
  { label: 'Tasks', keywords: 'work todos deadlines action items', path: '/tasks', icon: 'bi-list-task' },
  { label: 'Calendar', keywords: 'events meetings schedule dates', path: '/calendar', icon: 'bi-calendar3' },
  { label: 'Reminders', keywords: 'alerts notifications alarms', path: '/reminders', icon: 'bi-alarm' },
  { label: 'Memory', keywords: 'remember preferences context', path: '/memory', icon: 'bi-journal-bookmark' },
  { label: 'Profile', keywords: 'account settings password', path: '/profile', icon: 'bi-person' },
]

const getInitials = (name) => (name || '?').trim().split(/\s+/).map(w => w[0]).slice(0, 2).join('').toUpperCase()

export default function TopNavbar({ onMenu }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const inputRef = useRef(null)
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const normalized = query.trim().toLowerCase()
  const results = useMemo(() => normalized
    ? destinations.filter(item => `${item.label} ${item.keywords}`.toLowerCase().includes(normalized))
    : destinations, [normalized])

  useEffect(() => {
    const focusSearch = event => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault(); inputRef.current?.focus(); setOpen(true)
      }
    }
    window.addEventListener('keydown', focusSearch)
    return () => window.removeEventListener('keydown', focusSearch)
  }, [])

  const choose = item => { navigate(item.path); setQuery(''); setOpen(false) }
  const onKeyDown = event => {
    if (event.key === 'Enter' && results[0]) { event.preventDefault(); choose(results[0]) }
    if (event.key === 'Escape') { setQuery(''); setOpen(false); inputRef.current?.blur() }
  }
  const onLogout = () => { logout(); navigate('/login') }

  return <header className="top-navbar">
    <button className="icon-btn mobile-menu" onClick={onMenu} aria-label="Open menu"><i className="bi bi-list" /></button>
    <div className="global-search" onFocus={()=>setOpen(true)} onBlur={()=>setTimeout(()=>setOpen(false),120)}>
      <i className="bi bi-search"/><input ref={inputRef} aria-label="Search" placeholder="Search pages and features..." value={query} onChange={e=>{setQuery(e.target.value);setOpen(true)}} onKeyDown={onKeyDown}/><kbd>Ctrl K</kbd>
      {open&&<div className="global-search-results">{results.map(item=><button type="button" key={item.path} onMouseDown={e=>e.preventDefault()} onClick={()=>choose(item)}><i className={`bi ${item.icon}`}/><span>{item.label}</span><i className="bi bi-arrow-right-short"/></button>)}{!results.length&&<p>No matching page or feature.</p>}</div>}
    </div>
    <div className="nav-actions"><button className="icon-btn"><i className="bi bi-question-circle" /></button><button className="icon-btn notification-btn"><i className="bi bi-bell" /><span /></button><button className="nav-avatar">{getInitials(user?.display_name)}</button><button className="icon-btn" onClick={onLogout} aria-label="Log out" title="Log out"><i className="bi bi-box-arrow-right" /></button></div>
  </header>
}
