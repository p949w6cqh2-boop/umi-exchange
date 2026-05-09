# UMI Exchange — Scaling Considerations

This document covers scaling strategies for the UMI Exchange reference implementation. For most communities (under 5,000 members), the default single-server deployment is sufficient. The strategies below apply when load increases or when a network admin oversees multiple communities.

## Current Architecture (Single Server)

```
[Browser] → [Caddy (TLS + static)] → [Gunicorn (3 workers)] → [PostgreSQL]
                                                              → [Redis (cache + sessions + queue)]
```

This handles ~100 concurrent users comfortably on a $10/month VPS (2 CPU, 4 GB RAM).

## Database: Connection Pooling

**When**: PostgreSQL connection count exceeds 100 (check with `SELECT count(*) FROM pg_stat_activity`).

**Solution**: Add PgBouncer between Gunicorn and PostgreSQL.

```yaml
# Add to docker-compose.prod.yml
pgbouncer:
  image: edoburu/pgbouncer:1.22
  environment:
    DATABASE_URL: postgres://umi:${DB_PASSWORD}@db:5432/umi_exchange
    POOL_MODE: transaction
    MAX_CLIENT_CONN: 200
    DEFAULT_POOL_SIZE: 20
  depends_on:
    - db
```

Update `DATABASE_URL` in the app to point to `pgbouncer:5432` instead of `db:5432`.

## Caching Strategy

Already configured via Redis. Key patterns:

- **Session data**: Stored in Redis (no DB queries for session validation)
- **Feed queries**: Cache category lists and member counts with 5-minute TTL
- **Dashboard metrics**: Cache with 60-second TTL to avoid expensive aggregations

```python
# Example: caching dashboard metrics
from django.core.cache import cache

def get_dashboard_metrics(community_id):
    key = f"dashboard:{community_id}"
    metrics = cache.get(key)
    if metrics is None:
        metrics = compute_metrics(community_id)
        cache.set(key, metrics, timeout=60)
    return metrics
```

## Static and Media Files

- **Static files**: Served by Caddy with `Cache-Control: public, max-age=31536000, immutable`. Whitenoise handles collectstatic.
- **User-uploaded media** (future): Use S3-compatible storage (Backblaze B2, MinIO, or AWS S3) with `django-storages`.

## Background Task Workers

Django-Q2 runs background tasks (need expiration, email sending). Scale by increasing workers:

```python
# config/settings/base.py
Q_CLUSTER = {
    "name": "umi",
    "workers": 4,  # Increase from 2 to 4
    "recycle": 500,
    "timeout": 120,
    "django_redis": "default",
}
```

Or run a separate worker container:

```yaml
worker:
  image: ghcr.io/your-org/umi-exchange:latest
  command: python manage.py qcluster
  env_file: ../.env
  depends_on:
    - db
    - redis
```

## Horizontal Scaling

Since sessions are stored in Redis (not in local memory), multiple app instances can run behind a load balancer without sticky sessions.

```yaml
app:
  image: ghcr.io/your-org/umi-exchange:latest
  deploy:
    replicas: 3
```

Caddy or an upstream load balancer distributes requests. No code changes needed.

## Database Read Replicas

**When**: Read-heavy workloads (many dashboard views, large feeds) cause DB CPU >80%.

**Solution**: Add a PostgreSQL read replica and configure Django's database router:

```python
DATABASES = {
    "default": env.db("DATABASE_URL"),
    "replica": env.db("DATABASE_REPLICA_URL"),
}

DATABASE_ROUTERS = ["config.db_router.ReadReplicaRouter"]
```

## When to NOT Scale

For most UMI deployments (parish of 200 families, mutual aid group of 500 members), a single $5–10/month VPS is more than sufficient. The biggest performance wins come from:

1. Database indexes (already defined in models)
2. Redis caching (already configured)
3. Caddy static file serving (already configured)
4. Query optimization (select_related/prefetch_related in views)

**Don't scale until you have evidence of a bottleneck.** The boring technology stack is chosen precisely because it handles typical community-scale loads without heroics.
