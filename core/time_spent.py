"""Time spent watching, apart from the screen: worked out from an account's watches each time, so nothing is stored
and taking a watch back takes its minutes off by itself."""

from collections import Counter

from django.db.models import IntegerField, Sum, Value
from django.db.models.functions import Coalesce

from .models import Watch

# For the total as years, months, days, hours and minutes. It only has to give an idea, so a month is 30 days and a
# year is 365 days.
UNITS = (
    ('year', 365 * 24 * 60),
    ('month', 30 * 24 * 60),
    ('day', 24 * 60),
    ('hour', 60),
    ('minute', 1),
)

# The genre charts show this many genres, then one "Other" row with the rest and the titles that have no genre.
GENRES_SHOWN = 8
OTHER = 'Other'


def minutes_watched(user):
    """The minutes this account has spent watching, as (movies, series).

    Every watch counts its runtime (design rule 1): a movie watched 3 more times adds 3 runtimes, and an episode
    watched twice counts twice. An episode with no runtime of its own uses its series' typical episode runtime, and
    anything TMDB gave no runtime for counts as 0 minutes. Only this account's watches count.
    """
    zero = Value(0, output_field=IntegerField())
    movies = Watch.objects.filter(user=user, episode=None, title__kind='movie').aggregate(
        total=Sum(Coalesce('title__runtime', zero))
    )['total']
    series = Watch.objects.filter(user=user, episode__isnull=False).aggregate(
        total=Sum(Coalesce('episode__runtime', 'title__runtime', zero))
    )['total']
    return movies or 0, series or 0


def describe(minutes):
    """A number of minutes in words: '1 hour 40 minutes', '2 months 3 days 4 hours'. Units that are zero are left out,
    and nothing at all is '0 minutes'."""
    parts = []
    for name, size in UNITS:
        count, minutes = divmod(minutes, size)
        if count:
            parts.append(f'{count} {name}{"" if count == 1 else "s"}')
    return ' '.join(parts) or '0 minutes'


def minutes_by_genre(user):
    """The minutes this account has spent watching per genre, as (movies, series): each a list of (genre, minutes),
    from most to least, with at most GENRES_SHOWN genres and then ("Other", minutes) when anything is left.

    The minutes are counted like `minutes_watched`. A watch counts fully in each genre of its title, so a 2-hour
    Crime Drama adds 2 hours to Crime and 2 hours to Drama. A title with no genres saved counts in Other. A genre
    with 0 minutes is left out. Only this account's watches count.
    """
    zero = Value(0, output_field=IntegerField())
    movies = (
        Watch.objects.filter(user=user, episode=None, title__kind='movie')
        .annotate(minutes=Coalesce('title__runtime', zero))
        .values_list('minutes', 'title__genres')
    )
    series = (
        Watch.objects.filter(user=user, episode__isnull=False)
        .annotate(minutes=Coalesce('episode__runtime', 'title__runtime', zero))
        .values_list('minutes', 'title__genres')
    )
    return _ranked(movies), _ranked(series)


def _ranked(rows):
    """(minutes, genres) of each watch, as the ranked list `minutes_by_genre` describes."""
    totals = Counter()
    other = 0
    for minutes, genres in rows:
        if not minutes:
            continue
        names = {genre.get('name') for genre in genres or [] if genre.get('name')}
        if not names:
            other += minutes
        for name in names:
            totals[name] += minutes
    # Most minutes first; a tie in the order of the alphabet, so the page is the same each time.
    ranked = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    other += sum(minutes for _, minutes in ranked[GENRES_SHOWN:])
    ranked = ranked[:GENRES_SHOWN]
    if other:
        ranked.append((OTHER, other))
    return ranked


def short(minutes):
    """A number of minutes, short: '45 min' under an hour, else whole hours, rounded: '42 h'."""
    if minutes < 60:
        return f'{minutes} min'
    return f'{(minutes + 30) // 60} h'


def genre_chart(ranked):
    """The rows of one genre chart: the name, the time in short, and the bar's length in percent of the longest."""
    longest = max((minutes for _, minutes in ranked), default=0)
    return [
        {'name': name, 'time': short(minutes), 'percent': max(1, round(minutes * 100 / longest))}
        for name, minutes in ranked
    ]
