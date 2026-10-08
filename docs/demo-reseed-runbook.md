# Droplet re-seed runbook — American-English demo strings

Replaces the St. Brigid's demo data on the production droplet (reciprocalaid.network) with the
localized American-English seed. **Run by hand, by the founder** —
it deletes demo rows, which is behind the keyring. Everything it touches is fictional demo
data; the hard stop below aborts if that ever stops being true.

> **Updated 2026-10-08 for key custody** (`docs/key-custody-design.md`). The droplet is now
> `root@157.230.185.124` (the `143.244.167.7` host was destroyed 2026-09-05; never ssh to it).
> Its `.env` holds **no keys**: they live only in the running app container's stored config. So:
> deploy with the custody rig (§1), and run every management command **inside the running
> container** with `docker exec` (§3, §3b). A new container from `compose run`/`compose up` reads
> `.env` alone and has no keys. Proven on production 2026-10-07: §3 as written below, the exact
> closing line, then §3b.
>
> **The flush (§2) is only for a seed that RETITLES rows.** The seed matches needs and offers by
> title and repairs everything else in place (phones, contact choices, verification, the demo
> ride's first yes), so a reseed after a non-retitling change skips §2. It was skipped 2026-10-07.

Why a flush is mandatory: the seed's `get_or_create` keys needs/offers by **title**. The
localization retitled them, so re-seeding over the old rows would create a second, parallel
set (14 needs, 12 offers) instead of updating in place. Flush first, then seed fresh.

Order matters: deploy the new code **before** seeding — the strings live in the image.

## 0. Back up (2 min)

```bash
ssh root@157.230.185.124
cd /opt/umi-exchange
bash scripts/backup.sh     # expect "Remote upload verified" and the key ciphertext beside the dump
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

docker build -t umi-exchange:local -f docker/Dockerfile .
```

Then bring it up **from the laptop**, with the custody rig (it decrypts the keys, pipes them to
droplet tmpfs, recreates the app, shreds them, and runs `migrate`). A plain `compose up` on the
droplet no longer works: `.env` holds no keys.

```bash
# on the laptop, in the umi-exchange checkout
UMI_DROPLET=root@157.230.185.124 scripts/deploy-with-keys.sh deploy
UMI_DROPLET=root@157.230.185.124 scripts/deploy-with-keys.sh check    # "clean: droplet .env holds no plaintext key material"
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
settings to **this one command process only**, inside the RUNNING app container, so it reads the
real `DATABASE_URL` and keys from that container's environment, serves nothing, and exits.
Nothing about the running app changes. (Before key custody this used `compose run --rm`; that
starts a new container from `.env`, which no longer holds the keys.)

```bash
docker exec -e DJANGO_SETTINGS_MODULE=config.settings.development -e DEBUG=True \
  docker-app-1 python manage.py seed_demo_parish
```

Expected closing line (exact counts matter):

> St. Brigid's demo parish is ready: 12 members, 7 needs, 6 offers, 3 matches.
> Sign in as marta (admin), tom (coordinator), or nuala (member) — password 'demo-parish' for all.
> On a live site, run rotate_demo_password next: that password is public.

The coordinator sign-in is now **tom** (was `tomas`).

## 3b. Take the demo off the public password (1 min)

The password that closing line prints is written in this public repository. On a live site it
opens the demo parish's admin and coordinator accounts to anyone, and a coordinator can vouch
**any** account on the site as a verified human. Replace it straight away. The new password
lives only in the steward's private file (`~/.config/umi/demo-password.txt` on the laptop, mode
600) and travels on stdin, so it never appears on a command line, in a process list or in a log:

```bash
ssh root@157.230.185.124 'docker exec -i docker-app-1 python manage.py rotate_demo_password' \
  < ~/.config/umi/demo-password.txt
```

Expected: `Rotated the password on 12 seeded demo accounts.` Each rotation is audited.

## 4. Verify (2 min)

```bash
curl -s https://reciprocalaid.network/ | grep -c "9:30 Mass"    # expect ≥ 1
curl -s https://reciprocalaid.network/ | grep -ci "half-nine"   # expect 0
curl -s https://reciprocalaid.network/health/                    # {"status": "ok"}
```

Then by eye: sign in as `tom` with the password from the steward's file; the board should read American — a ride to
the 9:30 Mass, a leaky kitchen faucet, a crib for the new baby, the grocery run, math help
for Marco.

## Notes

- Re-running step 3 afterward is safe (idempotent); it only duplicates if step 2 is skipped.
- If anything looks wrong, the step-0 dump restores via
  `docker compose --env-file .env -f docker/docker-compose.prod.yml exec -T db psql -U umi umi_exchange < <dumpfile>`.
