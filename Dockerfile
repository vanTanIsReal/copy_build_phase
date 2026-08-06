# ---- Stage 1: Build ----
FROM python:3.11-slim AS builder

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ---- Stage 2: Production ----
FROM python:3.11-slim

WORKDIR /app

# Copy Python packages and executable commands
COPY --from=builder /install /usr/local

# Create non-root user
RUN useradd --create-home appuser

# Copy application code
COPY . .

# Give appuser permission to project files
RUN mkdir -p /app/data \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]