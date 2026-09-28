"""Give the seeded demo accounts a new, private password.

`seed_demo_parish` creates twelve accounts that share one password, and that password is
written in this public repository. On a laptop that is the point. On a live site it means
anyone can sign in as the demo parish's admin or coordinator — and a coordinator can vouch
ANY account on the instance as a verified human, because the vouch resolves its target by
username alone. Run this straight after every seed on a live site.

The new password is read from stdin and never printed, so it stays out of shell history,
process lists and logs:

    python manage.py rotate_demo_password < ~/.config/umi/demo-password.txt

Only the seed's own usernames with an @demo.invalid address are touched: a real registrant
who happened to type a .invalid address is left alone. Each rotation is audited.
"""

import sys

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.audit.services import emit

from .seed_demo_parish import DEMO_PASSWORD, MEMBERS

DEMO_DOMAIN = "@demo.invalid"
MIN_LENGTH = 16


class Command(BaseCommand):
    help = "Set a new password, read from stdin, on every seeded demo account."

    def handle(self, *args, **options):
        password = sys.stdin.readline().strip()
        if len(password) < MIN_LENGTH:
            raise CommandError(f"refusing: pipe a new password of at least {MIN_LENGTH} characters on stdin")
        if password == DEMO_PASSWORD:
            raise CommandError("refusing: that is the public password this command exists to replace")
        try:
            validate_password(password)
        except ValidationError as exc:
            raise CommandError("refusing: " + " ".join(exc.messages)) from exc

        usernames = [username for username, _display, _role in MEMBERS]
        demo = get_user_model().objects.filter(username__in=usernames, email__iendswith=DEMO_DOMAIN)
        if not demo.exists():
            raise CommandError("no seeded demo accounts found; nothing to rotate")

        rotated = 0
        with transaction.atomic():
            for user in demo:
                user.set_password(password)
                user.save(update_fields=["password"])
                emit("demo.password_rotated", user)
                rotated += 1
        self.stdout.write(f"Rotated the password on {rotated} seeded demo accounts.")
