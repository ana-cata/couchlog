"""Series and their episodes, apart from the screens: keeping them up to date, marking many episodes
at once, and which tab of the Series section a series is in for an account (To Watch, Watching, Finished or Dropped)."""

from django.db import transaction
from django.db.models import Count, Max
from django.utils import timezone

from . import tmdb
from .models import DroppedSeries, Episode, Title, Watch

# What TMDB says about a series that is over. A series is only "finished" for me once it says one of these.
ENDED_STATUSES = ('Ended', 'Canceled', 'Cancelled')


def refresh_episodes(series):
    """Ask TMDB for the series' status, IMDb id, banner and episodes, and save them.

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
        series.imdb_id = details['imdb_id']
        series.backdrop_url = details['backdrop_url']
        series.episodes_refreshed_at = timezone.now()
        series.save(update_fields=['status', 'imdb_id', 'backdrop_url', 'episodes_refreshed_at'])


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


def skipped_episodes(user, episode, today):
    """What marking `episode` skips over, which is what the page asks about: (last_marked, skipped).

    Marking a regular episode that has aired when episodes before it are not marked is a sign they were watched
    too. `skipped` are the episodes that have aired and are not marked between the nearest episode this account
    has marked before it (in the order the series page lists them) and `episode`, or all the episodes before it
    that have aired when none before it is marked. They are in page order. `last_marked` is that nearest marked
    episode, or None when there is none. Episodes marked after `episode`, and holes before `last_marked`, do not
    matter: the account has already moved past those.

    `skipped` is empty (nothing to ask) for a special, for an episode that has not aired, or when nothing is skipped.
    """
    if episode.season_number == 0 or episode.air_date is None or episode.air_date > today:
        return None, []
    marked = set(
        Watch.objects.filter(user=user, title_id=episode.title_id, episode__season_number__gt=0).values_list(
            'episode', flat=True
        )
    )
    last_marked, skipped = None, []
    for earlier in reversed(episodes_up_to(episode)[:-1]):
        if earlier.id in marked:
            last_marked = earlier
            break
        if earlier.air_date is not None and earlier.air_date <= today:
            skipped.append(earlier)
    skipped.reverse()
    return last_marked, skipped


def mark_episodes(user, episodes, today):
    """Mark many episodes as watched at once, for "mark a season" and the question's "Yes" (the skipped ones and this one).

    Only an episode that has aired (on or before `today`, the account's own day) and that the account
    has not marked yet gets a watch, dated `today` like a single mark. The rest are left alone, so an
    episode marked earlier keeps its watch and its date.

    Returns the episodes that were newly marked (none when there was nothing new).
    """
    already = set(Watch.objects.filter(user=user, episode__in=episodes).values_list('episode', flat=True))
    new = [
        episode
        for episode in episodes
        if episode.air_date is not None and episode.air_date <= today and episode.id not in already
    ]
    Watch.objects.bulk_create(
        [Watch(user=user, title_id=episode.title_id, episode=episode, watched_on=today) for episode in new]
    )
    return new


def unmark_episodes(user, episodes):
    """Mark many episodes as not watched at once, for the season button pressed again.

    Deletes the account's own watches of `episodes` and nothing else, so it is the undo of `mark_episodes`
    (the watches come back dated the day they are marked again). Returns the episodes that were marked
    and are not any more.
    """
    watches = Watch.objects.filter(user=user, episode__in=episodes)
    marked = set(watches.values_list('episode', flat=True))
    watches.delete()
    return [episode for episode in episodes if episode.id in marked]


def started_series(user):
    """The ids of the series this account has marked at least one episode of (any episode, a special too)."""
    return Watch.objects.filter(user=user, episode__isnull=False).values('title')


def dropped_series(user):
    """The ids of the series this account dropped. A dropped series is in no other tab, Up Next or the Calendar."""
    return DroppedSeries.objects.filter(user=user).values('title')


def dropped_tab(user):
    """The Dropped tab: the series this account dropped, the one dropped last first."""
    entries = DroppedSeries.objects.filter(user=user).select_related('title').order_by('-dropped_at', '-id')
    return [entry.title for entry in entries]


def progress_by_series(user, series_ids, today):
    """How far this account is in each of the given series, as {series id: (watched, aired)}.

    `aired` counts the episodes that have aired (on or before `today`, the account's own day) and
    `watched` counts those of them the account has watched. Specials (season 0) are left out, and so
    are episodes that have not aired or have no date. Rule 2 of the design rules: an episode counts as
    watched if it has at least one watch, so a rewatch counts once.
    """
    series_ids = list(series_ids)
    aired = dict(
        Episode.objects.filter(title__in=series_ids, season_number__gt=0, air_date__lte=today)
        .values('title')
        .annotate(count=Count('id'))
        .values_list('title', 'count')
    )
    watched = dict(
        Watch.objects.filter(
            user=user, title__in=series_ids, episode__season_number__gt=0, episode__air_date__lte=today
        )
        .values('title')
        .annotate(count=Count('episode', distinct=True))
        .values_list('title', 'count')
    )
    return {series_id: (watched.get(series_id, 0), aired.get(series_id, 0)) for series_id in series_ids}


def series_tabs(user, today):
    """The series this account has started, as two lists of series: (watching, finished).

    Both are worked out from the account's watches and TMDB's status each time, so un-marking an
    episode moves a series back by itself. The most recently marked series come first.

    A series is finished when TMDB says it ended or was cancelled **and** every episode that has
    aired (on or before `today`, the account's own day) is watched. Specials (season 0) do not have
    to be watched, and episodes that have not aired or have no date do not count. Every other
    started series is watching, including one that is caught up but still running. A dropped series is in
    neither list: Dropped wins over the other tabs (its watches are not touched).
    """
    marked = Watch.objects.filter(user=user, episode__isnull=False).exclude(title__in=dropped_series(user))
    last_marked = dict(
        marked.values('title').annotate(last=Max('created_at')).values_list('title', 'last')
    )
    if not last_marked:
        return [], []

    progress = progress_by_series(user, last_marked, today)
    series_by_id = Title.objects.in_bulk(last_marked)

    watching, finished = [], []
    for series_id in sorted(last_marked, key=last_marked.get, reverse=True):
        series = series_by_id[series_id]
        watched, aired = progress[series_id]
        all_watched = aired > 0 and watched >= aired
        (finished if series.status in ENDED_STATUSES and all_watched else watching).append(series)
    return watching, finished


def up_next(user, today):
    """What to watch next: one entry for each series in Watching that has an episode left to watch.

    The next episode is the first one, in the order the series page lists them (season, then episode
    number), that has aired (on or before `today`, the account's own day) and that the account has not
    watched. Specials (season 0) and episodes that have not aired or have no date are never next. A
    series with no such episode (caught up, or nothing aired yet) has no entry until one airs.

    Each entry is a dict: `series`, `episode` (the next one), `watched` and `aired` (its progress).
    The most recently marked series come first, like the Watching tab.
    """
    watching, _ = series_tabs(user, today)
    unwatched = (
        Episode.objects.filter(title__in=watching, season_number__gt=0, air_date__lte=today)
        .exclude(watch__user=user)
        .order_by('title', 'season_number', 'episode_number', 'id')
    )
    next_episode = {}
    for episode in unwatched:
        next_episode.setdefault(episode.title_id, episode)

    progress = progress_by_series(user, next_episode, today)
    return [
        {
            'series': series,
            'episode': next_episode[series.id],
            'watched': progress[series.id][0],
            'aired': progress[series.id][1],
        }
        for series in watching
        if series.id in next_episode
    ]
