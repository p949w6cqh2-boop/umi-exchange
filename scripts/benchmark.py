#!/usr/bin/env python
"""Load + query-count benchmark for UMI Exchange.

Reports, per endpoint: **DB queries / request** (an N+1 catcher — a healthy page
shows a small constant count, not ~1/item) and **p50 / p95 latency** under
concurrency, against a SEEDED realistic dataset.

It seeds data, issues load, then DELETEs it, so as a safety gate it prints the
*resolved* target DB and refuses to run unless --i-know-this-is-not-prod is passed
(and refuses outright if the DB host matches $BENCH_PROD_HOST). The DB is chosen by
DATABASE_URL independently of the settings module, so the gate checks the resolved
connection, not the module name.

    DJANGO_SETTINGS_MODULE=config.settings.development \\
    .venv/bin/python scripts/benchmark.py --seed 300 --requests 300 \\
        --concurrency 100 --i-know-this-is-not-prod

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
    if c:
        # Needs/Offers PROTECT their Category, so clear them before the Community
        # delete cascades the Categories + Members.
        Need.objects.filter(community=c).delete()
        Offer.objects.filter(community=c).delete()
        c.delete()  # cascades members + categories
    # Member.user / Community.created_by are FKs *to* User, so the seeded users
    # aren't reachable from the Community cascade — delete them by the bench
    # username prefixes (also clears orphans left by a crashed run).
    User = get_user_model()  # noqa: N806
    User.objects.filter(username__startswith="bench-").delete()
    User.objects.filter(username__startswith="bm-").delete()


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

    # Prod safety: the DB is chosen by DATABASE_URL independently of the settings
    # MODULE name, so gate on the *resolved* connection — not the module label —
    # and show exactly which DB will be seeded + wiped before requiring the flag.
    db = connection.settings_dict
    target = f"{db.get('NAME')} @ {db.get('HOST') or 'local'}"
    print(f"Target DB: {target} (engine: {db.get('ENGINE', '').rsplit('.', 1)[-1]})")
    prod_host = os.environ.get("BENCH_PROD_HOST", "")
    if prod_host and prod_host in str(db.get("HOST", "")):
        sys.exit(f"REFUSING: target DB host matches BENCH_PROD_HOST ({prod_host}) — this seeds + DELETEs rows.")
    if not args.i_know_this_is_not_prod:
        sys.exit(
            "REFUSING: this seeds data, issues load, then DELETEs it.\n"
            f"  Target: {target}\n"
            "  Re-run with --i-know-this-is-not-prod once you've confirmed that is a scratch/dev/staging DB."
        )

    print(f"Seeding {args.seed} needs + {args.seed} offers …")
    try:
        community, member, need = seed(args.seed)
        user = member.user
        endpoints = {
            "community-feed": reverse("community-feed", kwargs={"slug": community.slug}),
            "need-detail": reverse("need-detail", kwargs={"slug": community.slug, "pk": need.id}),
            "community-dashboard": reverse("community-dashboard", kwargs={"slug": community.slug}),
        }
        # Warm process-global caches (ContentType, etc.) so the first endpoint's
        # query count isn't inflated by one-time lookups.
        query_count(user, endpoints["community-feed"])
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
        print("\nqueries/req = per-request count for a full (capped) page: feed paginate_by=20,")
        print("need-detail slices [:5]. Healthy = a small constant; an N+1 shows as a count that")
        print("tracks the rendered page size — seed >= one page to exercise it (counts don't grow")
        print("past the cap by design). Absolute ms are in-process; point at staging for SLA numbers.")
    finally:
        cleanup()
        print("\nCleaned up seeded benchmark data.")


if __name__ == "__main__":
    main()
