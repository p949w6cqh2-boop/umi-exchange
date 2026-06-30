#!/usr/bin/env python
"""Load + query-count benchmark for UMI Exchange.

Reports, per endpoint: **DB queries / request** (an N+1 catcher — the count should
stay flat as the dataset grows) and **p50 / p95 latency** under concurrency, against
a SEEDED realistic dataset.

Runs against a SCRATCH / dev / staging DB — it seeds data and issues load, so it
REFUSES production settings unless --i-know-this-is-not-prod is passed. It cleans up
the data it seeds.

    DJANGO_SETTINGS_MODULE=config.settings.development \\
    .venv/bin/python scripts/benchmark.py --seed 300 --requests 300 --concurrency 100

For *real* WSGI concurrency numbers, point DATABASE_URL at a staging Postgres (the
in-process test client exercises the same view/ORM code; absolute latencies differ).
"""

import argparse
import os
import statistics
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import django

# Make the project root (parent of scripts/) importable so `config` / `apps` resolve.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
django.setup()

from django.conf import settings as _dj_settings  # noqa: E402

# The test Client sends Host: testserver; the pytest runner auto-allows it, a
# standalone script must (else every request is a 400 DisallowedHost).
_dj_settings.ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]

from django.contrib.auth import get_user_model  # noqa: E402
from django.db import connection  # noqa: E402
from django.test import Client  # noqa: E402
from django.test.utils import CaptureQueriesContext  # noqa: E402
from django.urls import reverse  # noqa: E402

from apps.communities.models import Category, Community, Member  # noqa: E402
from apps.needs.models import Need  # noqa: E402
from apps.offers.models import Offer  # noqa: E402

BENCH_SLUG = "benchmark-scratch"
_local = threading.local()


def seed(n):
    """Idempotent: drop any prior bench community, then create one community with
    members + n needs + n offers across a category. Returns (community, member, need)."""
    cleanup()  # clean slate (handles PROTECT ordering)
    User = get_user_model()  # noqa: N806 (Django convention for the user model)
    owner = User.objects.create(username=f"bench-{uuid.uuid4().hex[:8]}")
    community = Community.objects.create(name="Benchmark Scratch", slug=BENCH_SLUG, created_by=owner)
    cat = Category.objects.filter(community=community).first() or Category.objects.create(
        community=community, name="Bench", icon="🔧"
    )
    members = [
        Member.objects.create(
            user=User.objects.create(username=f"bm-{uuid.uuid4().hex[:8]}"),
            community=community,
            display_name=f"Member {i}",
            role="coordinator" if i == 0 else "member",
        )
        for i in range(20)
    ]
    needs = [
        Need.objects.create(community=community, requester=members[i % len(members)], category=cat, title=f"Need {i}")
        for i in range(n)
    ]
    for i in range(n):
        Offer.objects.create(community=community, offerer=members[i % len(members)], category=cat, title=f"Offer {i}")
    return community, members[0], needs[0]


def cleanup():
    c = Community.objects.filter(slug=BENCH_SLUG).first()
    if not c:
        return
    # Needs/Offers PROTECT their Category, so clear them before the Community
    # delete cascades the Categories.
    Need.objects.filter(community=c).delete()
    Offer.objects.filter(community=c).delete()
    c.delete()  # cascades members + categories


def _client(user):
    c = getattr(_local, "client", None)
    if c is None:
        c = _local.client = Client()
        c.force_login(user)
    return c


def query_count(user, url):
    """DB queries for a single request — deterministic; the N+1 signal."""
    c = Client()
    c.force_login(user)
    with CaptureQueriesContext(connection) as ctx:
        c.get(url)
    return len(ctx)


def load(user, url, requests_n, concurrency):
    lat = []

    def one(_):
        c = _client(user)
        t0 = time.perf_counter()
        c.get(url)
        return (time.perf_counter() - t0) * 1000.0

    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        lat = list(ex.map(one, range(requests_n)))
    lat.sort()
    p50 = statistics.median(lat)
    p95 = lat[min(len(lat) - 1, int(0.95 * len(lat)))]
    return p50, p95


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=300, help="needs + offers to create")
    ap.add_argument("--requests", type=int, default=300)
    ap.add_argument("--concurrency", type=int, default=100)
    ap.add_argument("--i-know-this-is-not-prod", action="store_true")
    args = ap.parse_args()

    if "production" in os.environ.get("DJANGO_SETTINGS_MODULE", "") and not args.i_know_this_is_not_prod:
        sys.exit("REFUSING: production settings. This seeds data + issues load — point it at scratch/staging.")

    print(f"Seeding {args.seed} needs + {args.seed} offers …")
    community, member, need = seed(args.seed)
    user = member.user
    endpoints = {
        "community-feed": reverse("community-feed", kwargs={"slug": community.slug}),
        "need-detail": reverse("need-detail", kwargs={"slug": community.slug, "pk": need.id}),
        "community-dashboard": reverse("community-dashboard", kwargs={"slug": community.slug}),
    }
    try:
        print(
            f"\n{'endpoint':24} {'queries/req':>12} {'p50 ms':>9} {'p95 ms':>9}   "
            f"(load: {args.requests} req @ {args.concurrency} concurrent)"
        )
        print("-" * 72)
        for name, url in endpoints.items():
            q = query_count(user, url)
            p50, p95 = load(user, url, args.requests, args.concurrency)
            flag = "  <-- N+1?" if q > 40 else ""
            print(f"{name:24} {q:>12} {p50:>9.1f} {p95:>9.1f}{flag}")
        print("\nqueries/req should stay ~flat as --seed grows; a count that scales with the")
        print("dataset is an N+1. Absolute ms are in-process (relative); use staging for SLA numbers.")
    finally:
        cleanup()
        print("\nCleaned up seeded benchmark data.")


if __name__ == "__main__":
    main()
