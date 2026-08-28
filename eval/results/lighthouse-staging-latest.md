# Lighthouse / Web Vitals — Staging

Đo bằng system Chrome ở chế độ Lighthouse lab trên trang đăng nhập công khai.

| Deployment | Performance | Accessibility | LCP | CLS | Kết quả chính |
|---|---:|---:|---:|---:|---|
| User | 68 | 92 | 5.353 ms | 0,0027 | Performance/LCP **FAIL** |
| Admin | 81 | 83 | 3.726 ms | 0 | Accessibility/LCP **FAIL** |

Gate: Performance >= 80, Accessibility >= 90, LCP <= 2.500 ms, CLS <= 0,1.

INP không được suy diễn từ navigation-only Lighthouse. Muốn có INP phải thu thập RUM từ người dùng
thật hoặc chạy kịch bản tương tác chuyên biệt. Axe E2E trên các trang đã đăng nhập được ghi trong
`browser-e2e-staging-latest.json`.
