"""send_smoke — prove email delivery actually works, end to end.

The pilot-parish finding this exists for: production defaults to the console email
backend, so a "sent" password-reset email can die silently in a log while the code paths
all report success. This command sends one real email through whatever backend the
running settings resolve, and PRINTS the backend first, so "it ran" can never be mistaken
for "it delivered" — the receipt is the message arriving in a real inbox.

Usage:
    python manage.py send_smoke steward@example.org
"""

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Send one test email to the given address and print the active email backend."

    def add_arguments(self, parser):
        parser.add_argument("to", help="Destination email address for the smoke test")

    def handle(self, *args, **options):
        to = options["to"]
        backend = settings.EMAIL_BACKEND
        self.stdout.write(f"EMAIL_BACKEND = {backend}")
        if backend.endswith("console.EmailBackend"):
            self.stdout.write(
                self.style.WARNING(
                    "Console backend: the message below prints to this terminal and is NOT "
                    "delivered. Configure SMTP env vars (see docs/email-delivery-runbook.md)."
                )
            )
        sent = send_mail(
            "UMI Exchange email smoke test",
            "This is the delivery smoke test. If you are reading this in a real inbox, outbound email works.",
            None,  # DEFAULT_FROM_EMAIL
            [to],
            fail_silently=False,
        )
        self.stdout.write(self.style.SUCCESS(f"send_mail reported {sent} message(s) handed to the backend."))
        self.stdout.write("Delivery is proven only by the message arriving. Check the inbox.")
