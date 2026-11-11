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
    # The wide banner picture, shown in the News section on Home. Empty when TMDB has none, and for a title saved
    # before banners were kept, until `refresh_calendar` runs.
    backdrop_url = models.CharField(max_length=300, blank=True)
    overview = models.TextField(blank=True)
    # In minutes, for the time spent watching. A movie's own runtime, or for a series its typical episode runtime (the
    # average of its episodes' runtimes), used for an episode that has none of its own. Empty when TMDB has none, and
    # for a title saved before runtimes were kept, until `refresh_calendar` (or a series page refresh) runs.
    runtime = models.PositiveIntegerField(null=True, blank=True)
    # TMDB's genres for the title, in TMDB's order, as a list like [{"id": 18, "name": "Drama"}]. Empty when TMDB has
    # none, and for a title saved before genres were kept, until `refresh_calendar` (or a series page refresh) runs.
    genres = models.JSONField(default=list, blank=True)
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


class DroppedSeries(models.Model):
    """A series one account gave up on (Series → Dropped).

    It is the only status set by hand, and it wins over To Watch, Watching and Finished. Dropping touches
    nothing else (not the watches, not the To Watch entry), so bringing the series back, which deletes this
    row, puts everything back as it was.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.ForeignKey(Title, on_delete=models.CASCADE)
    dropped_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = (
            # Dropping the same series twice never makes a second entry.
            models.UniqueConstraint(fields=['user', 'title'], name='one_dropped_entry_per_series'),
        )

    def __str__(self):
        return f'{self.user}: {self.title} (dropped)'


class RemovedSeries(models.Model):
    """What one account had for a series when it pressed "Remove from all lists", kept only for the Undo.

    Removing deletes the watches, the To Watch entry, the dropped state, the rating and the note. This row holds
    them, written out by Django's serializer with their ids, so Undo writes back exactly the same rows. It is
    deleted by the Undo, and once the Undo window is over the next visit to Series → To Watch deletes it too.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.ForeignKey(Title, on_delete=models.CASCADE)
    removed_at = models.DateTimeField(default=timezone.now)
    rows = models.TextField()

    # "Recently removed" lists this next to the To Watch entries removed by hand, and tells them apart by this.
    everything = True

    class Meta:
        constraints = (
            # Removing the same series again replaces the copy: only the last removal can be undone.
            models.UniqueConstraint(fields=['user', 'title'], name='one_removed_copy_per_series'),
        )

    def __str__(self):
        return f'{self.user}: {self.title} (removed from all lists)'


class Rating(models.Model):
    """One account's star rating and short note for one title (a movie or a series).

    The row only exists while there is something to keep: removing both the stars and the note deletes it. Changing
    either one is done by saving again from the title's page, which is also the way back after a mistake.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.ForeignKey(Title, on_delete=models.CASCADE)
    # 1 to 5 whole stars. Empty means no rating, which is not the same as 1 star.
    stars = models.PositiveSmallIntegerField(null=True, blank=True)
    note = models.TextField(blank=True)

    class Meta:
        constraints = (
            # One rating per account and title: saving again changes it.
            models.UniqueConstraint(fields=['user', 'title'], name='one_rating_per_title'),
        )

    @property
    def stars_text(self):
        """The stars as characters, like "★★★★☆" for 4. Empty when there is no rating."""
        return '★' * self.stars + '☆' * (5 - self.stars) if self.stars else ''

    def __str__(self):
        return f'{self.user}: {self.title} ({self.stars or "no"} stars)'


class DemoEvent(models.Model):
    """One thing that counts toward a limit of the public demo (core/demo.py). Only written in demo mode.

    The limits are worked out by counting these rows over the last hour or the last 24 hours. A row says what
    happened and when, and for a visitor's own limits which demo account it was. Nothing else: no email, no IP address.
    Rows older than 24 hours are deleted when a new demo account starts.
    """

    class Kind(models.TextChoices):
        ACCOUNT = 'account', 'New demo account'
        SEARCH = 'search', 'Search'
        CHANGE = 'change', 'Change'
        TMDB = 'tmdb', 'TMDB request'

    kind = models.CharField(max_length=7, choices=Kind)
    # Only for a visitor's own limits (searches and changes). Deleting the account deletes its rows.
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE)
    at = models.DateTimeField(default=timezone.now, db_index=True)

    def __str__(self):
        return f'{self.get_kind_display()} at {self.at:%Y-%m-%d %H:%M}' + (f' ({self.user})' if self.user else '')
