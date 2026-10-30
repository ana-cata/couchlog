"""The calendar, apart from the screen: collecting a movie's dates and a series' extra upcoming episodes, and what
is coming up for an account.

A series' own episodes and air dates are saved by `refresh_episodes` (core/episodes.py). TVmaze is the second
source, for the upcoming episodes TMDB does not list yet (`refresh_upcoming` below).
"""

import datetime

from django.db import transaction
from django.utils import timezone

from . import tmdb, tvmaze
from .episodes import dropped_series, series_tabs
from .models import Episode, Title, ToWatchItem, UpcomingEpisode


def refresh_movie(movie):
    """Ask TMDB for the movie's cinema and streaming dates and save them (an empty one when TMDB has none).

    TMDB is asked first, so when it fails (it raises `tmdb.TmdbError`) nothing is saved.
    """
    releases = tmdb.get_movie_releases(movie.tmdb_id)
    movie.cinema_at, movie.streaming_at = releases['cinema'], releases['streaming']
    movie.save(update_fields=['cinema_at', 'streaming_at'])


def refresh_upcoming(series):
    """Ask TVmaze for the series' upcoming episodes and save them, replacing the ones saved before.

    The series is found on TVmaze by the IMDb id `refresh_episodes` saved (so that has to have run), and TVmaze's
    id for it is remembered. A series with no IMDb id, or that TVmaze does not know, ends up with no rows. TVmaze
    is asked first, so when it fails (it raises `tvmaze.TvmazeError`) nothing is changed.

    Only episodes from yesterday on (UTC) are kept: the day of margin covers every time zone, and the Calendar
    leaves out what has passed in the account's own day anyway.
    """
    show_id = series.tvmaze_id
    if show_id is None and series.imdb_id:
        show_id = tvmaze.find_show_id(series.imdb_id)
    since = timezone.now().date() - datetime.timedelta(days=1)
    try:
        episodes = tvmaze.get_upcoming_episodes(show_id, since) if show_id else []
    except tvmaze.TvmazeNotFound:
        show_id, episodes = None, []  # the id remembered earlier is gone

    with transaction.atomic():
        series.upcoming_episodes.all().delete()
        UpcomingEpisode.objects.bulk_create([UpcomingEpisode(title=series, **episode) for episode in episodes])
        series.tvmaze_id = show_id
        series.save(update_fields=['tvmaze_id'])


def _episodes_text(episodes):
    """What a series' episodes of one day are called: 'S2E4 · Name', or 'S2E1–E8 · 8 episodes' for several."""
    first, last = episodes[0], episodes[-1]
    if len(episodes) == 1:
        return f'S{first.season_number}E{first.episode_number} · {first.name or "Untitled episode"}'
    if first.season_number == last.season_number:
        span = f'S{first.season_number}E{first.episode_number}–E{last.episode_number}'
    else:
        span = f'S{first.season_number}E{first.episode_number} – S{last.season_number}E{last.episode_number}'
    return f'{span} · {len(episodes)} episodes'


def upcoming(user, today, zone):
    """What this account is waiting for, from `today` on, as a list of days: [{'day': date, 'items': [...]}].

    The days are in order, and nothing in the past is here. The titles are the series in the Watching tab and
    the titles on the To Watch list, except dropped series. Each item is a dict: `title` and `text` (what is coming).
    - A series' episodes are on the air date TMDB gives, one item for each series and day (several episodes of
      the same day share it). Specials (season 0) and episodes with no air date are left out.
    - The upcoming episodes TVmaze lists are added on TVmaze's date, unless TMDB already has the episode: TMDB wins
      when it has an episode of the same season and number with a date (whichever date), or any episode of that
      series on the same day (which also covers an episode TMDB numbers differently). So each shows once.
    - A movie is on its cinema date ("In cinemas") and on its streaming date ("Streaming release"), each turned
      into a day in `zone` (the account's own time zone) like "today" is. A date TMDB does not have yet is not
      there, so a movie with neither is left out.
    """
    watching, _ = series_tabs(user, today)
    listed = Title.objects.filter(id__in=ToWatchItem.objects.filter(user=user, removed_at=None).values('title'))
    to_watch_series = listed.filter(kind='series').exclude(id__in=dropped_series(user))
    series_ids = {series.id for series in watching} | set(to_watch_series.values_list('id', flat=True))

    days = {}
    episodes_of_day = {}
    coming = (
        Episode.objects.filter(title__in=series_ids, season_number__gt=0, air_date__gte=today)
        .select_related('title')
        .order_by('air_date', 'title_id', 'season_number', 'episode_number', 'id')
    )
    for episode in coming:
        episodes_of_day.setdefault((episode.air_date, episode.title), []).append(episode)

    # What TVmaze adds. Days TMDB has are worked out first, so two TVmaze episodes of one day do not hide each other.
    tmdb_days = set(episodes_of_day)
    from_tvmaze = list(
        UpcomingEpisode.objects.filter(title__in=series_ids, air_date__gte=today)
        .select_related('title')
        .order_by('air_date', 'title_id', 'season_number', 'episode_number', 'id')
    )
    tmdb_numbers = set(
        Episode.objects.filter(
            title__in={episode.title_id for episode in from_tvmaze}, season_number__gt=0, air_date__isnull=False
        ).values_list('title', 'season_number', 'episode_number')
    )
    for episode in from_tvmaze:
        if (episode.title_id, episode.season_number, episode.episode_number) in tmdb_numbers:
            continue
        if (episode.air_date, episode.title) in tmdb_days:
            continue
        episodes_of_day.setdefault((episode.air_date, episode.title), []).append(episode)

    for (day, series), episodes in episodes_of_day.items():
        days.setdefault(day, []).append({'title': series, 'text': _episodes_text(episodes)})

    for movie in listed.filter(kind='movie'):
        for moment, text in ((movie.cinema_at, 'In cinemas'), (movie.streaming_at, 'Streaming release')):
            if moment is None:
                continue
            day = moment.astimezone(zone).date()
            if day >= today:
                days.setdefault(day, []).append({'title': movie, 'text': text})

    return [
        {'day': day, 'items': sorted(days[day], key=lambda item: (item['title'].title.lower(), item['text']))}
        for day in sorted(days)
    ]
