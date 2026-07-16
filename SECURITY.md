# Reporting a security problem

Thank you for looking out for the people who use these boards. Real neighbours put real
needs on them, so we treat every report seriously.

## How to reach us

Email **usermegadatainfrastructure@proton.me** with whatever you've found. Plain words are
fine — you don't need a formal write-up. Tell us what you saw, where, and how to see it
again if you know. This address is monitored by the founder; when the project deploys under
its own domain, it'll move to a `security@` address and this file will say so.

We'll read it, write back as fast as we can, and tell you honestly what we're doing about it.

## What we ask

- **Write to us first.** Give us a chance to fix it before you post it anywhere public.
- **Don't touch other people's data.** If proving the problem would mean reading a real
  person's needs, cases, or contact details, stop and describe the path instead. You can
  run your own instance in minutes ([README](README.md)) and test against that freely.
- **Don't run destructive tests** against anyone's live board.

## What's in scope

Anything in this repository: the Django app, its authentication and authorization, the
encryption and crypto-shred paths, federation, the deployment configs in `docker/`.

## Where the promises live

What the software promises about privacy, consent, and retention is written down in
[the UMI Protocol](docs/protocol/spec.md) — served on every instance at `/protocol/`.
If an instance breaks one of those promises, that's a security problem too. Tell us.
