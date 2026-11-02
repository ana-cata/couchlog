"""The movies and series suggested on the Search page while the search box is empty.

They are picked from what an account has watched or saved: its most-watched genres, asked from TMDB, with TMDB's
trending list filling up what is missing. What is left over from those lists is kept as spares, to replace a suggestion
once it is added. Nothing is saved, and nothing here changes any data.
"""

from django.db.models import Q

from . import tmdb
from .models import DroppedSeries, Title, ToWatchItem, Watch

# How many titles are suggested for movies, and as many for series.
HOW_MANY = 10
# How many of the account's genres the suggestions are picked from.
TOP_GENRES = 3


def _watched_or_on_list(user, kind):
    """The titles of this kind that the account has watched (at least one watch) or has on its To Watch list now."""
    watched = Watch.objects.filter(user=user).values('title')
    on_list = ToWatchItem.objects.filter(user=user, removed_at=None).values('title')
    return Title.objects.filter(Q(id__in=watched) | Q(id__in=on_list), kind=kind)


def top_genres(user, kind):
    """TMDB's numbers for the (up to 3) genres that most of the account's titles of this kind have.

    Each title counts once for each of its genres, however many times it was watched. A tie goes to the lower number.
    A title saved before genres were kept has none, so it counts for nothing.
    """
    counts = {}
    for genres in _watched_or_on_list(user, kind).values_list('genres', flat=True):
        for genre in genres:
            counts[genre['id']] = counts.get(genre['id'], 0) + 1
    ranked = sorted(counts, key=lambda genre_id: (-counts[genre_id], genre_id))
    return ranked[:TOP_GENRES]


def _left_out(user, kind):
    """TMDB's ids of the titles of this kind that are never suggested: watched, on To Watch, or a dropped series."""
    dropped = Title.objects.filter(kind=kind, id__in=DroppedSeries.objects.filter(user=user).values('title'))
    return set(_watched_or_on_list(user, kind).values_list('tmdb_id', flat=True)) | set(
        dropped.values_list('tmdb_id', flat=True)
    )


def suggest(user, kind):
    """The titles of this kind for this account, shaped like search results, as `(shown, spares)`.
    Raises `tmdb.TmdbError`.

    `shown` is up to 10 titles: first the popular titles in the account's top genres, then (when fewer than 10 are
    left, or it has no genres yet) this week's trending titles. `spares` is whatever else those same lists held, in the
    same order: the page keeps them out of sight to replace a suggestion once it is added. No extra TMDB call is made
    for them. A title is suggested once, and never when it is left out (see `_left_out`).
    """
    taken = _left_out(user, kind)
    found = []

    def take(candidates):
        for candidate in candidates:
            if candidate['tmdb_id'] not in taken:
                found.append(candidate)
                taken.add(candidate['tmdb_id'])

    genre_ids = top_genres(user, kind)
    if genre_ids:
        take(tmdb.discover(kind, genre_ids))
    if len(found) < HOW_MANY:
        take(tmdb.trending(kind))
    return found[:HOW_MANY], found[HOW_MANY:]
