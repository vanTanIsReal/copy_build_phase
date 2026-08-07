const contextSources = [
  {icon:'bi-chat-dots',label:'Cuộc trò chuyện',value:'8',color:'#526ff5'},
  {icon:'bi-check2-square',label:'Task đang mở',value:'7',color:'#8b5cf6'},
  {icon:'bi-calendar4-week',label:'Sự kiện tuần này',value:'5',color:'#10b981'},
  {icon:'bi-journal-bookmark',label:'Memory',value:'12',color:'#f59e0b'},
]

export default function AssistantContextPanel({open,onClose}) {
  return <><div className={`context-backdrop ${open?'show':''}`} onClick={onClose}/><aside className={`assistant-context ${open?'open':''}`}>
    <div className="context-title"><div><span>Bối cảnh của bạn</span><h3>Tổng quan hôm nay</h3></div><button className="icon-btn context-close" onClick={onClose}><i className="bi bi-x-lg"/></button></div>
    <div className="context-source-grid">{contextSources.map(x=><div key={x.label}><span style={{background:`${x.color}12`,color:x.color}}><i className={`bi ${x.icon}`}/></span><strong>{x.value}</strong><small>{x.label}</small></div>)}</div>
    <section className="context-section"><div className="context-section-head"><h4><i className="bi bi-calendar-event"/> Tiếp theo</h4><button>Xem lịch</button></div><div className="next-event-card"><div className="event-time-block"><strong>15:30</strong><span>Hôm nay</span></div><div><h5>Product launch call</h5><p><i className="bi bi-people"/> 6 người tham gia</p><small>Còn 2 giờ 15 phút</small></div></div></section>
    <section className="context-section"><div className="context-section-head"><h4><i className="bi bi-check2-square"/> Cần chú ý</h4><button>Xem task</button></div><div className="attention-list"><div><span className="attention-dot danger"/><p><strong>Send revised proposal</strong><small>Quá hạn • Northstar</small></p><b>High</b></div><div><span className="attention-dot warning"/><p><strong>Review launch messaging</strong><small>Hôm nay, 11:00</small></p><b>Today</b></div><div><span className="attention-dot primary"/><p><strong>Weekly analytics report</strong><small>Ngày mai, 16:00</small></p><b>Next</b></div></div></section>
    <section className="context-section"><div className="context-section-head"><h4><i className="bi bi-journal-bookmark"/> Memory liên quan</h4><button>Xem tất cả</button></div><div className="related-memory"><i className="bi bi-lightbulb"/><p>Bạn thường muốn được nhắc trước cuộc họp <strong>30 phút</strong>.</p></div></section>
    <div className="context-permission"><i className="bi bi-shield-check"/><div><strong>Bạn kiểm soát dữ liệu</strong><p>Orbit chỉ đọc những nguồn bạn đã cấp quyền.</p></div><button className="icon-btn"><i className="bi bi-chevron-right"/></button></div>
  </aside></>
}
