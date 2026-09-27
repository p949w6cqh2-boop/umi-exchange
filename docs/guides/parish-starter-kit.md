# Parish starter kit

*Try UMI with your own hands in an afternoon, watch one neighbour's need go from asked to
answered, and take the ready-made pieces your parish needs to start.*

This kit is the hands-on companion to
[How to start your own UMI community](start-your-own-community.md), which explains the two ways to
run it. Read that for *which door*. Use this to *practice* before you walk through one.

---

## 1. Try it on your laptop (about 30 minutes)

The best way to understand UMI is to run it, fill it with a practice parish, and use it as three
different people. Everything here happens on your own computer. Nothing touches any live site.

**You need:** a computer with Python 3.12 and git. No server, no domain, no account anywhere.

```bash
git clone https://github.com/p949w6cqh2-boop/umi-exchange.git
cd umi-exchange
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py seed_demo_parish
python manage.py runserver
```

The seed command builds **St. Brigid's**, a made-up parish: 12 members, 7 needs, 6 offers and
3 matches. When it finishes it tells you who to sign in as. Open **http://localhost:8000**.

**The practice accounts** all share one password, printed in
`apps/communities/management/commands/seed_demo_parish.py`. It exists only on your laptop: the
seed command refuses to run on a production site.

| Sign in as | Role | Use them to see |
|---|---|---|
| `nuala` | member | what it's like to ask for help |
| `tom` | coordinator | what a coordinator can do: vouch, moderate, see the whole board |
| `marta` | admin | community settings, the join code, adding coordinators |

### Exercise 1: be Nuala (10 minutes)

1. Sign in as `nuala`.
2. Find her need, **"A ride to the 9:30 Mass on Sunday."** Read it the way a neighbour would.
3. Post a need of your own in the **Transport** category: one plain sentence, and how urgent it
   is. (Transport, because Exercise 2 needs someone who already offers rides.)
4. Sign out.

**Notice:** how much did you have to think? Every question you had is one your parishioners
will have.

### Exercise 2: be the helper (10 minutes)

1. Sign in as `dan`. He has already offered **"I can drive Sunday mornings."**
2. Open the need you posted as Nuala.
3. Under it, you'll see Dan's offer with a **Propose Match** button. Press it.
4. Sign out, sign back in as `nuala`, and open the match.
5. Press **Accept match**, then confirm.

**Why Dan and not anyone:** a helper sees Propose Match only beside an offer *they* have already
made in the same category as the need. Someone with no ride offer sees no button on a ride need.
That's by design: a match pairs a real ask with a real offer.

**Notice:** after both said yes, what does each person see about the other? That moment is the
whole point of the board.

### Exercise 3: be the coordinator (10 minutes)

1. Sign in as `marta` and open the community's **settings page**.
2. Find the **Join Code** and its QR code at the top. That's what goes in your bulletin.
3. Find **Vouch for a neighbour** lower down. That's how a coordinator confirms someone is a real
   person without needing their email.
4. Change `tom`'s role, then change it back. Notice who is allowed to do that.

**Done when** you've asked, helped and coordinated, each once.

---

## 2. Worked example: one need, start to finish

Here is Nuala's ride to Mass, every step, whose hand and which screen.

| Step | Who | Screen | What happens | The need is now |
|---|---|---|---|---|
| 1 | Nuala | New need | Posts *"A ride to the 9:30 Mass on Sunday,"* category Transport, urgency high | **open** |
| 2 | Dan, who offered Sunday rides | The need | Presses **Propose Match** beside his own ride offer | open, with a proposed match |
| 3 | Nuala | The match | Presses **Accept match**, confirms | **matched** |
| 4 | Both | The match | Each can now see how to reach the other, by the way each chose | matched |
| 5 | Either | The match | After Sunday, presses **Mark fulfilled** | **fulfilled** |

A match that stalls can be **cancelled**; one that never gets accepted **expires**. Nobody's need
is left hanging with no way to close it.

**Why step 4 matters:** contact details are shown only after both people say yes, and only the
ways each person chose to be reached. Until then, nobody's phone number or email is on display.

---

## 3. Ready-made pieces

### A starting set of categories

These six are what St. Brigid's uses. Change them to fit your parish from the settings page.

| Category | What it covers |
|---|---|
| Transport | rides to Mass, appointments, the shops |
| Meals | a dinner after a hospital stay, a new baby, a funeral |
| Home Repair | a dripping tap, a stuck window, a ramp |
| Tutoring | homework help, reading, a skill someone can teach |
| Company | a visit, a phone call, a walk |
| Groceries | picking up and dropping off |

### A bulletin notice you can adapt

> **Need a hand, or have one to give?** Our parish now has a private board where neighbours ask
> for help and offer it: a ride to Mass, a meal, a fixed shelf. Only parishioners can see it. To
> join, go to **[your site]/join/** and enter the code **[your code]**, or scan the QR code at
> the back of church. No email needed. Questions: **[coordinator's name]** after Mass.

### A practice session for your coordinators

Before anyone helps a parishioner sign up, have them do it once themselves. The pattern that
works:

1. **Coordinators make their own account first**, on their own phone, so they know every screen.
2. **One person at a time, start to finish.** Slower, and you learn far more.
3. **The parishioner does the typing.** The coordinator coaches. People remember what their own
   hands did.
4. **After each sign-up, a coordinator vouches for them by username.** If the vouch can't find
   the name, the sign-up didn't go through. Do it again, slowly.
5. **A week later, ask each person their username, with no warning.** Their answers tell you
   whether your sign-up process works.

Two things will catch you out, so plan for them:

- **A form filled in too fast is treated as a robot and quietly dropped.** Autofill does this.
  Type by hand and pause before pressing Register. Step 4 catches it every time.
- **The site allows three sign-ups a minute from one internet connection.** A whole room on the
  parish wifi counts as one. Space people out.

---

## 4. Before a real need goes on your board

Practice needs are fine. **A real person's real need is different**, and there is a checklist
for it: [the ethics and safety gate](../ethics-and-safety.md). Six things must be true first,
among them backups that work, alerts that reach a person, and a second person who can stop the
whole thing if it goes wrong.

The site this project runs publishes its own gate status in that file, unticked boxes included.
Use it as a worked example of what "not ready yet" honestly looks like.

---

## Where each fact in this kit comes from

For anyone who wants to check. Every claim above, tied to the code or doc it came from.

| Claim | Source |
|---|---|
| The seed builds 12 members, 7 needs, 6 offers, 3 matches, and names who to sign in as | `seed_demo_parish` output, run on a fresh database 2026-09-26 |
| Exercises 1 and 2 work as written: a new Transport need, Dan sees Propose Match beside his offer, his press makes a proposed match, Nuala sees Accept match. A member with no ride offer sees no button. | walked through the real views on a fresh seeded database, 2026-09-26 |
| The seed refuses to run on a production site | `apps/communities/management/commands/seed_demo_parish.py:5-6` |
| `marta` is admin, `tom` coordinator, the rest members | same file, `MEMBERS` (line 24) |
| St. Brigid's six categories | same file, `CATEGORIES` (line 40) |
| Nuala's need, Transport, urgency high | same file, `NEEDS` |
| A helper sees Propose Match only beside their own active offer in the need's category, never on their own need | `apps/needs/views.py:113-129` (`suggested_offers`); `templates/needs/detail.html`, `{% if not is_own_need %}` |
| `dan` offers "I can drive Sunday mornings" in Transport; all 12 seeded users are verified, so none hits the sign-up gate | seeded database, checked 2026-09-26; `seed_demo_parish.py:228-230` |
| Accept match and Mark fulfilled show only to the two people in the match | `templates/matches/detail.html`, `is_participant` |
| A match goes proposed → accepted → fulfilled, and can be cancelled or expire | `apps/matches/models.py:24-27`, `VALID_TRANSITIONS` |
| A need is open, matched, fulfilled, closed or expired | `apps/needs/models.py:12-17` |
| Contact shows only after both say yes, only by the way each chose | `apps/communities/models.py`, `Member.contact_dict`; §8.2 |
| Join code and QR at the top of the settings page; Vouch for a neighbour lower down | `templates/communities/settings.html:13` and `:187` |
| A too-fast form is quietly dropped | `apps/accounts/verification.py:25` (`MIN_FORM_SECONDS = 3`); issue #170 |
| Three sign-ups a minute per connection | `apps/accounts/views.py:39` (`rate="3/m"`) |
| Email is optional | `apps/accounts/models.py:11` |
