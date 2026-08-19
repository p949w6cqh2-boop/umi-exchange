# Outbound email provider: decision record

> STATUS: **NOT DECIDED. This is the record written before the choice, not after it.**
> Jasiah has no provider account as of 2026-08-19. A recommendation is stated below; the decision
> line stays empty until he rules, and then it gets filled in here rather than reconstructed later.
>
> Context: UMI Exchange in production on a ~960 MB DigitalOcean droplet, prototype stage,
> budget-sensitive, serving fictional demo data today and vulnerable community members' PII once
> the `docs/ethics-and-safety.md` gate passes. Sibling record: `docs/monitoring-decision.md`.
> Hands-on path once a provider exists: `docs/email-delivery-runbook.md`.

> ⚠️ **HOW MUCH TO TRUST THIS DOCUMENT.** `monitoring-decision.md` came out of a 24-source
> adversarially-verified research pass. **This one did not.** The constraints, the egress analysis
> and the reasoning below are derived from this repository's own code and are checkable. **The
> provider tiers and prices are NOT verified and change often — confirm every one on the provider's
> current pricing page before signing up.** Treat the comparison table as a starting shortlist, not
> as findings.

## The decision to be made

**Which SMTP provider sends this application's outbound mail**, and from which domain.

## TL;DR

**Pick a hosted transactional SMTP provider on a free tier, sending from `reciprocalaid.network`,
and configure SPF and DKIM at setup rather than later.** Do not self-host outbound mail. The egress
here is genuinely small — a recipient address and a link — which is what makes a hosted provider
acceptable in a project that otherwise refuses to ship data off-box.

## What the code already constrains (verified in this repo)

These are not preferences. They are what the application will actually do.

- **It speaks SMTP, not a vendor API.** `config/settings/base.py` §Email reads `EMAIL_HOST`,
  `EMAIL_PORT`, `EMAIL_USE_TLS`/`SSL`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`,
  `DEFAULT_FROM_EMAIL`. **A provider that is API-only is disqualified** without a code change.
- **The switch is a single env var.** `config/settings/production.py` upgrades console → SMTP
  **only when `EMAIL_HOST_USER` is set**. Zero code changes are needed to go live.
- **The safe-fail default is console.** Nothing leaves the box until credentials exist. As of
  2026-08-19, `printenv EMAIL_HOST_USER` on the droplet returns **empty** — so today, production
  mail is still written to a log and delivered nowhere.
- **`DEFAULT_FROM_EMAIL` currently defaults to `noreply@umifoundation.org`**, a domain the project
  does not control. It must become an address on a domain it does.

## The decisive fact: what actually leaves the box

This is the crux, and it is the opposite of the Sentry case in `monitoring-decision.md`.

**The only outbound emails this application sends today are auth emails:** password reset, username
recovery, and email verification. What the provider sees is:

| leaves the box | does not leave the box |
|---|---|
| the recipient's email address | any need, offer, or match |
| a one-time link or a username | any casework narrative or `Person` record |
| the `DEFAULT_FROM_EMAIL` sender | any name, address, or phone |

**Compare with the monitoring decision, where the answer was "send nothing."** There, Sentry's SDK
captured stack-trace locals and breadcrumbs that could carry parishioner PII, and the leak was not
gated by the obvious setting. **Here there is no payload to leak.** An email address plus a reset
link is the irreducible minimum for the feature to exist at all: you cannot email someone without
telling the mail system who they are.

**So the two decisions differ for a principled reason, not an inconsistent one.** Refusing hosted
error aggregation and accepting hosted mail delivery are the same rule applied to different egress.

## Why NOT self-host outbound mail

Subsidiarity argues for the smallest, most local option, and taken naively that means running a
mail server on the droplet. **That would be the wrong call, and the reason is not convenience.**

- **Deliverability is a reputation system, not a protocol.** A fresh IP on a consumer-facing cloud
  range starts with no sending reputation, and DigitalOcean ranges are widely filtered. The mail
  would be accepted by the server and dropped or junked by the recipient's provider.
- **A reset email that lands in spam is worse than one that fails loudly.** The member believes
  they asked, sees nothing, and concludes the board is broken. **That is the same failure shape as
  the monitor whose alerts were switched off**: the system reports success while the human gets
  nothing. This project has now been bitten by that shape twice.
- **It is ongoing operational work** — TLS, reverse DNS, blocklist monitoring, bounce handling — on
  a one-maintainer prototype where that maintainer's time is the scarcest input.

**Subsidiarity is about the smallest thing that ACTUALLY WORKS.** A mail server that technically
runs but does not reach people is not the smaller solution; it is the failed one.

## Shortlist — ⚠️ TIERS UNVERIFIED, CHECK BEFORE SIGNING UP

Requirements applied: offers SMTP credentials, free at tens of emails per week, supports custom
domain with SPF and DKIM, no card required to start where possible.

| provider | why it is on the list | what to check |
|---|---|---|
| **Resend** | SMTP available alongside the API; DNS setup for SPF/DKIM is guided in one screen; free tier is generous relative to this volume | that SMTP (not API-only) is on the free tier; current monthly and daily caps |
| **Brevo** | SMTP included; free tier historically usable without a card | current daily cap; whether transactional SMTP is still free |
| **Amazon SES** | cheapest by far at any real volume; strong deliverability | requires an AWS account and a **sandbox exit request** before it can mail arbitrary addresses; more setup than the others |
| **Postmark** | best-in-class transactional deliverability | **likely costs money at this volume — a spend decision, his hand only** |

**Not evaluated and probably not right:** general mailbox products (Google Workspace, Zoho Mail).
They are for humans reading mail, not for application-generated transactional sending, and their
SMTP relays carry per-day limits and terms aimed at a different use.

## Recommendation for THIS context

1. **Start with Resend**, falling back to Brevo if its free tier no longer includes SMTP.
2. **Send from `reciprocalaid.network`**, never from a domain the project does not control.
3. **Set SPF and DKIM during setup, before the pilot.** Without them the resets get junked, and the
   project ends up with mail that "works" and still fails the people it exists for.
4. **Revisit SES only if volume ever makes cost a real question.** At tens of emails a week it
   never will, and the sandbox-exit step is not worth paying today.
5. **Record the choice in this file** when it is made, with the date and the reasoning, the same
   way `monitoring-decision.md` recorded Option C.

## Catholic Social Teaching lens (analytical, not source-backed)

- **Subsidiarity** — prefer the smallest option that actually works. Self-hosted mail is smaller on
  paper and does not work in practice, so the hosted relay is the honest reading of the principle.
- **Data dignity of the vulnerable** — the egress is one address and one link, and it is
  irreducible: the feature cannot exist without it. **What must be protected is that nothing else
  ever joins it.** Any future notification email must carry the same minimum and be reviewed here.
- **Stewardship** — a free tier at parish volume, no card where possible, and no vendor whose
  pricing punishes the project for growing into a second parish.

## What this decision does NOT cover

- **Inbound mail.** The board does not receive email and has no reason to.
- **Notification emails beyond auth.** If digest or match-notification email is ever built, the
  egress table above must be re-examined **before** it ships, not after.
- **Key custody for the credential.** `EMAIL_HOST_PASSWORD` can send mail as the project's domain
  if it leaks. `docs/email-delivery-runbook.md` already says to treat it with key-custody
  seriousness; once `docs/key-custody-design.md` lands operationally it belongs in the encrypted
  secrets file, not plaintext `.env`.

## The decision

> **Provider:** _(unfilled)_
> **Sending domain:** _(unfilled)_
> **Decided by Jasiah on:** _(unfilled)_
> **Reasoning, if it differs from the recommendation above:** _(unfilled)_

Until those lines are filled, the console backend stays the default and **no application email
reaches any human.** That is the safe-fail state, and the ethics gate is not blocked by it —
nothing here is a gate box. It is blocked only when a real person needs to reset a real password.
