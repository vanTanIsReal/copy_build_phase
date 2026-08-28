# Memory Harness — PostgreSQL thật

- Database: PostgreSQL 17.10, database test riêng `orbit_agent_eval_test` trên `127.0.0.1:55432`
- Kết quả: **9/9 PASS**, 0 failure, 0 error, 10,57 giây
- Fixture SQLite trong `tests/conftest.py`: **đã bỏ qua cho lần chạy này**
- Repository, lifecycle/TTL, isolation, semantic retrieval, context budget và maintenance đều chạy
  trên PostgreSQL thông qua `postgresql+asyncpg`.

Database local cô lập được dùng vì harness tạo/xóa schema và dữ liệu. Không chạy thao tác phá hủy này
trên PostgreSQL production của deployment.
