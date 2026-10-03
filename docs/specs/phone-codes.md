# Spec: codes by text message instead of on paper (and a phone, never an address, for Communion at home)

> STATUS: **BUILT, OFF by default.** Written 2026-10-02 on the founder's key "8".
> **Decided 2026-10-02 (night):** all four of the founder's decisions on the recommended option
> (§Decisions). Built in #205 with Twilio. ⚖️ **Provider changed 2026-10-03** (§Provider, as built):
> Firebase now, Twilio after the 501(c)(3).
> 💸 **Texting costs money.** Opening the provider account, adding a card, and any spend are the
> founder's hand; no agent opens an account or spends. His word on 10-02: *"if it cost money we will
> do it."* ⛔ **Real neighbors' phone numbers wait for the ethics gate** (`../ethics-and-safety.md`,
> 3 of 6), like every other piece of real personal data.

## Why now

The first coordinator sat down with the board on 2026-10-02. As the founder reported it: *"we will
use phones, she said we should stay away from paper. Switch paper codes to phone codes."* The same
afternoon, email "didn't work" for her own sign-up (a confirmation link that did not arrive or went
to spam; cause unknown). The people she helps are older parishioners who do not use technology much.
More of them carry a phone than read email, and a code on paper gets lost in a drawer.

## What the record already decided (not reopened)

- **The phone stays optional.** The founder said it in public twice (post 12, digest #5): *"I refused
  to force people to add a phone number."* Phone codes are for people who choose to add a phone.
  Nobody is made to give one, and nothing on the board stops working without one.
- **Only a channel the person has proven gets a way back in.** Password resets go only to an email
  address its owner confirmed (#172). The same rule holds for phones: a code is sent only to a
  number the person proved by typing back a code sent to it.
- **Account phone numbers are stored plainly**, like account email (`../ethics-and-safety.md`,
  the line beginning "The code enforces the promise"). This spec does not change that.
- **The coordinator's 15-minute code stays** (#186). It is the way back in for someone with no
  phone, no email, and no paper.

## The design

### 1. Proving a phone

- Settings → Phone → type the number → **"Text me a code"** (or **"Call me with a code"** for a
  landline, see decision 5) → type the 6 digits back → the number is proven
  (`phone_confirmed_at` set).
- Until then the page says "Not confirmed yet", the way an unconfirmed email does today.
- Changing the number clears the proof. Clearing the field removes the number.

### 2. Getting back in with a phone code

- "Forgot password?" → username → if that account has a proven phone, the board texts a 6-digit code
  that lasts 10 minutes and works once → type it → choose a new password. **A code never signs anyone
  in by itself**, the rule the paper code follows today.
- The page answers in the same words whether or not the username exists or has a phone, so it cannot
  be used to learn who is on the board (the posture of the reset and username pages now).
- **Paper becomes the fallback, not the default.** A person who adds a phone at sign-up proves it
  there and then, and is not handed a paper code. A person with no phone still gets one, and anyone
  can still print one from settings (decision 2).

### 3. Communion at home: a phone, never an address

Most of this already works. A request has a contact preference, and a coordinator viewing a request
sees the requester's phone when the preference allows it, **with every look written to the audit
record** (`need.contact_disclosed`, `apps/needs/views.py`). So a homebound parishioner with a phone
on their account posts in "Communion at home" with "phone" as the contact preference; the
coordinator sees the number, calls, and arranges the visit. **The board has no address field and
this spec adds none.** What this spec adds is that the number can be proven (section 1).

For someone with no account at all, the request goes through `on-behalf-requests.md` (gated).

### Provider and cost (read from the provider's public pages 2026-10-02; confirm at sign-up)

| Option | Price | What it asks of us |
|---|---|---|
| **Twilio Verify** (recommended) | **$0.05 per successful verification + $0.0083 per text (US)**; voice calls $0.05 per successful verification plus the voice channel fee | Twilio sends and checks the code. We store no code at all. No sender registration of our own. |
| Twilio Messaging, our own number | $0.0083 per 160-character text + carrier fees (AT&T $0.0035, T-Mobile $0.0045 per text) + a monthly number | We generate, store (hashed) and check codes ourselves, and register as a sender (10DLC or toll-free verification) before carriers deliver. |

At parish scale the cost is small: 30 successful codes in a month is about $1.75 on Verify.
**Abuse is the real cost.** "SMS pumping" is when someone triggers thousands of codes to numbers
they profit from. The guard rails, all required before launch:

- Send only to +1 numbers (US and Canada). The IP country gate in `geolocking.md` can add a second
  check where it is switched on.
- Rate limits per number, per account, and per IP (`django_ratelimit` is already used for sign-in).
- At most 5 codes per account per day.
- A spending alert in the provider console (decision 3).

### What a text says

> Your Reciprocal Aid code is 482913. It works for 10 minutes. Nobody from the board will ever ask
> you for it.

No name, no request, no community name: a text can be read over someone's shoulder.

### Audit

`account.phone_code_sent`, `account.phone_confirmed`, `account.recovery.phone_code_used`. Never the
number, never the code, in any audit `details`.

## Decisions the founder owns (recommendations in bold)

1. **Provider: Twilio Verify**, or Messaging with our own number (cheaper per text, much more setup).
2. **Paper: keep it as a fallback for people with no phone**, or remove it entirely.
3. **Spending alert at $10 a month**, or another amount.
4. **Who sees a Communion-at-home number: coordinators only**, or also the matched helper, as with
   every other request today.
5. **Offer "call me with a code" for landlines: yes.** Many homebound parishioners have a landline
   and no mobile phone.

**Decided 2026-10-02 (night), the founder's answers:**

| # | Decision | Answer |
|---|---|---|
| 1 | Provider | **Twilio Verify** |
| 2 | Paper | **Kept as the backup** for people with no phone |
| 3 | Spending alert | **$10 a month**, set by the founder in the provider console when he opens the account |
| 4 | Communion-at-home number | **Coordinators only**; a matched helper does not see it |
| 5 | Landlines | **Yes**, a voice call reads the code out |

## Provider, as built (changed 2026-10-03)

**Decision 1 changed, in the founder's words:** Twilio needs a $20 starting balance (*"DONT HAVE
20"*), so *"lets do firebase for now then after we get a nonprofit we will switch to twilio."* The
research behind the switch is in the brain (`projects/phone-codes-research-2026-10-02.md`).

| | Firebase / Google Identity Platform (`PHONE_CODES_PROVIDER=firebase`, now) | Twilio Verify (`=twilio`, after the 501(c)(3)) |
|---|---|---|
| Cost | The first 10 texts a day are not billed, then $0.01 per US text. Needs the pay-as-you-go **Blaze** plan, so a card on file | About $0.06 a code, a $20 starting balance; Twilio.org gives a one-time $100 credit to nonprofits |
| Channels | **Texts only** | Texts and voice calls |
| reCAPTCHA | **Required on every send.** Invisible, with the badge inline in the form, loaded only on the two pages that send a code; their CSP is widened for it, no other page loads Google | None |
| What Google keeps | It makes a Firebase user for the number when the code checks out; **the board deletes that user right away** (`accounts:delete`) | Twilio keeps its own verification logs |

How it runs: the board's server asks Google for a code, passing the person's reCAPTCHA token
(`accounts:sendVerificationCode`). It keeps Google's session ID in the person's own session, then
sends the typed code back to Google (`accounts:signInWithPhoneNumber`). It counts the code as good
only if Google says it went to the same number.

**Decision 5 (landlines) under Firebase:** no automated path exists that is free and within the
carrier rules. **Decided 2026-10-03, the founder's yes:** a coordinator calls the number saved on
the account (never a number the caller gives) and reads the 15-minute code the board already makes.
That turns the in-person code into a by-phone one, a small loosening, held by the rule that the
coordinator only ever places the call to the number on file. As built, the code page shows that
number to call back, notes when it was never confirmed by a code, and says "in person" when the
account has none; the coordinator's guide and practice kit say the same.

**His hand, to switch it on with Firebase:**
1. Create a Firebase project.
2. Move it to the Blaze plan, with a budget alert.
3. In Authentication, enable the Phone sign-in provider.
4. Add the board's domain to the authorized domains.
5. Copy the Web API key into the server `.env` as `FIREBASE_API_KEY`, and restrict that key to the
   Identity Toolkit API.
6. Set `PHONE_CODES_ENABLED=True` on his key. Real neighbors' numbers still wait for the ethics gate.

## Honest limits

- A text code is weaker than an authenticator app: a stolen or swapped SIM receives it. Fine for
  this audience; coordinator and admin accounts keep the authenticator-app option (`ENABLE_2FA`).
- A shared family phone means whoever holds the phone gets the code.
- Once built and switched on, **the board sends texts by itself**. Switching it on is the founder's
  key, separate from merging the code.
- Nothing here helps someone with no phone and no email. The coordinator's code still does.

## Tests to write with the build

- A code goes only to a proven number; an unproven one gets nothing, with the same page as success.
- The forgot-password page answers identically for unknown usernames, accounts with no phone, and
  accounts with a proven phone.
- A code works once, dies after 10 minutes, and five wrong tries lock it.
- No number and no code appear in any audit record or log line.
- The provider is called through one module that tests replace, so the suite never sends a text.

## Done-when

- [x] Founder decisions 1–5 answered (2026-10-02; the alert amount is set when the account opens).
- [ ] Provider account opened and a spending alert set (founder's hand).
- [x] Built behind a setting that is off by default; tests above green on Postgres (#205 Twilio,
      then Firebase as the provider for now).
- [ ] Turned on in production on the founder's key, and only after the ethics gate allows real
      neighbors' numbers.
