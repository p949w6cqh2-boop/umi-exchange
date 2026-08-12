# Spec: human verification at sign-up

> STATUS: SPEC, written 2026-08-11 on the founder's key, from the pastor's ask at the
> pilot-blessing meeting ("sign-in verification to make sure one is human"). Decision
> recommended below; BUILD happens on a separate key after the founder reads this.
> Companion concern from the same meeting, deliberately NOT this spec: a phone path for
> non-tech members (already served by coordinator on-behalf-of posting; ministry practice,
> not code).

## The question

Father's concern is bots and fake people: when someone appears on the parish board, is
there a human being behind the account? The pilot also carries his other concern — elderly
and non-technical members must not be walled out. Any verification we add has to serve the
first without betraying the second.

## What already stands between a bot and the board (verified in code)

1. **Registration alone grants nothing.** A fresh account sees no parish. Reaching any
   community's board requires a JOIN CODE (`communities` app; codes are CSPRNG,
   coordinator-issued). Father's own design makes this the human gate: **the code is
   handed out physically, at church.** A robot does not sit in a pew.
2. **Rate limits**: register 3/min/IP, login 5/min/IP (decorators + auth-path middleware).
3. **Password validation + Argon2**, OTP available for enrolled users.
4. **Coordinator moderation**: hidden posts are contained; accounts can be frozen; every
   sensitive act is on the append-only audit log.

So the realistic threat is not "bots flood the parish board" (the code wall already stops
that); it is (a) junk accounts accumulating in the user table, and (b) a stolen or leaked
join code being used remotely by someone who was never handed it in person.

## Options weighed

| Option | Stops | Costs | Verdict |
|---|---|---|---|
| **A. Lean on the join code + add email verification** | junk accounts can't reach a board; unverified emails can't recover access; leaked-code use leaves a real email trail | one extra click for everyone (elderly included — but it's "open your email and tap," a skill the parish email generation does have) | **RECOMMENDED** |
| B. CAPTCHA (hosted: Turnstile/hCaptcha/reCAPTCHA) | scripted registration | walls out exactly the members Father worries about (puzzle UIs, small screens); adds a third-party script into a privacy-first page; ideologically foreign to "no algorithm decides" | Rejected for the pilot |
| C. Honeypot field + submit-timing check | naive scripted registration | invisible to humans; trivial for a targeted bot | Include — it is free and harmless |
| D. Coordinator approval of every new member | everything | turns coordinators into gatekeepers of a queue; slows the first-yes moment the ministry lives on; the join code already IS coordinator approval in physical form | Rejected (revisit only if abuse appears) |

## Recommended design (A + C)

1. **Email verification on registration.** New accounts get `email_verified_at = NULL`; a
   signed one-time link (Django signing, 48h expiry) lands by email; clicking sets the
   timestamp. Until verified: the account can sign in and look around, but **cannot join a
   community, post, or propose** (one clear banner says why — plain words, no jargon).
   Rationale for soft-gating rather than hard-blocking sign-in: a member standing in the
   parish hall with a coordinator can still get help finishing setup.
2. **Honeypot + timing on the registration form.** A visually-hidden field that humans
   leave empty plus a minimum-seconds check; failures get the same "thanks" page (no
   oracle for the bot author).
3. **Say it at the board meeting in Father's words:** "you can only get in with a code we
   hand you at church, and every account has to answer a real email before it can touch
   the board." That sentence IS the verification story.
4. **Explicitly deferred:** SMS verification (costs money, excludes the phoneless, adds a
   data processor); CAPTCHA (see above); ID checks (grotesquely against the mission).

## Build notes (for the keyed implementation PR)

- Depends on working outbound email → `docs/email-delivery-runbook.md` lands FIRST.
- Migration: `email_verified_at` on the user model (nullable datetime); backfill existing
  demo accounts as verified (fictional data, and the pilot parish starts clean).
- Gate the three actions in views (join, post need/offer, propose match) via one helper +
  one mixin; tests per action.
- The verification email is the second real email the system sends; it inherits the
  deliverability work (SPF/DKIM) from the email runbook.
- Registration UX copy checks against `identity/voice.md` (product register).
- Tests: TDD per the house rule; the registration-throttle gotcha (distinct REMOTE_ADDR
  per POST) applies.

## Done-when

- [ ] Founder read this spec and keyed the build (or amended the recommendation).
- [ ] Email verification live behind working delivery; join/post/propose soft-gated.
- [ ] Honeypot + timing on register, tests prove both trip paths.
- [ ] Board-meeting sentence added to the Sept 15 pack.
