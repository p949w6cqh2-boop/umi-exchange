# Tutorial video — Stage 0: goals & audience

> STATUS: DRAFT awaiting Jasiah's Stage-0 key. Pipeline: founder-gated at every stage; nothing
> records, publishes, or uploads without his hand. Source of truth for the walkthrough:
> `docs/demo-walkthrough.md`. Voice source: `umi-brain/identity/voice.md` (CONFIRMED).

## The idea, in one line

Your voice and a few clicks over the real screen — "let's look at it real quick" — showing that
asking for help and offering it takes about a minute, and that the software treats both people
with dignity.

## Who it serves, and the one job per audience

| Audience | Moment they're in | The one job the video has | What "worked" looks like |
|---|---|---|---|
| **Parish leaders** (pastor, parish council, SVdP conference lead) | Deciding whether this is safe and simple enough to try | Answer "what is it, is it safe, what does it ask of us" in 90 seconds — calm, complete arc | They visit reciprocalaid.network and read; a conversation starts |
| **Ordinary members** | Handed a join code, unsure they can "do computers" | Make them feel "I could do this" — the ask form is a line or two, the promise is printed on it | They post their first ask (or say yes to a match) without asking for help |
| **The wider funnel** (short-form scrollers, Catholic + mutual-aid adjacent) | 3 seconds of thumb-hover | One complete emotional arc — ask → yes → contact revealed — inside 30s, then the door | Follows, shares, link-throughs; the master video gets its chance |

**One cut, one job.** The 90s master serves leaders and members. Shorts serve the funnel. No cut
tries to serve all three; that's how videos become about nothing.

## The register (opening + throughout)

- **"Let's look at it real quick."** Not a pitch, not an explainer — a neighbor showing you a
  thing on their screen. Present tense, kitchen-table, second person: "here's the board,"
  "watch what happens when both say yes."
- Voice rules inherit `identity/voice.md`: short sentences; neighbours, never users; honest to a
  fault; the connect is a welcome, not a jackpot. No exclamation-point cheerfulness, no SaaS
  words, no guilt appeals.
- On-screen text stays the product's own voice (including "neighbour" spelling) — the narration
  is a human talking over it, not the app rebranded.

## Hard constraints (non-negotiable)

1. **No face. Voice only.** Screen + cursor + voice — nothing else.
2. **Ethics line:** fictional St. Brigid's data only on screen. Never real PII, never a real or
   livestreamed ask, no real parish names spoken. Every name in frame is invented.
3. **Fictional disclosure, done honestly:** spoken once in the master ("this is our demo parish
   — every name here is fictional") + one line in every post's description text. Honesty IS the
   brand; hiding the demo-ness would cost more trust than it buys polish.
4. **Truthful claims only:** privacy promises appear in narration only where the code enforces
   them and the UI already says them (the post-form promise, the contact-reveal gate). No
   invented stats, no "thousands of parishes."
5. **Nothing posted, uploaded, or account-created by the pipeline.** Raw footage + drafts land
   in the repo branch (docs) and a gitignored output dir (video). Jasiah's hand presses every
   button, everywhere.

## Platform targets

TikTok · Instagram Reels · YouTube (master) + Shorts · Facebook · Threads · Pinterest.
Aspect + length mapping is Stage 5's job; Stage 3 records both 16:9 (desktop master) and 9:16
(phone-native pass — the app is phone-first; the whole demo gallery is 390px wide) so every
platform gets native footage, not crops.

## Goals added beyond the brief (proposed, for the key)

1. **Protect the money shot.** The walkthrough calls the connect "the reason all of this
   exists." Every cut, on every platform, either ends on or contains the contact-reveal beat.
   No cut ships without it.
2. **Subtitles always, burned or sidecar.** Sound-off scrolling is the short-form default and
   the parish demographic skews older — captions are not an accessibility extra here, they're
   the primary channel for half the viewers. Stage 5 generates the caption file from the
   Stage 1 script so words match voice exactly.
3. **Evergreen rule.** No dates, no version talk, no "new feature" phrasing on screen or in
   voice. The footage should be as true in a year as today. The durable asset is the
   re-runnable rig (Stage 3) — when the UI evolves, re-run it; footage is disposable by design.
4. **Trust-signal beats for the leader audience.** The two places the UI narrates its own
   restraint — "nothing about you is shared until you accept a match" on the post form, and the
   locked contact panel before both say yes — get deliberate screen time and a quiet spoken
   echo. That's the safety question answered by showing, not asserting.
5. **Legibility floor.** Phone-width UI text must be readable in the final vertical cut at arm's
   length. Stage 3 records at 2x device scale and Stage 4's contact sheet includes a
   smallest-text check per scene.
6. **Music is Jasiah's call, deferred to Stage 5.** If any: platform-native licensed audio only,
   chosen at post time by him — nothing downloaded, nothing baked into the raw footage (voice
   syncs to beats, music never fights the voice).
7. **Measure humbly.** Prototype stage: the metric is conversations started (site visits,
   replies, a pastor who asks a question) — not follower counts. No engagement-bait mechanics
   ever; witnessing generosity is the draw, same as in the product.

## What Stage 1 will do with this

Master ~90s script beat-by-beat over the 8 walkthrough screens (landing → join → hub → post an
ask → board → ask detail → match → connect), in Jasiah's register, plus 2–3 short-form hook
variants (funnel-job only). Every line checkable against the repo.
