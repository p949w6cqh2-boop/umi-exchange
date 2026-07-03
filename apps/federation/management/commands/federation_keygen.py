"""Generate an Ed25519 instance keypair for federation (§3.1). Prints the
private JWK to stdout — nothing is written to disk; the operator puts it in
the environment as FEDERATION_PRIVATE_KEY."""

import json

from django.core.management.base import BaseCommand

from apps.federation import crypto


class Command(BaseCommand):
    help = "Generate the federation instance keypair; prints the private JWK for FEDERATION_PRIVATE_KEY."

    def handle(self, *args, **options):
        jwk = crypto.generate_private_jwk()
        public = {k: v for k, v in jwk.items() if k != "d"}
        self.stdout.write(self.style.WARNING("Add to your environment (keep it secret, like ENCRYPTION_KEYS):"))
        self.stdout.write(f"FEDERATION_PRIVATE_KEY='{json.dumps(jwk)}'")
        self.stdout.write("")
        self.stdout.write(f"Instance id (share this thumbprint out-of-band): {crypto.jwk_thumbprint(public)}")
