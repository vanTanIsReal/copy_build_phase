import { Component } from 'react'

export default class AppErrorBoundary extends Component {
  state = { hasError: false }
  static getDerivedStateFromError() { return { hasError: true } }
  componentDidCatch(error) { console.error('Orbit UI error:', error) }
  render() {
    if (!this.state.hasError) return this.props.children
    return (
      <main className="auth-page orbit-fx d-flex align-items-center justify-content-center p-4">
        <section className="content-card text-center p-4" role="alert">
          <i className="bi bi-exclamation-triangle text-warning fs-1" />
          <h1 className="h4 mt-3">Orbit gặp lỗi hiển thị</h1>
          <p className="text-muted">Dữ liệu vẫn an toàn. Hãy tải lại trang để tiếp tục.</p>
          <button className="btn btn-primary" onClick={() => window.location.reload()}>Tải lại trang</button>
        </section>
      </main>
    )
  }
}