"""Time spent watching, apart from the screen: worked out from an account's watches each time, so nothing is stored
and taking a watch back takes its minutes off by itself."""

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
