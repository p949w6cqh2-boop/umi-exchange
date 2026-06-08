"""
Management command to test email delivery.
Usage: python manage.py test_email recipient@example.com
"""

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Send a test email to verify SMTP configuration."

    def add_arguments(self, parser):
        parser.add_argument(
            "recipient",
            type=str,
            help="Email address to send the test email to.",
        )

    def handle(self, *args, **options):
        recipient = options["recipient"]

        self.stdout.write(f"Email backend: {settings.EMAIL_BACKEND}")
        self.stdout.write(f"From: {settings.DEFAULT_FROM_EMAIL}")
        self.stdout.write(f"Host: {settings.EMAIL_HOST}:{settings.EMAIL_PORT}")
        self.stdout.write(f"TLS: {settings.EMAIL_USE_TLS}")
        self.stdout.write(f"User: {settings.EMAIL_HOST_USER or '(none)'}")
        self.stdout.write(f"Sending to: {recipient}")
        self.stdout.write("")

        try:
            sent = send_mail(
                subject="[UMI] Test Email",
                message=(
                    "This is a test email from your UMI Exchange instance.\n\n"
                    "If you received this, your email configuration is working correctly.\n\n"
                    "-- UMI Exchange"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient],
                fail_silently=False,
            )
            if sent:
                self.stdout.write(self.style.SUCCESS(f"Email sent to {recipient}"))
            else:
                self.stdout.write(self.style.WARNING("Email returned 0 (not sent)."))
        except Exception as e:
            raise CommandError(f"Email failed: {e}")
