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
    # Series only: when its episodes were last asked from TMDB. Empty until the first time.
    episodes_refreshed_at = models.DateTimeField(null=True, blank=True)
    # Series only: TMDB's own word for where the series stands ("Returning Series", "Ended",
    # "Canceled"...), as of the last refresh. Empty until the first time. A series only counts
    # as finished once this says it ended (see core/episodes.py).
    status = models.CharField(max_length=40, blank=True)
    # Series only: its IMDb id as TMDB gives it (like "tt11691774"), empty when TMDB has none. It is how the series
    # is found on TVmaze, the second source for upcoming episode dates.
    imdb_id = models.CharField(max_length=20, blank=True)
    # Series only: the series' own id on TVmaze, remembered so TVmaze is asked one question and not two. Empty until
    # it was found, and when TVmaze does not know the series.
    tvmaze_id = models.PositiveIntegerField(null=True, blank=True)
    # Movie only: the earliest cinema release and the earliest streaming (digital) release TMDB lists in any
    # country, as the moments TMDB gives them (always midnight UTC). Empty when TMDB has none yet. The calendar
    # turns each into a day in the account's own time zone when it is shown.
    cinema_at = models.DateTimeField(null=True, blank=True)
    streaming_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = (
            # TMDB numbers movies and series separately, so the kind is part of the identity.
            models.UniqueConstraint(fields=['kind', 'tmdb_id'], name='one_row_per_tmdb_title'),
        )

    def __str__(self):
        return f'{self.title} ({self.kind})'


class Episode(models.Model):
    """One episode of a series, saved from TMDB and shared by every account (design rule 6).

    Episodes are matched with TMDB's own id, so an episode that TMDB renumbers is the same row
    and keeps the watches pointing at it. Rows are never deleted.
    """

    title = models.ForeignKey(Title, on_delete=models.CASCADE, related_name='episodes')
    tmdb_id = models.PositiveIntegerField()
    # Season 0 is TMDB's "Specials".
    season_number = models.PositiveIntegerField()
    episode_number = models.PositiveIntegerField()
    name = models.CharField(max_length=300, blank=True)
    # Empty when TMDB has no date yet. Only the day matters, as TMDB gives it.
    air_date = models.DateField(null=True, blank=True)
    # In minutes. Empty when TMDB has none.
    runtime = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        constraints = (
            models.UniqueConstraint(fields=['title', 'tmdb_id'], name='one_row_per_tmdb_episode'),
        )

    def __str__(self):
        return f'{self.title.title} S{self.season_number}E{self.episode_number}'


class UpcomingEpisode(models.Model):
    """An episode that TVmaze says is coming and that is not (yet) known by TMDB, kept for the Calendar only.

    TVmaze often lists a whole season's weekly dates when TMDB lists only the first episode. These rows
    are not `Episode`s: nothing can be watched, counted or marked through them, so no watch can ever point
    at one. Each refresh replaces all of a series' rows, so rows come and go freely.
    """

    title = models.ForeignKey(Title, on_delete=models.CASCADE, related_name='upcoming_episodes')
    season_number = models.PositiveIntegerField()
    episode_number = models.PositiveIntegerField()
    # As TVmaze gives it, which can be a placeholder such as "TBA".
    name = models.CharField(max_length=300, blank=True)
    # Only the day matters, as TVmaze gives it.
    air_date = models.DateField()

    def __str__(self):
        return f'{self.title.title} S{self.season_number}E{self.episode_number} (TVmaze)'


class Watch(models.Model):
    """One time an account watched a title, with its own date (design rule 1).

    There is no "one per title" limit, so a rewatch is just another row. A watch of an episode
    has `episode` filled in (and `title` is its series); a watch of a movie has it empty.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.ForeignKey(Title, on_delete=models.CASCADE)
    episode = models.ForeignKey(Episode, null=True, blank=True, on_delete=models.CASCADE)
    # The day it was watched, in the account's own time zone. Empty means "date unknown".
    # For an episode it is the day the button was pressed.
    watched_on = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        what = self.episode or self.title
        return f'{self.user}: {what} on {self.watched_on or "unknown date"}'


class ToWatchItem(models.Model):
    """One title on one account's To Watch list.

    Removing a title only fills in `removed_at`, so undo can bring it back exactly as it was.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.ForeignKey(Title, on_delete=models.CASCADE)
    added_at = models.DateTimeField(default=timezone.now)
    # Empty while the title is on the list.
    removed_at = models.DateTimeField(null=True, blank=True)
    # Set when the title left the list because it was marked as watched (not removed by hand).
    # Un-marking that watch puts the title back on the list, and "Recently removed" skips it.
    removed_by_watch = models.ForeignKey(Watch, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')

    class Meta:
        constraints = (
            # Adding the same title twice never makes a second entry.
            models.UniqueConstraint(fields=['user', 'title'], name='one_to_watch_entry_per_title'),
        )

    def __str__(self):
        return f'{self.user}: {self.title}' + (' (removed)' if self.removed_at else '')
