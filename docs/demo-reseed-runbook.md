# Droplet re-seed runbook — American-English demo strings

Replaces the St. Brigid's demo data on the production droplet (reciprocalaid.network,
143.244.167.7) with the localized American-English seed. **Run by hand, by the founder** —
it deletes demo rows, which is behind the keyring. Everything it touches is fictional demo
data; the hard stop below aborts if that ever stops being true.

Why a flush is mandatory: the seed's `get_or_create` keys needs/offers by **title**. The
localization retitled them, so re-seeding over the old rows would create a second, parallel
set (14 needs, 12 offers) instead of updating in place. Flush first, then seed fresh.

Order matters: deploy the new code **before** seeding — the strings live in the image.

## 0. Back up (2 min)

```bash
ssh root@143.244.167.7
cd /opt/umi-exchange   # adjust if the checkout lives elsewhere
bash scripts/backup.sh
ls -la /var/backups/umi/   # confirm today's dump exists before going further
```

## 1. Deploy the new code (5 min)

After the `localize-demo-american-english` branch is merged to main:

```bash
git pull
# If that ABORTS on local changes: the droplet carried uncommitted live config until
# PR #89 (now merged) captured it. One-time reconcile, then pulls are clean forever:
#   git stash --include-untracked && git pull && git stash drop

# (To preview before merging instead: git fetch && git checkout localize-demo-american-english)

docker build -t umi-exchange:local .
docker compose --env-file .env -f docker/docker-compose.prod.yml up -d
docker compose --env-file .env -f docker/docker-compose.prod.yml ps   # app healthy
```

The rebuild is required — the seed command and the landing template are baked into the image
(`COPY . .`); pull + restart alone serves the old strings. Both Dockerfiles run collectstatic
under production settings (the WhiteNoise-manifest fix from PR #83), so a plain rebuild is safe.

## 2. Flush the old demo parish (2 min)

Deletion order is deliberate — `Need.category`, `CommunityPage.created_by`, `Resource.added_by`,
and `Flag.reporter` are `on_delete=PROTECT`, so a bare `community.delete()` raises
`ProtectedError`. Children go first, then the community cascade, then the demo users
(their emails all end in `@demo.invalid` — old usernames `tomas`/`sile` are swept up too).
Audit history survives: `AuditLog.user` is `SET_NULL`, and the append-only table is untouched.

```bash
docker compose --env-file .env -f docker/docker-compose.prod.yml exec -T app \
  python manage.py shell <<'PY'
from django.db import transaction

from apps.accounts.models import User
from apps.communities.models import Community, Member, Resource
from apps.matches.models import Match
from apps.moderation.models import Flag
from apps.needs.models import Need
from apps.offers.models import Offer
from apps.pages.models import CommunityPage
from apps.tags.models import MemberTag, Tag

SLUG = "st-brigids"
c = Community.objects.filter(slug=SLUG).first()
if c is None:
    raise SystemExit("No st-brigids community found — nothing to flush.")

# Hard stop: this script only ever touches the fictional demo parish.
if c.case_files.exists():
    raise SystemExit("ABORT: case files exist on this community — not demo-only. Do not flush.")

print("about to flush:",
      "members", Member.objects.filter(community=c).count(),
      "| needs", Need.objects.filter(community=c).count(),
      "| offers", Offer.objects.filter(community=c).count(),
      "| matches", Match.objects.filter(need__community=c).count())

with transaction.atomic():
    Match.objects.filter(need__community=c).delete()
    Flag.objects.filter(reporter__community=c).delete()      # PROTECT reporter — before members
    Need.objects.filter(community=c).delete()                # PROTECT category — before categories
    Offer.objects.filter(community=c).delete()
    CommunityPage.objects.filter(community=c).delete()       # PROTECT created_by — before members
    Resource.objects.filter(community=c).delete()            # PROTECT added_by — before members
    MemberTag.objects.filter(member__community=c).delete()
    Tag.objects.filter(community=c).delete()
    c.delete()  # cascades members, categories, households, notifications
    n, _ = User.objects.filter(email__endswith="@demo.invalid").delete()
    print("deleted demo user rows (incl. cascades):", n)

print("flush complete")
PY
```

## 3. Re-seed (1 min)

`seed_demo_parish` hard-refuses when `DEBUG` is off, and the prod container pins
`config.settings.production` (`DEBUG = False`). The override below applies development
settings to **this one command process only** — it reads the same `DATABASE_URL`/keys from
the compose env, serves nothing, and exits. Nothing about the running app changes.

```bash
docker compose --env-file .env -f docker/docker-compose.prod.yml run --rm --no-deps \
  -e DJANGO_SETTINGS_MODULE=config.settings.development -e DEBUG=True \
  app python manage.py seed_demo_parish
```

Expected closing line (exact counts matter):

> St. Brigid's demo parish is ready: 12 members, 7 needs, 6 offers, 3 matches.
> Sign in as marta (admin), tom (coordinator), or nuala (member) — password 'demo-parish' for all.

The coordinator sign-in is now **tom** (was `tomas`).

## 4. Verify (2 min)

```bash
curl -s https://reciprocalaid.network/ | grep -c "9:30 Mass"    # expect ≥ 1
curl -s https://reciprocalaid.network/ | grep -ci "half-nine"   # expect 0
curl -s https://reciprocalaid.network/health/                    # {"status": "ok"}
```

Then by eye: sign in as `tom` / `demo-parish`; the board should read American — a ride to
the 9:30 Mass, a leaky kitchen faucet, a crib for the new baby, the grocery run, math help
for Marco.

## Notes

- Re-running step 3 afterward is safe (idempotent); it only duplicates if step 2 is skipped.
- If anything looks wrong, the step-0 dump restores via
  `docker compose --env-file .env -f docker/docker-compose.prod.yml exec -T db psql -U umi umi_exchange < <dumpfile>`.
