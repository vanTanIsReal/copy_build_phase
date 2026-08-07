import { useEffect, useRef } from 'react'
import { WS_BASE_URL } from './client'

export function useChatSocket(token, onMessage) {
  const socketRef = useRef(null)
  const onMessageRef = useRef(onMessage)
  onMessageRef.current = onMessage

  useEffect(() => {
    if (!token) return undefined
    let cancelled = false
    let reconnectTimer

    const connect = () => {
      const ws = new WebSocket(`${WS_BASE_URL}?token=${token}`)
      socketRef.current = ws
      ws.onmessage = (event) => {
        try { onMessageRef.current?.(JSON.parse(event.data)) } catch { /* ignore malformed frame */ }
      }
      ws.onclose = () => { if (!cancelled) reconnectTimer = setTimeout(connect, 2000) }
    }
    connect()

    return () => {
      cancelled = true
      clearTimeout(reconnectTimer)
      socketRef.current?.close()
    }
  }, [token])

  const sendJson = (obj) => {
    const ws = socketRef.current
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj))
  }

  return { sendJson }
}
