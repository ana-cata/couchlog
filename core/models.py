from django.conf import settings
from django.db import models
from django.utils import timezone


class Profile(models.Model):
    """Per-account settings. One row per account, created when first needed."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    # A name from the IANA list, for example "Europe/Lisbon". Empty until the account
    # picks one at the first login.
    timezone = models.CharField(max_length=64, blank=True)

    def __str__(self):
        return f'{self.user} ({self.timezone or "no time zone yet"})'


class Title(models.Model):
    """A movie or series saved from TMDB, shared by every account.

    The details are copied here when someone first adds the title, so the app works from
    its own data (design rule 6). Later features (watches, episodes, the calendar) point to it.
    """

    class Kind(models.TextChoices):
        MOVIE = 'movie', 'Movie'
        SERIES = 'series', 'Series'

    kind = models.CharField(max_length=6, choices=Kind)
    tmdb_id = models.PositiveIntegerField()
    title = models.CharField(max_length=300)
    # The first four characters of TMDB's date, or empty when TMDB has none.
    year = models.CharField(max_length=4, blank=True)
    poster_url = models.CharField(max_length=300, blank=True)
    overview = models.TextField(blank=True)

    class Meta:
        constraints = (
            # TMDB numbers movies and series separately, so the kind is part of the identity.
            models.UniqueConstraint(fields=['kind', 'tmdb_id'], name='one_row_per_tmdb_title'),
        )

    def __str__(self):
        return f'{self.title} ({self.kind})'


class ToWatchItem(models.Model):
    """One title on one account's To Watch list.

    Removing a title only fills in `removed_at`, so undo can bring it back exactly as it was.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.ForeignKey(Title, on_delete=models.CASCADE)
    added_at = models.DateTimeField(default=timezone.now)
    # Empty while the title is on the list.
    removed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = (
            # Adding the same title twice never makes a second entry.
            models.UniqueConstraint(fields=['user', 'title'], name='one_to_watch_entry_per_title'),
        )

    def __str__(self):
        return f'{self.user}: {self.title}' + (' (removed)' if self.removed_at else '')
