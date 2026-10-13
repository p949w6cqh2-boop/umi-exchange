"""two_factor's setup wizard with its re-enrolment guard on every method (2026-10 bug hunt, L54).

The package's SetupView refuses to start when the account already has a device, but only on GET. A
session from before the owner enrolled (a shared tablet, a stolen cookie) could POST the wizard's
steps, add a second device, and come out of it verified, which opens the Disable view.
"""

from django.shortcuts import redirect
from two_factor.utils import default_device
from two_factor.views import SetupView


class GuardedSetupView(SetupView):
    def post(self, request, *args, **kwargs):
        if default_device(request.user):
            return redirect(self.get_success_url())
        return super().post(request, *args, **kwargs)
