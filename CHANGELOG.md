# What's new on UMI Exchange

> Plain-language patch notes for the people who use the board — kept current on every merge.
> (Developers: the full story lives in git history; the brain's `context.md` carries the handoff.)

## 2026-07-16

- **The protocol has a home.** The footer's "Built on the UMI Protocol" line now goes to a
  real page on this very server: /protocol/, with the plain file beside it at
  /protocol/spec.md. No outside website needed — it reads fine on an offline laptop.
- **One honest way to report a security problem.** /.well-known/security.txt now says
  exactly how to reach us, and SECURITY.md explains it in plain words. The old copies that
  pointed at addresses that didn't exist are gone.
- **Every link is a promise.** A new test fails the build if anything in the app points at
  a domain we don't actually have.
- **The promise is written down.** The rules this board lives by — who can see what, what
  gets encrypted, what gets shed and when — now exist as one document: the UMI Protocol,
  version 0.1. It was written from what the code already does, read in full, and signed off.
  Soon there'll be a page where anyone can read it.

## 2026-07-14

- **One name everywhere: Reciprocal Aid Network.** The app stopped switching between
  its old names. UMI stays as the infrastructure it's all built on.
- **The hillside has its priest** — where the page says the deed comes first, a priest
  kneels on the terraced hillside at dawn, planting with his own hands, the sun rising
  behind the church at the crest. Made carefully, as a sacred image.
- **Pictures checked for truth** — every scene was scanned for realism. The giving-hands
  print was redrawn, a stray artist's scribble came out of the basket scene, and the
  beliefs page now shows the first lake itself: water close to home.

- **The "What we believe" page opens like the story page now** — same voice, same
  conviction. Lake 0 gets its picture: the spring the other lakes are filled from.

- **Everything reads the way you'd say it** — every screen in the app got the same
  plain-language pass the story pages got: buttons, settings, empty pages, and error
  pages included.
- **Kinder dead ends** — a page you don't have access to now explains itself politely,
  and broken links get a warm page instead of a technical one.
- **The hub greets you by your first name.**
- **"What you've shared" now says it in plain words** — who can see what, in a sentence
  ("They can see your name and your email"), with a Stop sharing button and an honest note
  about what stopping does.

- **New pictures** — the scenes on the story pages and around the board are now real
  two-colour block prints: the well, the lamplit door, bread passing hand to hand, the
  shared harvest basket, the one place set, the garden hill, the notice board.
- **The widow's table shows her now** — the first scene on the beliefs page carries the
  grief it names: a widow alone at her table, head in her hands, the loaf untouched.
- **Pictures sit tighter in their frames** — the extra paper edge around each print is
  gone, so they read as prints on the page, not pictures in white boxes.
- **The widow's scene now matches the other prints** — redrawn on the same bare paper,
  her green shawl the only colour in the room.
- **Plainer section titles** — headings across the story pages are now complete
  sentences, written the way you'd say them out loud.
- **Smoother reading** — the story pages now read in full, flowing sentences.
  The dashes and clipped fragments are gone.
- **Written the way people talk** — the story pages passed a read-it-out-loud test.
  Contractions are back, and long comma-chains became short spoken sentences.

## 2026-07-13

- **For coordinators: the federation launch guide caught up with the build** — sharing beyond
  your community is now described the way it actually works (the "Share beyond this community"
  card on your own ask or offer — one press, and only the outline travels), and the one-time
  pairing code is documented where it now lives: pinned on the page, not a vanishing pop-up.
- **Fixed things you never saw** — two rounds of adversarial bug-hunting hardened security,
  robustness, federation, and theming; the build checks that guard every change were repaired and
  pinned so they can't silently drift.
- **Emails that actually arrive** — when your community's server sets up its mail account, UMI
  now sends real email for the moments that need you (someone offered on your ask, a match wants
  your yes). **Consented:** a switch in your account settings turns email off entirely — you'll
  still see everything in the app. Off means off.
- **Keyboard-friendly buttons** — every button now shows a clear focus ring when you move by
  keyboard, and disabled buttons finally look disabled.
- **Nothing renders blank anymore** — pages show all their content even if scripts fail or are
  turned off; the gentle scroll animations became pure enhancement.
- **The connect moment got its ceremony** — when both of you say yes, the page settles, warms,
  and says "You're connected." Volunteers who raised a hand without posting an offer now get the
  same welcome (that was a real bug — found and fixed).

## 2026-07-12

- **You can now report a post** — a quiet "Something wrong with this post?" on every ask and
  offer. Reports go only to your coordinators; you're never named, and you're told when it's been
  reviewed. Coordinators get a queue to hide (reversibly), keep, or dismiss.
- **First steps that guide you** — new members see three real moves on their hub (post → raise a
  hand → connect) with checkmarks that come from what you've actually done. Dismiss it once and
  it never nags again.
- **Search that finds** — the board now matches your area ("Riverside") and puts the most
  relevant result first instead of merely the newest. Filters that match nothing say so and offer
  one tap to clear.
- **Start your own community in minutes** — creating a community lands you on a setup guide:
  share the join code (one-tap copy + printable QR), pick your colours, add coordinators, post
  the first ask.
- **Resources beyond the board** — coordinators can gather trusted places to turn (legal aid,
  food, health, benefits, housing) into a directory one tap from the hub.
- **A bar you can reach with your thumb** — on phones, Hub · Board · Post · Alerts · You now live
  at the bottom of the screen where your hand actually is.
- **New artwork throughout** — the illustrations were re-carved as woodcut-style still lifes:
  two hands passing bread, the well with jugs waiting, the noticeboard with its ladder still
  leaning. No more clip-art figures.

## 2026-07-11

- **The privacy promise, in writing and in code** — a public page states exactly what UMI keeps
  and for how long, and every line on it is enforced by running code: encrypted names on old
  requests shred themselves after 12 months, closed casework after 7 years, exchanged contact
  details after 72 hours. "Deletion here is not a promise to look away; it is a lock with no key
  left in the world."
- **Sensitive cases now default to restricted** — a case nobody classifies fails safe; only the
  people named on it can read it.
- **Signing up without an email works properly** — the second person to join without an email
  no longer hits a false "already exists" error.
- **Tags and households explained in plain words** — what a tag is for (the green check means a
  coordinator confirmed it), what a household does, and two short guides: how to get a tag, and
  how to start your own UMI community.
- **Revoked badges can't masquerade** — a withdrawn verification now looks withdrawn, never like
  an innocent self-reported tag.
- **The audit log's lock now truly locks** — the deployment recipe separates the database roles
  so the append-only history can't be quietly rewritten, even by the app itself.
