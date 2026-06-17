# St. Patrick Implementation Playbook

*A 90-day guide to launching UMI Exchange at St. Patrick parish.*
*Based on the `main` branch. See `STATE.md` for the verified feature list.*

---

## 1. Executive summary

> *"All the believers were one in heart and mind. No one claimed that any of
> their possessions was their own, but they shared everything they had… And
> there were no needy persons among them. For from time to time those who owned
> land or houses sold them, brought the money from the sales and put it at the
> apostles' feet, and it was distributed to anyone who had need."*
> — **Acts 4:32–37**

The earliest Church kept a simple, sacred practice: those who had something to
give were connected to those in need, and the community made sure **no one was
overlooked**. UMI Exchange is a quiet digital tool for doing exactly that, today,
inside one parish.

**What it is.** A private, parish-only board where members post **needs** ("I
need a ride to chemo on Thursdays") and **offers** ("I can fix small plumbing
problems"). A coordinator — or the members themselves — connect the two. Contact
details stay hidden until **both people agree to be matched**, so it is safe and
unintrusive. It looks less like an app and more like a parish bulletin: warm,
calm, and uncluttered.

**Why St. Patrick needs it.** Right now, requests for help travel by memory and
word of mouth — a note in the office, a mention after Mass, a name someone half
remembers. Things fall through the cracks. This gives the parish one trustworthy
place to see who needs help and who can give it, without anyone's phone number
ending up on a public list.

**What the pilot will achieve.** Over 90 days we will stand the tool up, train a
small coordinator team, quietly invite volunteers, then open it to the whole
parish — and measure whether it genuinely helps neighbors help neighbors. At the
end, Father and the team decide whether to keep it, grow it, or set it down.

---

## 2. Pilot timeline (90 days)

A steady, unhurried pace. Each phase is two weeks.

### Weeks 1–2 — Setup (technical)
- Provision a small server (VPS) or arrange hosting.
- Install Docker, run the hardening script, configure the environment.
- Deploy the app, run database setup, confirm the health check is green.
- Create the St. Patrick community and the first **admin** (coordinator) account.
- *Outcome:* a working, secured site at the parish's web address.

### Weeks 3–4 — Onboard the coordinator team
- Gather 2–4 trusted people (staff or reliable volunteers) as coordinators.
- Walk them through the **coordinator workflows** (Section 5) using a few
  practice needs and offers.
- Print the **quick-start guide** (Section 4) and the parish **QR code**.
- Turn on **2FA** for coordinator accounts (recommended — Section 6).
- *Outcome:* a team that can post, match, and answer questions confidently.

### Weeks 5–6 — Soft launch (small group)
- Invite ~10–20 volunteers the coordinators already trust.
- Seed the board with a handful of real needs and offers so it isn't empty.
- Watch for confusion; fix wording, categories, anything awkward.
- *Outcome:* a small, friendly proof that the flow works end to end.

### Weeks 7–8 — Parish-wide announcement
- Run the **bulletin announcement** and **pulpit script** (Section 4).
- Display the QR code at exits and in the bulletin.
- Coordinators staff a table after Mass for one or two weekends to help people join.
- *Outcome:* the whole parish knows it exists and how to join.

### Weeks 9–10 — Monitor, support, iterate
- Coordinators check the **dashboard** a few times a week for stale needs.
- Follow up gently on needs that haven't been matched.
- Collect quick feedback ("Was this easy? Did it help?").
- *Outcome:* needs are actually getting met; rough edges smoothed.

### Weeks 11–12 — Evaluate and decide
- Pull the **success metrics** (Section 7).
- Hold a 30-minute review with Father and the coordinators.
- Decide: continue as-is, grow it, or pause. Plan any next steps (Section 8).
- *Outcome:* a clear, evidence-based decision.

---

## 3. Environment setup instructions (for the technical helper)

> This section is for whoever sets up the server. Everyone else can skip it.
> Commands assume a fresh Ubuntu VPS with Docker installed. Replace
> `app.stpatrick.org` with the parish's actual domain (or server IP).

**1. Clone the repository**
```bash
git clone https://github.com/your-org/umi-exchange.git /opt/umi-exchange
cd /opt/umi-exchange
```

**2. Harden the server** (firewall, fail2ban, automatic security updates, SSH)
```bash
sudo bash scripts/harden.sh
```

**3. Create the environment file** `.env`
```bash
cp .env.example .env
```
Then edit `.env` and set at least these. The two `python3 -c …` lines print a
fresh secret — paste each result in:
```bash
# Required
SECRET_KEY=<paste output of: python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())">
ENCRYPTION_KEY=<paste output of: python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">
ALLOWED_HOSTS=app.stpatrick.org
SITE_URL=https://app.stpatrick.org
DATABASE_URL=postgres://umi:${DB_PASSWORD}@db:5432/umi_exchange
DEBUG=False
DJANGO_SETTINGS_MODULE=config.settings.production

# Database password (used by the bundled Postgres container)
DB_PASSWORD=<choose a long random password>

# Optional but recommended
HEALTH_CHECK_TOKEN=<choose a random string>
SENTRY_DSN=            # leave blank unless you use Sentry
```
> The app **will refuse to start in production** if `SECRET_KEY` is the example
> value or `ENCRYPTION_KEY` is blank — this is intentional, so a misconfigured
> server can't go live insecurely.

**4. Point the web server at your domain.** Edit `docker/Caddyfile.prod` and
replace the placeholder domain with `app.stpatrick.org`. Caddy will fetch an
HTTPS certificate automatically.

**5. Start everything (production)**
```bash
docker compose -f docker/docker-compose.prod.yml up -d
```

**6. Run database migrations and create the first coordinator**
```bash
docker compose -f docker/docker-compose.prod.yml exec app python manage.py migrate
docker compose -f docker/docker-compose.prod.yml exec app python manage.py createsuperuser
```

**7. Collect static files** (the warm parish styling). The image does this at
build time; run it again any time the design changes:
```bash
docker compose -f docker/docker-compose.prod.yml exec app python manage.py collectstatic --noinput
```

**8. Verify the health endpoint** — should return `ok`:
```bash
curl https://app.stpatrick.org/health/
# → {"status": "ok", "db": "ok", "cache": "ok"}
```

**9. Schedule a daily backup** (3 AM):
```bash
echo "0 3 * * * cd /opt/umi-exchange && bash scripts/backup.sh" | crontab -
```

You're live. Log in at `https://app.stpatrick.org/` with the coordinator account
and create the **St. Patrick** community (this also generates the join code).

---

## 4. Onboarding materials (ready to copy)

### Bulletin announcement (one paragraph)
> **Help One Another — St. Patrick's Care Board.** Our parish now has a simple,
> private way to ask for a hand and to offer one. Need a ride to an appointment,
> a meal during illness, help with yard work, or a tutor for a child? Able to
> give a little time or a skill? Join St. Patrick's Care Board, a members-only
> board where neighbors quietly connect. Your phone number stays private until
> *you* agree to a match. Scan the code in this bulletin or ask a parish
> coordinator after Mass to get started. *"There were no needy persons among
> them."* (Acts 4:34)

### Pulpit script (≈30 seconds, after Mass)
> "Before you go — our parish has a new, simple way to care for one another.
> It's called the St. Patrick Care Board. If you need help — a ride, a meal, a
> repair — or if you have a little time or a skill to share, you can join. It's
> private: your contact information is never shown until you choose to accept a
> match. There's a code in today's bulletin, and coordinators are at the doors to
> help you sign up. Let's make sure no one in our parish family is overlooked."

### QR code / join code
Each community has a unique join code and a matching QR image.
- **Placeholder join link:** `https://app.stpatrick.org/join/?code=STPATRICK` —
  the real code is generated automatically when the community is created.
- **To get the real QR code:** a coordinator (admin) opens **Community Settings**
  and uses the join-code / QR option there. Print that QR image for the bulletin
  and the welcome table. If a code is ever shared too widely, a coordinator can
  **regenerate** it from the same page (the old one stops working).

### One-page quick-start guide for volunteers (plain English)

**Welcome to the St. Patrick Care Board** 🌿
A private place to ask for help or offer it. Here's all you need to know.

**1. Join.** Point your phone camera at the parish QR code (or open the link from
the bulletin). You'll see a "Join" page. *On screen:* a single box asking for the
join code (already filled in) and your name. Tap **Join**.

**2. Look around.** You'll land on the **board** — a calm, cream-colored list of
cards. *On screen:* cards with a **green** edge are **needs** (someone asking for
help); cards with a **gold** edge are **offers** (someone able to help). Use the
search box or the category buttons at the top to filter.

**3. Offer help.** Tap **Post an Offer**, choose a category (e.g., "Transportation"),
write one line about what you can do, and tap post. *On screen:* a short form with
a few boxes; the green button at the bottom saves it.

**4. Ask for help.** Tap **Post a Need**, choose a category, describe what you
need, and pick how urgent it is. Your request appears as a green-edged card.

**5. Connect.** When you find a card you can help with (or that matches your need),
open it and tap **Propose Match**. The other person is notified. *On screen:* a
timeline shows the steps — Proposed → Accepted → Fulfilled.

**6. Share contact only when ready.** When someone proposes a match to you, you'll
see **Accept** and **Decline**. *On screen:* tapping Accept shows a gentle pop-up:
"Your contact info will be shared with the other party." Only **after you accept**
do phone/email appear — for both of you. Reach out, arrange the help, done.

**7. Finish.** Once the help has happened, open the match and tap **Mark
Fulfilled**. That's it.

**Your privacy:** No one sees your contact details until you accept a match. You
never have to post your home address — a general neighborhood is enough. If you
get stuck, ask a coordinator. Thank you for caring for our parish family. 🙏

---

## 5. Coordinator workflows (step by step)

Coordinators can do everything a member can, **plus** post on behalf of others,
oversee all matches, and see the dashboard.

### A. Post a need on behalf of a family
Some people can't or won't use a phone/computer. A coordinator can post for them.
1. Tap **Post a Need**.
2. Fill in the category, a short description, and urgency as usual.
3. In the **"On behalf of"** box, type the person's name (e.g., "the Romero
   family"). *This name is stored **encrypted** and is only there to help
   coordinators remember who the request is really for.*
4. Post it. The need now appears on the board for others to help with.

### B. Propose a match
1. Open a **need** card (green edge) you can pair with an offer — or open an
   **offer** card.
2. Tap **Propose Match**. If you're matching a specific offer, select it.
3. The need's owner is notified. The match now shows as **Proposed**.

### C. Accept a match and reveal contact info
1. Open the match (from a notification or the board).
2. Review the two sides. Tap **Accept Match** → confirm in the pop-up.
3. Contact details for both people now appear in the green box, and the other
   party is notified. *(Every time contact info is shown, the system records it
   in the audit log — see Section 6.)*

### D. Mark a match fulfilled
1. Once the help has actually happened, open the match.
2. Tap **Mark Fulfilled**. You may add a short note (e.g., "ride completed").
3. The need closes. The timeline shows Proposed → Accepted → Fulfilled.

### E. Use the coordinator dashboard
Open **Community Settings → Dashboard** (coordinators/admins only).
- **Metrics:** open needs, active offers, pending matches, and fulfilled counts
  for the period (week/month/quarter/year).
- **Stale needs:** needs that have sat too long without a match — these are your
  follow-up list. Reach out or propose a match.
- **Export (CSV):** download a spreadsheet of needs or matches for record-keeping
  or a report to Father. *(The download buttons produce `needs` and `matches`
  CSV files.)*

---

## 6. Privacy briefing (plain language)

This tool is built to protect people. In plain terms:

- **Contact info is hidden until a match is accepted.** Browsing the board, you
  never see anyone's phone or email. They appear **only** after both sides accept
  a match — to those two people (and, for oversight, a coordinator).
- **No street addresses.** The neighborhood field is for a **general area**
  ("Westside," "near the school"), not a house number. Encourage people to keep
  it general.
- **Every contact reveal is logged.** The system keeps a tamper-proof **audit
  log** of who viewed contact information and when. The log can be added to but
  **never edited or deleted** — even by an administrator.
- **Coordinators can see everything — so protect those accounts.** Coordinators
  can view all needs, offers, and matches. Because of that, we **strongly
  recommend turning on two-factor authentication (2FA)** for every coordinator
  account (an extra code from a phone app at login). It can be enabled for the
  parish instance.
- **The data stays under parish control.** St. Patrick can **self-host** the tool
  on its own server (the data lives there and nowhere else), or we can host it on
  the parish's behalf. Either way it is **private to the parish** — there is no
  public directory, no selling of data, no ads.

---

## 7. Success metrics (measure at 90 days)

Keep it simple. Most numbers come straight from the dashboard and CSV export.

| Metric | How to get it | Why it matters |
|---|---|---|
| **Needs posted** | Dashboard / needs CSV | Are people comfortable asking? |
| **Offers posted** | Dashboard / offers count | Is there capacity to give? |
| **Matches fulfilled** | Dashboard / matches CSV (status = fulfilled) | The real outcome — help delivered |
| **Avg. time from need → match** | Compare each need's posted date to its match's accepted date (matches CSV) | How responsive is the community? |
| **Volunteer feedback** | A 3-question survey or after-Mass chats | Did it save time? Was it easy? Would they use it again? |

A simple target for a first pilot: **a steady trickle of fulfilled matches and
volunteers who say it was easy and would use it again.** Numbers matter less than
whether real needs were quietly met.

---

## 8. Post-pilot roadmap

If the pilot succeeds, here's what could come next — in rough order.

### Extended protocol features (not yet built)
The current tool is **UMI Protocol v0.1 at "Core" level.** The next level adds:
- **Referrals** — a coordinator forwarding a need to a partner ministry or agency.
- **Attestations & trust badges** — members vouching for one another, with a small
  "Trusted" badge appearing after enough vouches (the badge design already exists
  as a placeholder; the logic behind it does not).
- **Network admin** — overseeing several parishes/communities from one place.

These are deliberately **not** in the pilot to keep it simple. They become worth
building once a single parish is thriving.

### Other "lakes" (companion tools from the wider vision)
The same calm, private approach can extend to related parish work, each as its own
small tool:
- **Case Notes** — a private, structured way for the St. Vincent de Paul / care
  team to track ongoing situations (with the same strict privacy and audit rules).
- **Skills Directory** — a searchable, opt-in list of parishioners' skills and
  trades, for when a specific kind of help is needed.

These are described here only so Father can see where it could go — none is part
of the pilot.

### Cost / tiers
For a single parish pilot, the **free, self-hosted tier is more than enough** — the
whole thing runs comfortably on a small ~$5–10/month server. There is no need to
pay for anything during the 90 days. A paid/hosted tier (we run and maintain it,
handle backups and updates) only becomes relevant if the parish would rather not
manage a server, or if multiple parishes join a shared network later.

---

*Father should be able to hand Sections 4–6 to a volunteer and say "follow this."
Section 3 is for the technical helper. Questions, or ready for the next lake?
Start a new chat and point it at `STATE.md` first.*
