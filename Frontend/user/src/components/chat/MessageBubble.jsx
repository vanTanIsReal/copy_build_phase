import Avatar from '../common/Avatar'
import { getInitials, getColor, formatTime } from '../../utils/avatar'

const ATTACHMENT_MARKER = '[[orbit-attachment]]'

function renderContent(content) {
  const lines = String(content || '').split(/\\n|\r?\n/)
  return lines.map((line, index) => {
    if (!line.startsWith(ATTACHMENT_MARKER)) return <span key={`text-${index}`}>{line}{index < lines.length - 1 && <br />}</span>
    try {
      const file = JSON.parse(line.slice(ATTACHMENT_MARKER.length))
      return <span className="message-attachment" key={`file-${index}`}>
        {file.type?.startsWith('image/') && file.dataUrl ? <img src={file.dataUrl} alt={file.name} /> : <i className="bi bi-file-earmark" />}
        <a href={file.dataUrl} download={file.name}>{file.name}</a>
      </span>
    } catch { return <span key={`text-${index}`}>{line}</span> }
  })
}

export default function MessageBubble({ message, own }) {
  const body = renderContent(message.content)
  if (own) return (
    <div className="message-row own"><div className="message-content"><div className="message-bubble">{body}</div><div className="message-time">{formatTime(message.created_at)} <i className="bi bi-check2-all" /></div></div></div>
  )
  return (
    <div className="message-row"><Avatar initials={getInitials(message.sender_name)} color={getColor(message.sender_id)} size={34} /><div className="message-content"><div className="message-sender">{message.sender_name}</div><div className="message-bubble">{body}</div><div className="message-time">{formatTime(message.created_at)}</div></div></div>
  )
}