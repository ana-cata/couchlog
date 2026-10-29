"""Series and their episodes, apart from the screens: keeping them up to date, and which tab of
the Series section a series is in for an account (To Watch, Watching or Finished)."""

from django.db import transaction
from django.db.models import Count, Max
from django.utils import timezone

from . import tmdb
from .models import Episode, Title, Watch

# What TMDB says about a series that is over. A series is only "finished" for me once it says one of these.
ENDED_STATUSES = ('Ended', 'Canceled', 'Cancelled')


def refresh_episodes(series):
    """Ask TMDB for the series' status and episodes, and save them.

    Episodes are matched with TMDB's own id: a renumbered or renamed episode is updated in place
    (so its watches stay with it), a new one is added, and none is ever deleted. TMDB is asked first,
    so when it fails (it raises `tmdb.TmdbError`) nothing is saved.
    """
    details = tmdb.get_series_episodes(series.tmdb_id)
    with transaction.atomic():
        Episode.objects.bulk_create(
            [Episode(title=series, **episode) for episode in details['episodes']],
            update_conflicts=True,
            unique_fields=['title', 'tmdb_id'],
            update_fields=['season_number', 'episode_number', 'name', 'air_date', 'runtime'],
        )
        series.status = details['status']
        series.episodes_refreshed_at = timezone.now()
        series.save(update_fields=['status', 'episodes_refreshed_at'])


def started_series(user):
    """The ids of the series this account has marked at least one episode of (any episode, a special too)."""
    return Watch.objects.filter(user=user, episode__isnull=False).values('title')


def series_tabs(user, today):
    """The series this account has started, as two lists of series: (watching, finished).

    Both are worked out from the account's watches and TMDB's status each time, so un-marking an
    episode moves a series back by itself. The most recently marked series come first.

    A series is finished when TMDB says it ended or was cancelled **and** every episode that has
    aired (on or before `today`, the account's own day) is watched. Specials (season 0) do not have
    to be watched, and episodes that have not aired or have no date do not count. Every other
    started series is watching, including one that is caught up but still running.
    """
    marked = Watch.objects.filter(user=user, episode__isnull=False)
    last_marked = dict(
        marked.values('title').annotate(last=Max('created_at')).values_list('title', 'last')
    )
    if not last_marked:
        return [], []

    # Rule 2 of the design rules: an episode counts as watched if it has at least one watch.
    aired = dict(
        Episode.objects.filter(title__in=last_marked, season_number__gt=0, air_date__lte=today)
        .values('title')
        .annotate(count=Count('id'))
        .values_list('title', 'count')
    )
    watched = dict(
        marked.filter(episode__season_number__gt=0, episode__air_date__lte=today)
        .values('title')
        .annotate(count=Count('episode', distinct=True))
        .values_list('title', 'count')
    )
    series_by_id = Title.objects.in_bulk(last_marked)

    watching, finished = [], []
    for series_id in sorted(last_marked, key=last_marked.get, reverse=True):
        series = series_by_id[series_id]
        all_watched = aired.get(series_id, 0) > 0 and watched.get(series_id, 0) >= aired[series_id]
        (finished if series.status in ENDED_STATUSES and all_watched else watching).append(series)
    return watching, finished
