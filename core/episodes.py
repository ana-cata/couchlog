"""Series and their episodes, apart from the screens: keeping them up to date, marking many episodes
at once, and which tab of the Series section a series is in for an account (To Watch, Watching or Finished)."""

import uuid

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


def episodes_up_to(episode):
    """The episodes from season 1, episode 1 up to and including `episode`, in the order the series page lists them.

    Specials (season 0) are not part of that order, so this is for a regular episode.
    """
    in_order = episode.title.episodes.filter(season_number__gt=0).order_by('season_number', 'episode_number', 'id')
    up_to = []
    for candidate in in_order:
        up_to.append(candidate)
        if candidate.id == episode.id:
            break
    return up_to


def mark_episodes(user, episodes, today):
    """Mark many episodes as watched at once, for "mark a season" and "watched up to here".

    Only an episode that has aired (on or before `today`, the account's own day) and that the account
    has not marked yet gets a watch, dated `today` like a single mark. The rest are left alone, so an
    episode marked earlier keeps its watch and its date. All the new watches share one `batch`, which
    is what `undo_batch` removes.

    Returns the episodes that were newly marked and the batch (both empty when there was nothing new).
    """
    already = set(Watch.objects.filter(user=user, episode__in=episodes).values_list('episode', flat=True))
    new = [
        episode
        for episode in episodes
        if episode.air_date is not None and episode.air_date <= today and episode.id not in already
    ]
    if not new:
        return [], None
    batch = uuid.uuid4()
    Watch.objects.bulk_create(
        [Watch(user=user, title_id=episode.title_id, episode=episode, watched_on=today, batch=batch) for episode in new]
    )
    return new, batch


def undo_batch(user, batch):
    """Remove exactly the watches one `mark_episodes` call added (the account's own), and nothing else.

    Returns the episodes that are no longer marked. A watch that was already un-marked one by one is
    simply not there any more, and an episode marked again since by hand has a different watch, so
    it stays marked.
    """
    watches = Watch.objects.filter(user=user, batch=batch).select_related('episode__title')
    episodes = [watch.episode for watch in watches]
    watches.delete()
    return episodes


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
