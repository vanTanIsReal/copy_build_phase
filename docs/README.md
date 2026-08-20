# Bộ tài liệu chuẩn — Orbit Multi-Agent

Thư mục này chỉ giữ tài liệu đang được dùng cho dự án Multi-Agent và vận hành liên quan. Team đọc theo thứ tự sau:

| Thứ tự | Tài liệu | Câu hỏi được trả lời |
|---|---|---|
| 1 | [Product Brief](BRIEF.md) | Sản phẩm là gì, giải quyết vấn đề nào và phạm vi MVP ra sao? |
| 2 | [PRD](PRD.md) | Nghiệp vụ, yêu cầu và acceptance criteria là gì? |
| 3 | [Architecture](ARCHITECTURE.md) | Component, data flow, authorization và current/target state được thiết kế thế nào? |
| 4 | [Enterprise Workspace Foundation](ENTERPRISE_WORKSPACE_FOUNDATION.md) | Company Root, Workspace, role, membership và lifecycle hoạt động ra sao? |
| 5 | [Multi-Agent Implementation Plan](MULTI_AGENT_IMPLEMENTATION_PLAN.md) | Bốn người chia việc, phụ thuộc, merge và release thế nào? |
| 6 | [Multi-Agent Test Dataset](MULTI_AGENT_TEST_DATASET.md) | Golden cases, taxonomy và eval data được chuẩn hóa thế nào? |
| 7 | [Deployment Guide](deploy.md) | Chạy và triển khai hệ thống thế nào? |

## Quy tắc single source of truth

- `BRIEF.md` khóa ý tưởng và ranh giới sản phẩm.
- `PRD.md` khóa hành vi và acceptance.
- `ARCHITECTURE.md` khóa giải pháp kỹ thuật và security boundary.
- `ENTERPRISE_WORKSPACE_FOUNDATION.md` khóa nghiệp vụ role/membership.
- `MULTI_AGENT_IMPLEMENTATION_PLAN.md` chỉ quản lý execution; không được tự thay đổi product/architecture contract.
- Mọi tài liệu phải phân biệt rõ **đã có trong code** và **mục tiêu cần triển khai**.
- Khi đổi contract, role, profile hoặc data boundary, PR phải cập nhật tài liệu canonical tương ứng cùng lúc.

## Thuật ngữ bắt buộc

- Một deployment Orbit là **một công ty**.
- `Company Root` là boundary ẩn do hệ thống tạo.
- “Workspace” trên sản phẩm là `AgentWorkspace` phòng ban nằm dưới Company Root.
- Ba Workspace Agent của MVP là `product_delivery`, `quality_assurance`, `executive`.
- Personal Agent là compatibility flow riêng, không tính là Workspace Agent thứ tư.
- Platform Admin tạo Workspace và phân lead/member; user không tự tạo Workspace.
- Executive Agent aggregate `WorkspaceBrief`, không mặc định đọc raw chat liên phòng ban.

## Tài liệu đã loại bỏ

Các giáo trình AI20K, AI log, branch report, kế hoạch lịch sử, wireframe cũ, Personal Agent spec rời rạc và các bản thiết kế trùng lặp đã được bỏ khỏi `docs/`. Chúng vẫn có thể khôi phục từ lịch sử Git nếu cần tra cứu, nhưng không còn là nguồn dùng để triển khai Multi-Agent.
