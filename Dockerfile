# ── Multi-stage Dockerfile for UMI Exchange ──
# This is the root Dockerfile for convenience. The canonical production
# Dockerfile lives at docker/Dockerfile.

# ── Stage 1: Build dependencies ──
FROM python:3.12-slim AS builder
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends libpq-dev libffi-dev gcc && rm -rf /var/lib/apt/lists/*
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

USER umi

# collectstatic MUST run under production settings so the WhiteNoise manifest
# (CompressedManifestStaticFilesStorage) is generated. The dev default uses a non-manifest
# storage and would ship an EMPTY manifest -> prod 500s "Missing staticfiles manifest entry".
# USER umi is set first so the collected tree is owned by the runtime user. Errors are NOT
# swallowed: a broken static build must fail the image build, not ship silently. The throwaway
# build-only env just lets production settings import (there is no .env at build time); the
# running container reads the real .env via compose.
RUN DJANGO_SETTINGS_MODULE=config.settings.production \
    SECRET_KEY=build-only-not-used-at-runtime \
    ENCRYPTION_KEY="$(python -c 'import base64; print(base64.urlsafe_b64encode(b"0"*32).decode())')" \
    DATABASE_URL="postgres://u:p@localhost:5432/db" \
    REDIS_URL="redis://localhost:6379/0" \
    ALLOWED_HOSTS="localhost" \
    DEBUG="False" \
    python manage.py collectstatic --noinput
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD curl -sf http://localhost:8000/health/ || exit 1
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-"]
