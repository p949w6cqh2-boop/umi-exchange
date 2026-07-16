# Layer C final — the Wellspring pass (Stage 8)

> Same Commons geometry the mid-fi proved; color, type, and imagery arrive here.
> Evergreen primary, bronze strictly for offer-coding, stone paper, espresso ink,
> Newsreader display + Schibsted Grotesk body (the app's own woff2). Screen 01
> (/protocol/) shipped real in Slice 1 and was not flagged for revisit.

## Stage-7 carry-forwards, resolved here

1. **Scripture varied.** The hub welcome line is now "Bear one another's burdens."
   (Galatians 6:2, 28/140); the story page keeps "Whatever you did for the least of
   these, you did for me." (Matthew 25:40) inside the demo-canon prose. Screens 02 and
   08 agree on the new line.
2. **Hub greeting sub-line: STATIC — recommended, presented for the key.**
   - §D keys `welcome_line` as one ≤140 field on `Community.settings`; rotation would
     mean a list plus a scheduler — schema beyond the key.
   - The line is the parish speaking to its own; seasons change it by hand (an Advent
     line, a Lent line) — deliberate, not randomized. Rotation invites
     scripture-out-of-context accidents nobody signed.
   - The field is editable any day from Settings → Identity, so "rotating" is
     available to a coordinator the human way. If automated rotation is ever wanted,
     it's an IDEA for post-v1 (coordinator-curated list, weekly pick), not S4.
3. **"We still don't."** — kept verbatim; keyed as demo canon.

## Corrections made by looking

- The mid-fi spotlight said "basket default"; §J keys **`_well` as the hub default** —
  fixed here (real `static/img/scenes/well.webp` shown, caption says so).
- Draft banner is the keyed **amber strip**; hidden banner uses the app's error family.

## Shots — `shots/`, 390px-first + 1280 desktop, keyed variant states at 390

Same matrix as mid-fi: screens 02–10 both widths; variants at 390 — 03 `empty`,
04 `coordinator`/`published`, 05 `draft`/`hidden`, 07 `anon`/`coord`/`empty`,
09 `coord`. 27 captures.

## Rebuild

```bash
python3 -m http.server 8125 -d .   # repo root — real fonts + prints resolve
npm i --no-save playwright && npx playwright install chromium
node docs/wireframes/identity/final/shoot-final.mjs
```
