import { useEffect, useState } from 'react'
import { getMessages } from '../api/chat'

export function useMessages(token, conversationId) {
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!token || !conversationId) { setMessages([]); return }
    setLoading(true)
    getMessages(token, conversationId).then(data => setMessages(data.messages)).finally(() => setLoading(false))
  }, [token, conversationId])

  return { messages, setMessages, loading }
}
