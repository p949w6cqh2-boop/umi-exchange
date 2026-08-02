# Tutorial video — Stage 1: script

> STATUS: DRAFT awaiting Jasiah's Stage-1 key. Register: `umi-brain/identity/voice.md`
> (say-it-aloud test governs; contractions are normal speech; no em-dashes; neighbours, never
> users). Every claim is checked against the repo — the "true because" column names the source.
> Narration spells "neighbor" the way Jasiah speaks; on-screen product text keeps its own voice.

## Master script (~90 seconds, ~230 words at a relaxed pace)

| # | Screen (walkthrough) | ~Secs | Say this | True because |
|---|---|---|---|---|
| 0 | Landing, top | 0–6 | Let me show you something real quick. This is a board our parish runs on the internet. It works like the corkboard in the back of the church, except it can let you know when someone answers. | Notifications exist: "You'll get a notification the moment a neighbour offers" (`needs/detail.html`) |
| 1 | Landing, hero + notices | 6–14 | Need a hand? Lend one. That's the whole idea. Neighbors ask, neighbors answer, and a real person you know makes the introduction. | Hero copy verbatim; "A coordinator you know pairs asks with offers" (landing) |
| 2 | Join screen | 14–22 | You get in with a code from your parish. No app store, no credit card. If you have the code, you're already welcome. | Join-code flow; web app, no billing anywhere in the codebase; last line is the parish's own sign-in blurb |
| 3 | Hub | 22–32 | When you sign in, the parish greets you by name, with a line the coordinators wrote. One ask that could use a hand today, and the pulse of the week underneath. A crib found a home. A neighbor stepped up. Nobody's name gets paraded. | Hub greeting + welcome line + spotlight + pulse (seeded); helpers unnamed in public is a design rule (voice.md §8.2 spirit) |
| 4 | Post an ask (form) | 32–45 | Asking takes about a minute. Pick a category, say it in a line or two. A ride to Mass, math help for your kid, a hand with the groceries. And the promise is printed right on your ask: nothing about you is shared until you accept a match. | Form is one page; the promise is the enforced UI string on the posted ask (`needs/detail.html:60`) — beat amended at Stage 4 to match the recorded footage |
| 5 | The board | 45–54 | Everything lives on one board, asks and offers side by side. A ride to the 9:30 Mass. Two extra dinners most weeks. A retired teacher, patience included. | All three are seeded board items, word for word |
| 6 | Ask detail → propose | 54–63 | When somebody can help, a coordinator proposes the match. A person who knows you both, not an algorithm. Both sides get a plain yes or no, and nothing is revealed yet. | Walkthrough §7: "The coordinator proposed; both sides get a plain yes/no. Nothing is revealed yet." |
| 7 | Match → the connect | 63–78 | And when both say yes, there it is. Contact, shared between the two of you and your coordinator, a person who keeps it safe. The page says it better than I can: reach out kindly and arrange the rest together. From here it's two neighbors and a phone call. | `matches/detail.html:27` "shared between the two of you and your coordinator" (#136 corrected the page; the recorded footage still shows the pre-#136 string — re-shoot pending); `_contact_info_box.html` "Reach out kindly and arrange the rest together." |
| 8 | Landing again (or connect held) | 78–90 | Now, everything you just watched is our demo parish. St. Brigid's isn't real, and every name here is invented. But the software is real, it's open, and any parish can run its own. If that sounds like yours, come read at reciprocal aid dot network. Ready to begin? Ask your coordinator for a code. | Fictional-disclosure goal (Stage 0 #keyed); open source is true; CTA is the voice.md invitational-question form |

Breath check: longest sentence is 16 words. Read the whole thing aloud once before recording;
anything that trips the tongue gets rewritten at Stage 6, not endured.

## Short-form hook variants (funnel job only; each cuts to the connect beat)

**V1 — curiosity (safest):**
"This is how our parish asks for help now. Watch what happens when both people say yes."
→ post-an-ask beat (condensed) → connect reveal → "reciprocal aid dot network."

**V2 — against the grain:**
"No algorithm decides who gets helped here. A person does. Let me show you."
→ board beat → propose beat → connect reveal.

**V3 — the dad line (optional, only if Jasiah wants the personal note):**
"My dad asked if this was complicated. Here's the whole thing in thirty seconds."
→ join → post an ask → connect. *This one makes a personal claim only Jasiah can own; it's his
call entirely, and it dies without a second thought if it doesn't feel right.*

## Claims deliberately NOT made anywhere

Free (hosting costs exist; "open" is the honest word) · any adoption numbers · "safe" as a bare
adjective (we show the promises instead) · anything about future features.
