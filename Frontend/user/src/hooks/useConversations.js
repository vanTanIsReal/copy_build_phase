import { useEffect, useState } from 'react'
import { listConversations } from '../api/chat'

export function useConversations(token, workspaceId) {
  const [conversations, setConversations] = useState([])
  const [loading, setLoading] = useState(true)

  const refresh = () => {
    if (!token) return
    setLoading(true)
    listConversations(token, workspaceId).then(data => setConversations(data.conversations)).finally(() => setLoading(false))
  }

  useEffect(() => { refresh() }, [token, workspaceId])

  return { conversations, setConversations, loading, refresh }
}
