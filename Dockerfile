# ---- Stage 1: Build ----
FROM python:3.11-slim AS builder

# Cài vào một virtualenv độc lập ở /opt/venv thay vì `pip install --user` (đích /root/.local).
# LÝ DO — đây là bug chặn deploy của bản Dockerfile trước: trên Debian, /root có mode 0700, nên
# sau `USER appuser` tiến trình KHÔNG traverse được vào /root/.local -> PATH=/root/.local/bin vô
# dụng -> `uvicorn: command not found`, container exit ngay. /opt/venv thì mọi user đọc được.
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH

WORKDIR /app
COPY requirements.txt .
RUN pip install --retries 5 --timeout 120 -r requirements.txt

# ---- Stage 2: Runtime ----
FROM python:3.11-slim

# PYTHONUNBUFFERED: src/main.py dùng print() cho log khởi động. stdout của Python khi ghi vào pipe
# (docker/Render) là block-buffered -> không có biến này, traceback lúc init_db()/init_checkpointer()
# có thể không kịp xuất hiện trước khi container chết, rất khó debug deploy hỏng.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/opt/venv/bin:$PATH

RUN useradd -m -u 10001 appuser

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=appuser:appuser . .

# CHROMA_PERSIST_DIR mặc định ./data/chroma. LƯU Ý: trên Render/container disk là ephemeral —
# thư mục này bị xoá sạch mỗi lần deploy. Cần bền vững thì phải gắn persistent disk (mất phí) hoặc
# chuyển vector store sang pgvector trên chính Postgres. Xem DEPLOYMENT.md.
RUN mkdir -p /app/data && chown appuser:appuser /app/data

USER appuser

EXPOSE 8000

# Render dùng healthCheckPath trong render.yaml, không đọc HEALTHCHECK này; nó phục vụ
# docker-compose (phương án tự host VPS) để restart container khi app treo.
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/health')" || exit 1

# Shell form (không phải exec-form JSON array) để $PORT được expand lúc container start — Render
# inject biến PORT và bắt buộc app bind đúng cổng đó; exec-form hardcode sẽ bỏ qua. ${PORT:-8000}
# fallback về 8000 khi không có PORT (docker-compose local).
#
# --proxy-headers + --forwarded-allow-ips='*': app luôn nằm sau reverse proxy (Render edge / Caddy).
# Không có 2 cờ này uvicorn thấy scheme "http" và IP của proxy, làm sai URL tự sinh và log IP client.
# An toàn vì container không bao giờ nhận traffic trực tiếp từ Internet.
CMD uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'
