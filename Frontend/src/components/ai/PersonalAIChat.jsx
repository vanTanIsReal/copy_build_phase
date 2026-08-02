import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'

const prompts = [
  { icon:'bi-sun', label:'Lên kế hoạch hôm nay', prompt:'Tổng hợp lịch, task và deadline của tôi hôm nay' },
  { icon:'bi-calendar-check', label:'Lịch sắp tới', prompt:'Tuần này tôi có những cuộc họp quan trọng nào?' },
  { icon:'bi-exclamation-diamond', label:'Deadline gần nhất', prompt:'Deadline nào đang đến gần và cần ưu tiên?' },
  { icon:'bi-journal-bookmark', label:'Tìm trong memory', prompt:'Tóm tắt những gì bạn nhớ về cách tôi làm việc' },
]

export default function PersonalAIChat({ onContext }) {
  const [draft,setDraft]=useState('')
  const [messages,setMessages]=useState([])
  const send = (value=draft) => {
    if(!value.trim()) return
    const now=Date.now()
    setMessages(prev=>[...prev,{id:now,own:true,text:value},{id:now+1,placeholder:true,text:'Đây là nội dung phản hồi mẫu của giao diện. Khi kết nối backend AI, câu trả lời sẽ được tổng hợp từ các nguồn dữ liệu bạn đã cấp quyền.'}])
    setDraft('')
  }
  return <section className="personal-chat">
    <header className="personal-chat-header"><div className="personal-ai-avatar"><i className="bi bi-stars"/><span/></div><div><h3>Orbit Personal AI</h3><span><i/> Sẵn sàng hỗ trợ bạn</span></div><div className="personal-header-actions"><button className="context-mobile-btn" onClick={onContext}><i className="bi bi-layout-sidebar-reverse"/> Bối cảnh</button><button className="icon-btn"><i className="bi bi-arrow-clockwise"/></button><button className="icon-btn"><i className="bi bi-three-dots"/></button></div></header>
    <div className="personal-messages">
      <div className="personal-welcome"><motion.div initial={{scale:.85,opacity:0}} animate={{scale:1,opacity:1}} className="welcome-ai-mark"><i className="bi bi-stars"/></motion.div><span className="welcome-kicker">Chào buổi sáng, Alex</span><h1>Hôm nay mình có thể<br/><em>giúp gì cho bạn?</em></h1><p>Hỏi mình về lịch, công việc, deadline hoặc thông tin từ các cuộc trò chuyện đã được cấp quyền.</p><div className="prompt-grid">{prompts.map(p=><motion.button whileHover={{y:-3}} whileTap={{scale:.98}} key={p.label} onClick={()=>send(p.prompt)}><span><i className={`bi ${p.icon}`}/></span><strong>{p.label}</strong><small>{p.prompt}</small><i className="bi bi-arrow-up-right"/></motion.button>)}</div></div>
      <AnimatePresence>{messages.map(m=><motion.div key={m.id} initial={{opacity:0,y:8}} animate={{opacity:1,y:0}} className={`personal-message ${m.own?'own':''}`}>
        {!m.own&&<div className="message-ai-icon"><i className="bi bi-stars"/></div>}<div><div className="personal-message-bubble">{m.placeholder&&<span className="placeholder-label">Phản hồi mẫu</span>}{m.text}</div><time>Bây giờ</time></div>
      </motion.div>)}</AnimatePresence>
    </div>
    <div className="personal-composer-wrap"><div className="active-sources"><span><i className="bi bi-database-check"/> Đang dùng 4 nguồn</span><button>Chats <i className="bi bi-check"/></button><button>Tasks <i className="bi bi-check"/></button><button>Calendar <i className="bi bi-check"/></button><button>Memory <i className="bi bi-check"/></button></div><form className="personal-composer" onSubmit={e=>{e.preventDefault();send()}}><button type="button" className="icon-btn"><i className="bi bi-plus-lg"/></button><textarea rows="1" value={draft} onChange={e=>setDraft(e.target.value)} placeholder="Hỏi Orbit về công việc và lịch trình của bạn..." onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send()}}}/><button type="button" className="icon-btn"><i className="bi bi-mic"/></button><button className="personal-send" aria-label="Gửi"><i className="bi bi-arrow-up"/></button></form><small>Orbit có thể mắc lỗi. Hãy kiểm tra lại thông tin quan trọng.</small></div>
  </section>
}
