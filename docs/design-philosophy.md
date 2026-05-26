# UMI Exchange — Design Philosophy

## Why This System Exists

> *"While AI promises to boost productivity by taking over mundane tasks, it frequently forces workers to adapt to the speed and demands of machines, rather than machines being designed to support those who work. As a result, contrary to the advertised benefits of AI, current approaches to technology can paradoxically de-skill workers, subject them to automated surveillance and relegate them to rigid and repetitive tasks. The need to keep up with the pace of technology can erode workers' sense of agency and stifle the innovative abilities they are expected to bring to their work."* [152]
>
> *"Precisely in order to avoid this drift, it is necessary to design systems that are centered on the human person and not solely on performance."*

This passage names a fundamental tension in the way technology is built today. UMI Exchange was designed, from the very first line of code, as a direct answer to this tension. Below is a step-by-step account of how we arrived at each architectural decision — and why each one is, at its core, a human decision, not a performance decision.

---

## Step 1: We Started With the Person, Not the Platform

**The drift to avoid:** Most mutual aid platforms begin with a data model — "what entities do we need?" — and work outward to a user interface. The person who needs a ride to a doctor's appointment becomes a row in a `needs` table. The neighbour who can help becomes a row in `offers`. The platform optimises for matching speed, not for the texture of the relationship between them.

**What we did instead:** We started with the UMI Protocol — a *specification* that begins with the language of gift and reciprocity, not the language of transactions. The protocol defines a `Need` not as a ticket to be resolved but as an act of vulnerability: someone in a community saying *"I need help."* An `Offer` is not a service listing but an act of generosity: *"I can help."* A `Match` is not an algorithmic assignment but a **mutual consent** between two people who know each other's names.

This is why the very first model we wrote was not `Need` or `Offer` but `Community`. You cannot have reciprocity between strangers on the internet. You can only have it between people who belong to each other — a parish, a mutual aid group, a neighbourhood. The community is not a "tenant" in a multi-tenant SaaS. It is the *ground* on which trust grows.

---

## Step 2: We Chose "Boring Technology" to Serve the Operator, Not to Impress

**The drift to avoid:** *"The need to keep up with the pace of technology can erode workers' sense of agency."* A parish secretary who volunteers four hours a week to coordinate meals for new mothers should not need to understand Kubernetes, React hydration, or WebSocket protocols. When we choose a fashionable stack, we are not serving the operator — we are **subjecting** them to our preferences, forcing them to adapt to the speed and demands of tools designed for venture-funded engineering teams.

**What we did instead:** Every technology in the stack has 10+ years of production use:

| Technology | Age | Why |
|-----------|-----|-----|
| Python | 1991 | The parish volunteer can read the code |
| Django | 2005 | One framework does auth, ORM, templates, forms |
| PostgreSQL | 1996 | Runs on a $5/month VPS for years |
| Redis | 2009 | Session cache, task queue, no configuration ceremony |
| HTMX | 2020 | Dynamic UI without a JavaScript build pipeline |
| Alpine.js | 2019 | 1.2 KB of client-side state, readable inline |
| Tailwind CSS | 2017 | Utility classes, no CSS compilation required at runtime |
| Docker + Caddy | 2013/2015 | `docker compose up` and you're running |

The operator does not need to "keep up." They run `bash scripts/setup.sh`. They run `python manage.py runserver`. The technology disappears behind the human act it enables.

---

## Step 3: We Made the Machine Adapt to the Person — Not the Reverse

**The drift to avoid:** *"AI frequently forces workers to adapt to the speed and demands of machines."* In most platforms, the matching algorithm decides who gets help. The user is presented with an assignment and must accept or reject it on the algorithm's timeline.

**What we did instead:** There is no matching algorithm. UMI Exchange implements a **human-driven** matching flow:

1. **A person posts a Need.** They choose the category, the urgency, the neighbourhood. They write the description in their own words. The system does not auto-classify, does not suggest urgency, does not rewrite their words.

2. **Another person sees it and chooses to help.** They click "Propose Match." This is not an assignment. It is a *proposal* — the word matters.

3. **The first person accepts or declines.** Only after mutual consent does contact information appear. The machine does not decide. The machine *waits*.

The state machine (`proposed → accepted → fulfilled`) is not a workflow engine optimising throughput. It is a *protocol of consent*. Each transition requires a human hand on a button and a human eye on a confirmation dialog: *"Your contact info will be shared with the other party."*

The `Match.transition_to()` method enforces this:
- `proposed → accepted` — requires a person to click "Accept"
- `accepted → fulfilled` — requires a person to click "Mark Fulfilled"
- `fulfilled → anything` — **blocked**. The machine cannot undo what a person has completed
- A person cannot match with themselves (Section 8.6)
- Race conditions are handled with `SELECT FOR UPDATE` — but the *decision* is never automated

---

## Step 4: We Refused Automated Surveillance

**The drift to avoid:** *"Current approaches to technology can paradoxically de-skill workers, subject them to automated surveillance and relegate them to rigid and repetitive tasks."*

**What we did instead:**

- **No behavioural tracking.** There are no analytics events. No scroll depth tracking. No "engagement" metrics. The dashboard shows only *aggregate* counts: how many needs are open, how many are fulfilled, how many are stale. It does not show who is "performing" and who is not.

- **IP addresses are hashed** in the audit log (`AuditLog.log()` uses a one-way hash). We log *that* something happened, not *who* did it from *where*.

- **Contact information is encrypted at rest** (Fernet encryption for `on_behalf_of` fields). Even a database breach does not expose the most vulnerable people.

- **The neighbourhood field warns you.** When a person enters their area, a yellow caution box says: *"Use a general area (e.g., 'Westside') rather than your street address. This field is visible to all community members."* The machine does not silently collect location data. It actively warns you about the privacy implications of what you're sharing.

- **Contact revelation follows a protocol** (Section 8.2). Before a match is accepted, the contact info box shows a locked padlock and the words: *"Contact info will appear here after this match is accepted."* The person sees the lock. They know nothing is being shared without their consent. This is not a feature. It is a *promise*.

---

## Step 5: We Designed the Dashboard to Support the Coordinator, Not to Replace Them

**The drift to avoid:** *"Technology can paradoxically de-skill workers."* A coordinator who uses a dashboard that makes all the decisions for them is not being supported — they are being **deskilled**. They become a button-presser, not a community leader.

**What we did instead:** The dashboard shows:
- **Stale Needs** (open for 7+ days with no matches) — but it does not auto-assign someone to help. It shows the coordinator *where attention is needed* and trusts them to respond with human judgment. Maybe the need is stale because the person resolved it privately. Maybe it's stale because it's a hard one. The coordinator knows; the machine doesn't.
- **Aggregate metrics** — but no individual performance scores. No "top volunteers" leaderboard. Mutual aid is not a competition.
- **CSV export** — the coordinator can take the data *out* of the system. They are not locked in. They can open it in a spreadsheet, discuss it in a meeting, print it out. The system is a tool in their hands, not a cage around their work.

---

## Step 6: We Made Progressive Enhancement the Architecture, Not the Exception

**The drift to avoid:** *"Relegating workers to rigid and repetitive tasks."* A system that requires JavaScript to function, that requires a modern browser, that requires a fast internet connection — such a system *excludes* the very people mutual aid is meant to serve.

**What we did instead:**

- **Every form works without JavaScript.** HTMX makes the feed filter dynamically, but if JavaScript is disabled, the form submits normally. Alpine.js makes the FAB button toggle, but the links to "Post a Need" and "Post an Offer" are always visible on desktop.
- **Touch targets are 44×44px minimum** (WCAG 2.1 AA). A grandmother with arthritis can tap the buttons on her phone.
- **The QR code join flow** does not require the new member to type a URL. They point their phone camera at a printed card. The technology adapts to the person's capability, not the reverse.
- **`<noscript>` fallbacks** exist throughout. The community settings page shows the join code in a `<code>` tag that can be manually selected even if the clipboard API fails.

---

## Step 7: We Made Self-Hosting the Default, Not the Exception

**The drift to avoid:** Most platforms centralise control. Your community's data lives on someone else's server. Your community's rules are someone else's Terms of Service. You cannot leave without losing everything. This is the digital equivalent of forcing workers to "adapt to the speed and demands of machines."

**What we did instead:**

- **Any parish, any group, any neighbourhood can run their own instance.** Minimum: 2 CPU, 4 GB RAM, $5/month.
- **`scripts/harden.sh`** — a single idempotent script that configures UFW, fail2ban, SSH hardening, unattended-upgrades. You don't need a DevOps team. You need someone who can type `sudo bash scripts/harden.sh`.
- **`scripts/backup.sh` + `scripts/restore.sh`** — your data is yours. You can back it up, restore it, move it. No vendor lock-in.
- **AGPL-3.0 license** — if someone runs a modified version, they must share their changes. The commons stays common.
- **CSS custom properties for theming** — a Catholic parish can set `--umi-primary: #1A3E5C` (deep blue) and `--umi-accent: #D4A745` (gold). A Buddhist timebank can set their own colours. The tool adapts to the community's identity, not the other way around.

---

## Conclusion: The System Serves the Person

Every decision described above — the boring stack, the human-driven matching, the refusal of surveillance, the progressive enhancement, the self-hosting — follows from one principle:

**The system must be centred on the human person and not solely on performance.**

Performance would say: "Use an AI matching algorithm." We said: "Let the people decide."
Performance would say: "Track engagement metrics." We said: "Count fulfilled needs, not clicks."
Performance would say: "Centralise for efficiency." We said: "Distribute for dignity."
Performance would say: "Require the latest browser." We said: "Support the oldest grandmother."

UMI Exchange is not a fast system. It is not a clever system. It is a *faithful* system — faithful to the principle that technology exists to serve the person, and that the person is never a means to the technology's end.

---

*Built on UMI Protocol v0.1. Code: AGPL-3.0. Protocol: CC-BY-4.0.*
