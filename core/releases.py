"""The calendar, apart from the screen: collecting a movie's streaming date, and what is coming up for an account.

Series need nothing of their own here: their episodes and air dates are saved by `refresh_episodes` (core/episodes.py).
"""

from . import tmdb
from .episodes import series_tabs
from .models import Episode, Title, ToWatchItem


def refresh_movie(movie):
    """Ask TMDB for the movie's cinema and streaming dates and save them (an empty one when TMDB has none).

    TMDB is asked first, so when it fails (it raises `tmdb.TmdbError`) nothing is saved.
    """
    releases = tmdb.get_movie_releases(movie.tmdb_id)
    movie.cinema_at, movie.streaming_at = releases['cinema'], releases['streaming']
    movie.save(update_fields=['cinema_at', 'streaming_at'])


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
    the titles on the To Watch list. Each item is a dict: `title` and `text` (what is coming).
    - A series' episodes are on the air date TMDB gives, one item for each series and day (several episodes of
      the same day share it). Specials (season 0) and episodes with no air date are left out.
    - A movie is on its cinema date ("In cinemas") and on its streaming date ("Streaming release"), each turned
      into a day in `zone` (the account's own time zone) like "today" is. A date TMDB does not have yet is not
      there, so a movie with neither is left out.
    """
    watching, _ = series_tabs(user, today)
    listed = Title.objects.filter(id__in=ToWatchItem.objects.filter(user=user, removed_at=None).values('title'))
    series_ids = {series.id for series in watching} | set(listed.filter(kind='series').values_list('id', flat=True))

    days = {}
    episodes_of_day = {}
    coming = (
        Episode.objects.filter(title__in=series_ids, season_number__gt=0, air_date__gte=today)
        .select_related('title')
        .order_by('air_date', 'title_id', 'season_number', 'episode_number', 'id')
    )
    for episode in coming:
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
