"""The public demo: throwaway accounts filled with sample titles, and the limits that keep the free services free.

Only used when the setting DEMO_MODE is on, which is only in the demo's own copy on Render (docs/demo.md). With it off,
nothing here runs. The limits are counted with `DemoEvent` rows over the last hour or the last 24 hours.
"""

import datetime
import secrets
from functools import wraps
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import User
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from . import tmdb
from .episodes import refresh_episodes
from .forms import timezone_names
from .models import DemoEvent, Episode, Profile, Title, ToWatchItem, Watch
from .releases import refresh_movie

# Every demo account's username starts with this, and only those accounts are ever deleted.
USERNAME_PREFIX = 'demo-'
# How long a demo account lives. Older ones are deleted when a new one starts.
ACCOUNT_LIFETIME = datetime.timedelta(hours=24)
AN_HOUR = datetime.timedelta(hours=1)
A_DAY = datetime.timedelta(hours=24)
# How old the saved episodes of a sample series may be before a new account asks TMDB again.
EPISODES_REFRESH_AFTER = datetime.timedelta(days=1)

# The sample titles, as TMDB ids. Only the ids are in the code: their details are asked from TMDB when the demo needs
# them, and saved in the demo's own database. Chosen on card #98; the series still airing keep the Calendar from
# being empty, so when they stop airing, swap them for others that air (docs/demo.md).
# Movies watched, with how many days ago (None: date unknown).
WATCHED_MOVIES = [(278, 2), (129, 9), (496243, None)]  # The Shawshank Redemption, Spirited Away, Parasite
# Movies on the To Watch list. Dune: Part Three (December 2026) and Black Panther 3 (December 2028) have cinema dates
# ahead, so the Calendar has a film for a long time.
TO_WATCH_MOVIES = [666277, 1170608, 1386618]  # Past Lives, Dune: Part Three, Black Panther 3
# Series with episodes watched: (TMDB id, how many episodes from the start, None for every aired one, how many days
# ago the last of them was watched). One a day before that, going back.
STARTED_SERIES = [
    (67070, None, 20),  # Fleabag: every episode, and it ended, so it is Finished
    (95396, 4, 3),  # Severance: halfway through season 1
    (153312, 3, 1),  # Tulsa King: still airing, so the Calendar has its new episodes
]
# Series on the To Watch list.
TO_WATCH_SERIES = [87108, 84773]  # Chernobyl, The Lord of the Rings: The Rings of Power (still airing)

SEARCH_LIMIT = 'The demo allows {limit} searches an hour. Try again a little later.'
CHANGE_LIMIT = (
    'The demo allows {limit} changes a day, and this visit has used them all, so nothing was saved. '
    'Undo and the buttons that take something back still work.'
)
TMDB_LIMIT = 'The demo has asked TMDB as often as it may this hour. Try again later.'
DEMO_FULL = 'The demo is full for today. Try again tomorrow.'
SAMPLES_UNREACHABLE = 'The demo could not load its sample titles from TMDB. Try again in a minute.'


class DemoFull(Exception):
    """The whole demo has made as many accounts as it may in a day."""


def context(request):
    """What every page needs to know about the demo: whether it is one, and where the code is."""
    return {'demo_mode': settings.DEMO_MODE, 'demo_repo_url': settings.DEMO_REPO_URL}


def _count(kind, within, user=None):
    """How many times `kind` happened in the last `within`, for one account or (with no user) for the whole demo."""
    events = DemoEvent.objects.filter(kind=kind, at__gte=timezone.now() - within)
    if user is not None:
        events = events.filter(user=user)
    return events.count()


def _use(kind, within, limit, user=None):
    """Count one more `kind`, unless the limit is reached: then count nothing and return False."""
    if _count(kind, within, user) >= limit:
        return False
    DemoEvent.objects.create(kind=kind, user=user)
    return True


def use_tmdb_request():
    """Called before every request to TMDB in the demo (core/tmdb.py). Refuses it past the hourly limit."""
    if not _use(DemoEvent.Kind.TMDB, AN_HOUR, settings.DEMO_TMDB_REQUESTS_PER_HOUR):
        raise tmdb.TmdbError(TMDB_LIMIT)


def search_refused(user):
    """Why this visitor's search is refused, or '' when it is allowed (it is then counted). Always '' outside the demo."""
    if not settings.DEMO_MODE:
        return ''
    limit = settings.DEMO_SEARCHES_PER_HOUR
    return '' if _use(DemoEvent.Kind.SEARCH, AN_HOUR, limit, user) else SEARCH_LIMIT.format(limit=limit)


def counts_as_change(view):
    """Marks a button that adds something. In the demo it counts toward the visitor's daily changes and, past the
    limit, is refused with a friendly message and saves nothing. Outside the demo it does nothing.

    Buttons that take something back (Undo, Remove, Mark as not watched, the − buttons, Bring back) are never marked,
    so they are never counted or refused (design rule 5).
    """

    @wraps(view)
    def checked(request, *args, **kwargs):
        if settings.DEMO_MODE:
            limit = settings.DEMO_CHANGES_PER_DAY
            if not _use(DemoEvent.Kind.CHANGE, A_DAY, limit, request.user):
                return _refused(request, CHANGE_LIMIT.format(limit=limit))
        return view(request, *args, **kwargs)

    return checked


def _refused(request, text):
    """The answer to a refused button. With htmx, the text in the line under the header bar (problems.js shows the
    text of a 429 answer); without it, back to the page with the text as a message."""
    if request.headers.get('HX-Request'):
        return HttpResponse(text, status=429, content_type='text/plain; charset=utf-8')
    messages.error(request, text)
    next_url = request.POST.get('next', '')
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = reverse('home')
    return redirect(next_url)


def is_full():
    """Whether the demo has made as many accounts as it may in the last 24 hours."""
    return _count(DemoEvent.Kind.ACCOUNT, A_DAY) >= settings.DEMO_ACCOUNTS_PER_DAY


def delete_old_accounts():
    """Delete the demo accounts older than a day, with everything in them, and the limit counts older than a day.

    The saved titles stay: they are shared and not anyone's data.
    """
    too_old = timezone.now() - ACCOUNT_LIFETIME
    User.objects.filter(username__startswith=USERNAME_PREFIX, date_joined__lt=too_old).delete()
    DemoEvent.objects.filter(at__lt=too_old).delete()


def _saved_title(kind, tmdb_id):
    """Our saved copy of a sample title, asked from TMDB the first time."""
    title = Title.objects.filter(kind=kind, tmdb_id=tmdb_id).first()
    if title is None:
        details = tmdb.get_title(kind, tmdb_id)
        keys = ('title', 'year', 'poster_url', 'backdrop_url', 'overview', 'runtime', 'genres')
        title, _ = Title.objects.get_or_create(kind=kind, tmdb_id=tmdb_id, defaults={key: details[key] for key in keys})
    return title


def sample_titles():
    """Every sample title, saved with what the pages and the Calendar need. TMDB is only asked for what is missing, so
    after the first account the demo works from its own copy (raises `tmdb.TmdbError` when TMDB fails).

    Returns {(kind, tmdb_id): Title}.
    """
    titles = {}
    for tmdb_id, *_ in WATCHED_MOVIES:
        titles['movie', tmdb_id] = _saved_title('movie', tmdb_id)
    for tmdb_id in TO_WATCH_MOVIES:
        movie = titles['movie', tmdb_id] = _saved_title('movie', tmdb_id)
        if movie.cinema_at is None and movie.streaming_at is None:
            refresh_movie(movie)
    for tmdb_id in [tmdb_id for tmdb_id, *_ in STARTED_SERIES] + TO_WATCH_SERIES:
        series = titles['series', tmdb_id] = _saved_title('series', tmdb_id)
        refreshed = series.episodes_refreshed_at
        if refreshed is None or refreshed < timezone.now() - EPISODES_REFRESH_AFTER:
            refresh_episodes(series)
    return titles


def _add_sample_data(user, titles, today):
    """Give a new account its sample watches and To Watch list, dated from `today` (in its own time zone)."""
    for tmdb_id, days_ago in WATCHED_MOVIES:
        watched_on = None if days_ago is None else today - datetime.timedelta(days=days_ago)
        Watch.objects.create(user=user, title=titles['movie', tmdb_id], watched_on=watched_on)

    for tmdb_id, how_many, last_days_ago in STARTED_SERIES:
        series = titles['series', tmdb_id]
        aired = list(
            Episode.objects.filter(title=series, season_number__gt=0, air_date__lte=today).order_by(
                'season_number', 'episode_number', 'id'
            )
        )
        watched = aired if how_many is None else aired[:how_many]
        for number, episode in enumerate(watched):
            days_ago = last_days_ago + len(watched) - 1 - number
            Watch.objects.create(
                user=user, title=series, episode=episode, watched_on=today - datetime.timedelta(days=days_ago)
            )

    to_watch = [titles['movie', tmdb_id] for tmdb_id in TO_WATCH_MOVIES]
    to_watch += [titles['series', tmdb_id] for tmdb_id in TO_WATCH_SERIES]
    ToWatchItem.objects.bulk_create([ToWatchItem(user=user, title=title) for title in to_watch])


def start_account(time_zone):
    """A new throwaway account with the sample data, for one visitor. Raises `DemoFull` past the daily limit, and
    `tmdb.TmdbError` when the sample titles cannot be loaded; either way no account is made.

    The account has a random name, no usable password, and `time_zone` (the browser's, UTC if it is not a real one),
    so it skips the time zone step. Accounts older than a day are deleted first.
    """
    if is_full():
        raise DemoFull
    titles = sample_titles()
    if time_zone not in timezone_names():
        time_zone = 'UTC'
    today = timezone.now().astimezone(ZoneInfo(time_zone)).date()
    with transaction.atomic():
        delete_old_accounts()
        user = User.objects.create_user(username=USERNAME_PREFIX + secrets.token_hex(6))
        Profile.objects.create(user=user, timezone=time_zone)
        _add_sample_data(user, titles, today)
        DemoEvent.objects.create(kind=DemoEvent.Kind.ACCOUNT)
    return user
