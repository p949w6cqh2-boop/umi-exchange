# Layer C mid-fi — greyscale Commons (Stage 7)

> Structure, hierarchy, spacing, and copy are real; color is deliberately withheld until
> Stage 8. Fictional St. Patrick's seed content throughout (the §J seed canon: Our story +
> Mass times live, Ministries draft, Old bulletin archived; Nuala the member, Fr. Declan
> the admin). Screen 01 is not a mockup — it's the REAL /protocol/ page from
> `slice/platform-floor`, shot live at DEBUG=0, footer-click and TOC-jump verified.

## Shots — `shots/`, 390px-first + 1280 desktop, keyed variant states at 390

| screen | base | variant states (`?v=`) |
|---|---|---|
| 01 /protocol/ (real, Layer P) | 390 + desktop | — |
| 02 settings → identity | 390 + desktop | — |
| 03 pages manager | 390 + desktop | `empty` |
| 04 page editor | 390 + desktop | `coordinator`, `published` |
| 05 page, member view | 390 + desktop | `draft`, `hidden` |
| 06 page, anonymous view | 390 + desktop | — |
| 07 /p/ index | 390 + desktop | `anon`, `coord`, `empty` |
| 08 hub, personalized | 390 + desktop | — |
| 09 tombstone (no title — keyed) | 390 + desktop | `coord` (restore line) |
| 10 moderation queue, page row | 390 + desktop | — |

## Rebuild

```bash
python3 -m http.server 8124 -d docs/wireframes/identity/midfi &
DEBUG=0 DATABASE_URL=sqlite:////tmp/midfi.db3 .venv/bin/python manage.py migrate -v0
DEBUG=0 DATABASE_URL=sqlite:////tmp/midfi.db3 .venv/bin/python manage.py collectstatic --noinput
DEBUG=0 DATABASE_URL=sqlite:////tmp/midfi.db3 .venv/bin/python manage.py runserver 127.0.0.1:8123 &
npm i --no-save playwright && npx playwright install chromium
node docs/wireframes/identity/midfi/shoot.mjs
```

Lo-fi wireframes (the keyed source of these screens): `../` — one file per screen,
REGIONS/AUTHZ/EMPTY/SAFETY/VARIANTS annotations there, not here.
