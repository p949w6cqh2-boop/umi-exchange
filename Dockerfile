# ── Multi-stage Dockerfile for UMI Exchange ──
# This is the root Dockerfile for convenience. The canonical production
# Dockerfile lives at docker/Dockerfile.

# ── Stage 1: Build dependencies ──
FROM python:3.12-slim AS builder
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends libpq-dev gcc && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: Production image ──
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# Non-root user
RUN groupadd -r umi && useradd -r -g umi -d /app -s /sbin/nologin umi
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 curl && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local
WORKDIR /app
COPY --chown=umi:umi . .
RUN mkdir -p /app/logs /app/staticfiles && chown -R umi:umi /app/logs /app/staticfiles
RUN python manage.py collectstatic --noinput 2>/dev/null || true

USER umi
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD curl -sf http://localhost:8000/health/ || exit 1
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-"]
