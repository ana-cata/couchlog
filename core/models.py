from django.conf import settings
from django.db import models


class Profile(models.Model):
    """Per-account settings. One row per account, created when first needed."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    # A name from the IANA list, for example "Europe/Lisbon". Empty until the account
    # picks one at the first login.
    timezone = models.CharField(max_length=64, blank=True)

    def __str__(self):
        return f'{self.user} ({self.timezone or "no time zone yet"})'
