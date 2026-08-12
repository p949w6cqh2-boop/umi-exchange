# What's new on UMI Exchange

> Plain-language patch notes for the people who use the board — kept current on every merge.
> (Developers: the full story lives in git history; the brain's `context.md` carries the handoff.)

## 2026-08-12

- **The person check is now real, and it never asks you to click traffic lights.** New
  accounts confirm they're human one of two ways: click the link we email you, or — if
  email isn't your thing — tell a coordinator at church your username and they vouch for
  you in person (that vouch goes on the permanent record). Until one of those happens, a
  new account can sign in and look around but can't join a community or post. Existing
  accounts aren't affected. Robots filling in the sign-up form now get quietly shown the
  door — real neighbours won't notice anything changed.
- **Who can stop this thing, and who holds the keys — written down.** Two new pages in the
  open documentation: one says who holds real authority over the board (the pastor can halt
  it with a phone call; a complaint about the steward goes to the parish office, never
  through the steward himself; succession and removal are spelled out), and one designs how
  the encryption keys stop living on the same machine as the data they protect (a sealed
  envelope in the parish safe, openable only by two named people, is part of it). The
  designs become real before any real parishioner's information goes on the board.
- **How we make sure you're a person, without walling anyone out.** A written plan for
  sign-up verification: the code you're handed at church stays the front door, and each new
  account will confirm a real email address before it can post. We looked at CAPTCHAs — the
  "click all the traffic lights" puzzles — and rejected them, because they wall out exactly
  the people this board most wants to welcome.

## 2026-08-11

- **Forgot your username? The board can now tell you.** The sign-in page always offered a
  password reset; now there is a "Forgot username?" link beside it. Enter your email and the
  board sends the username registered to it. Nothing is revealed to anyone else: the page
  answers the same way whether or not it knows your address.
- **Reset emails are on the path to actually arriving.** We found that on the live server,
  "we've sent you an email" could be true in the code and false in your inbox — the message
  went to a server log. A delivery check now exists and the setup to send real email is
  written down, so this gets fixed at the root before the first parish onboards.

## 2026-07-30

- **We were telling you your contact details went to one person. They also go to your
  coordinator, and now the board says so.** Five places on this site said that once you and a
  neighbour both say yes, your phone number and email pass between the two of you alone. That was
  not true. A coordinator of your community can also see them, so there is someone accountable if
  an introduction goes wrong. The code has always worked that way and every disclosure has always
  been written into the permanent record. The words were wrong, and the words are what you read
  before deciding to trust us. The connect screen, the privacy page, the terms, the front page and
  the first-steps guide all name the coordinator now.
- **The front page no longer says the software can simply forget you.** It said sensitive records
  are encrypted so thoroughly the software itself can forget them. Our story was corrected on this
  a week ago and the front page was missed. It now says the same true thing: the things that could
  really hurt someone are encrypted each with its own key, and everyday things like a display name
  are still held in plain text.

- **A community's pages now link to each other.** Before, getting from "Our story" to "Mass times"
  meant going back to the list of pages and starting again. Each page now carries a row of its
  sibling pages across the top, in whatever order the coordinators put them in, with the one you're
  reading marked. It only ever shows pages you're allowed to open: a draft, or a page hidden after a
  report, never appears there, not even for the coordinator who can see it themselves.
- **Our story now says plainly what "forget me" does and doesn't cover.** The page used to say the
  software can simply forget someone who asks. That was more than we can promise. It now names what
  is encrypted with its own destroyable key — a case note, the identity behind a request, the name of
  the neighbour someone was asking for — and then says outright that everyday things like a display
  name, an email, or the title of an ask are still held in plain text. A promise only belongs on a
  page if the code keeps it.

## 2026-07-29

- **The board's records are now proven recoverable.** We took a real backup, carried it off this
  machine to a separate storage service, brought it back, and rebuilt a working copy of the board
  from it — the whole drill, start to finish, not just in theory. Old backups now also clean
  themselves up on schedule, both here and at the off-site copy, so nothing lingers longer than the
  thirty days we promise. And if a night ever comes when the off-site copy can't be made, the backup
  job now says so loudly instead of quietly carrying on.

## 2026-07-27

- **A small bookkeeping repair to consent records.** When a coordinator recorded consent that was
  given on a paper form, the record was filed under a label the system doesn't recognise. It is now
  filed as written consent — which is what a signed paper form is — and any record already filed the
  odd way has been corrected to match.
- **If a neighbour hasn't been asked, the board no longer acts as though they have.** When a
  coordinator opens a case for someone who has no account here, that person's name is now kept short
  on the case — initials only, with a line saying plainly that they haven't been asked directly —
  until their yes is actually recorded. And when it is recorded, it is written down as *theirs*, with
  the coordinator noted as the person who heard it, rather than being filed under the coordinator's
  own name as it was before. Whoever wrote it down can withdraw it on their behalf, and it shows up
  in their list of shared things so it can't be quietly forgotten.
- **The board now says plainly what it is, and isn't.** A new "What this is" page, linked in the
  footer, states it directly: this board brokers introductions between neighbours, and it does not
  vet people, run background checks, supervise meetings, or guarantee anyone's safety. The same words
  appear when you're about to accept a match — before contact details are exchanged, not after.
- **Reporting or blocking someone no longer requires matching with them first.** You can do both from
  any ask or offer they've posted. The neighbours you've blocked are listed in your settings, and
  coordinators have a standing link to the reports queue from their dashboard.

## 2026-07-25

- **Groundwork: the last of the linked-community repairs.** Still switched off everywhere, so
  nothing changes for you today. A community asking to link a second board now actually reaches an
  admin who can approve it, instead of waiting on an approval that could never arrive. And three
  hardening fixes underneath: a linked community must prove it holds the key it publishes, a
  malformed request now gets a clean refusal instead of an error, and a flood of confused updates
  can no longer tie up the server.
- **Groundwork: what crosses to a linked community, and what must never.** Linking two communities
  is still switched off everywhere, so nothing here changes what you see today — these are repairs
  made before it can ever be switched on. A post a coordinator has hidden now stops being offered to
  a linked community straight away, and can't be picked up by one; an offer taken off the board
  can't be sent to one. When a match across communities can't go ahead, the other side is no longer
  handed contact details on a retry. And when a link is paused or ended, contact details still
  waiting to be sent are erased rather than sitting there indefinitely.
- **Two-step sign-in now actually guards your account.** If you've set up an authenticator app,
  signing in now asks for your 6-digit code (or a saved recovery code) after your password — as the
  settings page always said it would. Before this, the code was never asked for, so the extra
  protection existed on paper only. Nothing changes if you haven't set up an authenticator.
- **What you write in a note stays where it can be erased.** The board keeps a permanent record of
  *actions* — who accepted a match, when a tag was reviewed — that by design can never be altered.
  Three spots were copying the actual words people typed (a match note, a tag-review reason) into
  that permanent record, where no erasure request could ever reach them. The record now only notes
  *that* something was written; the words themselves stay on the post, where they can still be
  corrected or removed.
- **The waiting-asks list no longer loses the asks that need it most.** On the coordinator
  dashboard, an ask where a helper had stepped up and then stepped back was counted as "already
  matched" forever — so the very asks most at risk of being forgotten never appeared in the
  waiting list. Only genuinely in-progress matches count now. Also closed a small door that let a
  signed-out visitor tell which community addresses exist by how the page failed.
- **The app can no longer report itself healthy when it isn't.** The built-in health probe used to
  answer "fine" even if the database was unreachable — a redirect fooled it before it ever really
  checked. It now checks for real, and honours the optional health token. And a safety catch for
  later: the optional error-reporting service (currently switched off) is now configured so that if
  it's ever switched on, it cannot send request contents or in-memory data off the server — the
  places a decrypted case note would sit at the moment of a crash. The old setting only *looked*
  like it promised that.
- **A block now holds everywhere on the board.** Blocking a neighbour was already keeping the two of
  you from being matched, but their name and posts could still turn up in a few places: the Pulse and
  the spotlight ask on your home screen — the first thing you see after signing in — and the
  suggestion panels on ask and offer pages. Those all respect the block now, both ways. The same
  panels also stop showing posts a coordinator has hidden.
- **Field notes sync again after a bad entry, and a lost edit now says so.** One malformed entry in
  a batch of offline visit notes used to fail the whole batch — and because the phone keeps trying,
  syncing could stay stuck for good. Bad entries are now reported one by one and the rest go
  through. Separately: if you went Back on your phone and re-sent an edited visit note, the edit
  could be dropped while the page still said "Visit saved". Now an identical re-send is quietly
  ignored as before, but an edit that can't be stored tells you plainly and points you to the note
  to amend, so nothing you wrote goes missing without you knowing.
- **Withdrawn consent now stops a handoff too.** When someone withdraws consent, their case freezes:
  no new notes can be written. Handing the case to another visitor was the one path that slipped
  past that freeze, and it carried a written summary with it. It's now frozen like everything else —
  the case can still be closed. Two related repairs: the daily overdue-reminder email now re-checks
  that the person still has access to the case before it goes out (someone who left, was removed, or
  had their access ended kept getting it), and it honours the email opt-out. And a case can no
  longer be deleted outright from the admin screens — closing a case is the only path, so finalized
  notes stay intact and the record of what happened stays whole.
- **Two rare timing faults that could undo work already done.** If a coordinator removed a neighbour
  at the same moment someone marked a match complete, the finished match could be quietly flipped
  back to cancelled and the ask put back on the board. And the hourly tidy-up that closes out
  past-due asks could close one a neighbour had just accepted — leaving them on their way to help
  while the person who asked was told it had lapsed. Both now re-read the current state before
  writing anything, so whoever acted first wins and nothing gets overwritten.
- **Tidier, safer edges around your community.** A community's name is now handled safely inside the
  "Leave this community?" prompt, so a name containing something that looks like code can't act on
  your screen. An admin who leaves can no longer pull up the community's live join code — rotating
  the code now truly closes that door. On a phone, the bottom bar no longer follows you to a
  community you aren't part of and leave you tapping links that go nowhere. And a malformed report
  or block now answers with a plain "not found" instead of an error page.
- **Tougher on password guessing and lockout tricks.** Repeated sign-in attempts on one account are
  now counted properly — a small trick that used to reset the counter no longer works — and the admin
  sign-in door is covered by the same limit. A burst of sign-up attempts using your name can no longer
  lock you out of your own sign-in. And a new password can't be the same as your username.
- **Hidden and blocked posts stay out of matches.** If a coordinator has hidden a notice — or
  removed the neighbour who posted it — it can no longer be picked up as a match, and a match on
  it can't be accepted after the fact. And when two neighbours have blocked each other, a match
  between them can't be completed, even one that was already waiting, so contact details are never
  shared across a block.
- **Steadier locks on personal information.** Quiet, under-the-hood repairs to the system that
  keeps names and case notes encrypted. Changing the master key used to stop halfway if it met a
  finalized case note; it now finishes cleanly. A case's emergency safety note is now covered by
  that key change too. And the one-time upgrade that moves older records onto the stronger lock
  can no longer snag on a single unreadable record and stall. Nothing looks different on the
  board — these keep the protections whole.

## 2026-07-22

- **The founder's name now shows in full.** The About page signature and the protocol's
  steward line read **Jasiah Williams** now, not just the first name. Nothing else on those
  pages moved.
- **Groundwork for finding a person by name.** Nothing changes on screen yet. Names on
  file stay locked (encrypted), and the board now keeps a scrambled fingerprint of each
  name that can't be turned back into the name itself. When the lookup screen arrives
  later, a coordinator will be able to type a name and find the right record — within
  their own community only — without the board ever unlocking anyone else's. People
  already on file get their fingerprint added in a later, separately approved step.

## 2026-07-18

- **The demo parish now speaks American English.** St. Brigid's sample notices traded their
  Irish turns of phrase for American ones — a ride to the 9:30 Mass instead of a lift to
  half-nine, math help instead of maths, a crib instead of a cot, the grocery run instead of
  the big shop — so a first-time American reader never mistakes the wording for a typo. Same
  twelve neighbours, same warmth; the coordinator sign-in is now **tom** (was tomas).

## 2026-07-17

- **The Identity form no longer eats your words.** Type a patron line that's a touch too
  long and the page now hands everything back — your welcome lines, your blurb, all of it —
  with a note about what to shorten, instead of bouncing you to a fresh form.
- **Every screen passes the readability bar now.** The darker quiet-grey text reached the
  last six older screens — the landing page, the join page, the board's offer cards, and
  the match pages. The automated check that runs with the demo gallery now measures zero
  accessibility violations across all nineteen screens it audits, and a test keeps the
  too-faint tints from coming back.
- **Easier to read, for everyone.** The quiet grey text across the newer screens is a
  shade darker now — enough that tired eyes and bright sunlight don't lose it. The
  filters on the board finally introduce themselves to screen readers, and the labels
  on the bottom bar are clearer too. An automated accessibility check now runs with
  every demo gallery, so this doesn't quietly slip back.
- **The demo walkthrough grew three screens.** What a visitor sees at a community's
  front door, a page in the parish's own words, and the protocol page every footer
  points home to.
- **The board wears your community's own face.** Settings gains an Identity section:
  your patron, your welcome lines, your sign-in blurb, and which of the board's scenes
  greet people on the hub and the front door. Blank keeps the warm default — nothing
  needs filling in for the board to feel finished.
- **The hub greets with your words, and they turn over daily.** Write up to ten welcome
  lines and the greeting under a member's name rotates through them, one per day — the
  same line for everyone all day. Only words your coordinators wrote ever appear.
- **The hub carries your pages.** A quiet "Your community" card shows the first few
  pages with a door to the rest. Belong to two communities? Each hub wears its own
  face, whole.
- **The demo parish tells its story.** St. Brigid's now seeds with its patron, its
  welcome lines, and four pages — the story on the front door, Mass times live, a
  ministries draft, and an old bulletin put away.

## 2026-07-16

- **Community pages are on the board.** The pages your coordinators write now show up:
  members find them under Pages on the hub and at the bottom of every screen, each one
  signed "Written by the coordinators" — always. A community can also choose pages for
  its front door, so a neighbour who isn't signed in yet can read them and find the
  join door. Private communities stay private: from the outside, a private board and no
  board at all look exactly the same.
- **Pages can be reported, like anything else on the board.** "Something wrong with this
  page?" sits at the bottom of every page. A coordinator can take a reported page off the
  board with one press, and put it back just as easily. Nothing is deleted.
- **A put-away page says so, warmly.** Following an old link to an archived page tells a
  member it was put away and may return — without teasing what it said.
- **Your community can start writing its own pages.** Coordinators and admins now have
  "Your pages" in Settings: write a draft in plain text, preview it exactly as it will
  look, and keep shaping it until it's right. Only an admin can publish — that's the
  community signing its name. Pages are never deleted, only put away, and anything put
  away can come back as a draft.
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
