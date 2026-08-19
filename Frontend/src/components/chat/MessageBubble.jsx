import Avatar from '../common/Avatar'
import { getInitials, getColor, formatTime } from '../../utils/avatar'

function renderContent(content) {
  const match = content.match(/^\[\[attachment\|([^|]+)\|([^|]+)\|([^\]]+)\]\](?:\n([\s\S]*))?$/)
  if (!match) return <span className="message-text">{content}</span>
  const [, encodedName, encodedType, data, text] = match
  const name = decodeURIComponent(encodedName); const type = decodeURIComponent(encodedType)
  const isImage = type.startsWith('image/')
  return <div className="message-file"><a href={data} target="_blank" rel="noreferrer" className="message-file-link">{isImage ? <img src={data} alt={name} /> : <i className="bi bi-file-earmark-arrow-down" />}<span>{name}</span></a><a className="message-file-download" href={data} download={name} aria-label={`Download ${name}`}><i className="bi bi-download" /></a>{text && <div className="message-file-text">{text}</div>}</div>
}

export default function MessageBubble({ message, own }) {
  if (own) return (
    <div className="message-row own"><div className="message-content"><div className="message-bubble">{renderContent(message.content)}</div><div className="message-time">{formatTime(message.created_at)} <i className="bi bi-check2-all" /></div></div></div>
  )
  return (
    <div className="message-row"><Avatar initials={getInitials(message.sender_name)} color={getColor(message.sender_id)} size={34} /><div className="message-content"><div className="message-sender">{message.sender_name}</div><div className="message-bubble">{renderContent(message.content)}</div><div className="message-time">{formatTime(message.created_at)}</div></div></div>
  )
}
