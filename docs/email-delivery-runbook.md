# Email delivery runbook — making reset + recovery emails actually arrive

> STATUS: written 2026-08-11 with the auth-recovery change. THE FINDING: production
> defaults to the console email backend (`config/settings/base.py`), so on the droplet a
> password-reset email "sends" into the gunicorn log and no human ever receives it. The
> reset flow looked done and was functionally dead. Same would hold for the new username
> recovery. This runbook is the path to real delivery, and the receipts that prove it.
>
> Provider choice and credentials are the founder's hand (external account + possible
> spend, keyring class). An agent prepared the plumbing and this document.

## What the code already does

- All SMTP settings read from env (`EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`,
  `EMAIL_USE_TLS`/`SSL`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`) —
  `config/settings/base.py` §Email.
- `production.py` auto-upgrades console→SMTP **only when `EMAIL_HOST_USER` is set** — so the
  fix is entirely .env configuration, zero code.
- `python manage.py send_smoke <address>` (new) sends one real message and prints the
  active backend first — "it ran" can never be mistaken for "it delivered."

## The founder's hand-list

1. **Pick the provider.** Constraints that matter here: the FROM domain should be one we
   control (`DEFAULT_FROM_EMAIL` currently defaults to `noreply@umifoundation.org` — use an
   address on a domain you can set SPF/DKIM for, e.g. `noreply@reciprocalaid.network`), free
   or near-free at parish volume (tens of emails/week), and no parishioner data beyond the
   recipient address ever goes to the provider (these emails carry a username or a reset
   link, nothing else — acceptable egress, worth stating).
2. **Create the account + SMTP credential** (founder hand). Set SPF + DKIM DNS records for
   the sending domain per the provider's instructions — without them, parish members' mail
   hosts will junk-folder the resets.
3. **Droplet `.env` additions:**
   ```
   EMAIL_HOST=<provider smtp host>
   EMAIL_PORT=2587
   EMAIL_USE_TLS=True
   EMAIL_HOST_USER=<smtp username>
   EMAIL_HOST_PASSWORD=<smtp password>
   DEFAULT_FROM_EMAIL=noreply@<sending domain>
   ```

   🔴 **The port is 2587, not 587, and this cost a debugging cycle on 2026-09-11.**
   **DigitalOcean blocks outbound 25, 465 and 587 by default** as an anti-spam measure.
   The symptom is a `TimeoutError: timed out` inside `smtplib.connect` — a *connect*
   failure, not an auth failure, so it reads like a broken network rather than a policy.
   `ufw` is not the cause (`harden.sh` sets `allow outgoing`). Measured on the droplet:

   ```
   25 BLOCKED · 465 BLOCKED · 587 BLOCKED · 2465 OPEN · 2587 OPEN
   ```

   **Resend publishes 2465 and 2587 for hosts that block the standard ports.** Use **2587**
   with `EMAIL_USE_TLS=True` (STARTTLS). 2465 is implicit TLS and would need
   `EMAIL_USE_SSL=True` with `EMAIL_USE_TLS=False` — Django rejects both being true.
   The alternative is opening a DigitalOcean support ticket to lift the block; the
   alternate port needs no ticket.

   ⚠️ **`EMAIL_HOST_USER` for Resend is the literal word `resend`**, not an address. A typo
   there still leaves the value truthy, so `production.py` still flips the backend to SMTP
   and the config *looks* applied — it fails only when mail is actually sent.
   Then restart the app (deploy runbook invocation). Note: once the key-custody design
   lands, these join the encrypted secrets file, not plaintext .env.
4. **Smoke:** `python manage.py send_smoke <your own address>` on the droplet. The receipt
   is the message in your inbox — screenshot it.
5. **E2E, the real thing:** on the live site, "Forgot password?" for a demo account whose
   email you control → receive the email → complete the reset. Then "Forgot username?" the
   same way. Screenshot both received emails; those are the PR-closing receipts.
6. **Deliverability check:** send_smoke to one Gmail and one non-Gmail address; confirm
   neither lands in spam. If they do: SPF/DKIM records are wrong — fix before the pilot.

## Ongoing posture

- Console backend stays the dev default on purpose (no accidental real email from dev).
- The auth emails are the ONLY outbound email today. Any future notification email goes
  through the same `DEFAULT_FROM_EMAIL` and inherits this deliverability work.
- If the provider credential ever leaks, it can send spam as the parish's domain: treat
  `EMAIL_HOST_PASSWORD` with key-custody seriousness and rotate on any suspicion.
