"""Time spent watching: the minutes worked out from an account's watches (a movie's runtime, an episode's own runtime
or else its series' typical one), how they are shown on the Profile page, and how the runtimes are saved.

Every watch counts, rewatches too; taking a watch back takes its minutes off; nothing is stored for the total."""

import datetime
import re

import pytest
import time_machine
from django.contrib.auth.models import User
from django.test import Client

from core.episodes import typical_runtime
from core.models import Episode, Profile, Title, ToWatchItem, Watch
from core.time_spent import describe, minutes_watched

MOVIE_URL = 'https://api.themoviedb.org/3/movie/603'
SERIES_URL = 'https://api.themoviedb.org/3/tv/1399'
SERIES_PAGE = '/series/1399/'

MADE_UP_MOVIE = {
    'id': 603,
    'title': 'Made-up Movie',
    'release_date': '1999-03-31',
    'poster_path': '/made-up-movie.jpg',
    'overview': 'A made-up story about a movie.',
    'runtime': 100,
}
MADE_UP_SERIES = {
    'id': 1399,
    'name': 'Made-up Series',
    'first_air_date': '2011-04-17',
    'poster_path': '/made-up-series.jpg',
    'overview': 'A made-up story about a series.',
    'status': 'Returning Series',
    'seasons': [{'season_number': 0}, {'season_number': 1}, {'season_number': 2}],
}


def made_up_episode(season, number, tmdb_id, air_date, runtime):
    return {
        'id': tmdb_id,
        'season_number': season,
        'episode_number': number,
        'name': f'Made-up episode {season}x{number}',
        'air_date': air_date,
        'runtime': runtime,
    }


# The special has a runtime but is left out of the average. 6003 has none of its own. The regular episodes that
# have a runtime are 60, 30 and 90 minutes, so the typical episode is 60.
SEASONS = {
    0: [made_up_episode(0, 1, 6000, '2010-01-01', 20)],
    1: [
        made_up_episode(1, 1, 6001, '2011-04-17', 60),
        made_up_episode(1, 2, 6002, '2011-04-24', 30),
        made_up_episode(1, 3, 6003, '2011-05-01', None),
    ],
    2: [
        made_up_episode(2, 1, 6101, '2011-05-08', 90),
        made_up_episode(2, 2, 6102, '2999-01-01', None),
    ],
}

# The fixed "now" for every test here: 8 pm UTC on 28 Oct 2026.
NOW = datetime.datetime(2026, 10, 28, 20, 0, tzinfo=datetime.UTC)


@pytest.fixture(autouse=True)
def tmdb_key(settings):
    settings.TMDB_API_KEY = 'made-up-secret-key'


@pytest.fixture(autouse=True)
def clock():
    with time_machine.travel(NOW, tick=False) as traveller:
        yield traveller


def make_client(name, zone='Europe/Lisbon'):
    """A browser logged in as a new account (with a time zone chosen, so no redirect to Profile)."""
    user = User.objects.create_user(username=name, password='made-up-password')
    Profile.objects.create(user=user, timezone=zone)
    client = Client()
    client.force_login(user)
    client.user = user
    return client


@pytest.fixture
def logged_in_client(db):
    return make_client('made-up-user')


@pytest.fixture
def movie_route(respx_mock):
    return respx_mock.get(MOVIE_URL).respond(json=MADE_UP_MOVIE)


@pytest.fixture
def opened(logged_in_client, respx_mock):
    """The account, with the made-up series opened once so its episodes and typical runtime are saved."""
    respx_mock.get(SERIES_URL).respond(json=MADE_UP_SERIES)
    # By season number, so a test can change one season's answer.
    logged_in_client.routes = {
        number: respx_mock.get(f'{SERIES_URL}/season/{number}').respond(
            json={'season_number': number, 'episodes': episodes}
        )
        for number, episodes in SEASONS.items()
    }
    logged_in_client.get(SERIES_PAGE)
    return logged_in_client


def mark_film(client, watched_on='2026-10-28', **extra):
    """The first mark of the film and "Watch again": the same button."""
    return client.post('/watched/add/', {'kind': 'movie', 'tmdb_id': 603, 'watched_on': watched_on, **extra})


def remove_watch(client, watch_id):
    return client.post('/watched/remove/', {'watch_id': watch_id})


def eid(tmdb_id):
    return Episode.objects.get(tmdb_id=tmdb_id).id


def press_circle(client, tmdb_id):
    """The first mark of an episode, as "No, only this one" makes it (so there is never a question)."""
    return client.post('/watched/episode/add/', {'episode_id': eid(tmdb_id), 'only_this': 1})


def watch_again(client, tmdb_id):
    """The round check button of an episode that is already marked: it counts another watch."""
    return client.post('/watched/episode/add/', {'episode_id': eid(tmdb_id)})


def minus(client, tmdb_id):
    """The "−" of an episode's row: takes back its latest watch."""
    watch = Watch.objects.filter(user=client.user, episode__tmdb_id=tmdb_id).order_by('created_at', 'id').last()
    return client.post('/watched/remove/', {'watch_id': watch.id, 'episode_id': watch.episode_id})


def season_post(client, address, number):
    return client.post(address, {'tmdb_id': 1399, 'season': number, 'next': SERIES_PAGE})


def minutes(client):
    """(movies, series) minutes of the account."""
    return minutes_watched(client.user)


def profile_shows(client):
    """What the Profile page says about the time spent: (movies, series, total), as words."""
    html = client.get('/profile/').content.decode()
    texts = [re.sub(r'<.*?>', '', text) for text in re.findall(r'<dd>(.*?)</dd>', html)]
    return tuple(texts)


def watch_snapshot():
    return list(Watch.objects.order_by('id').values())


# --- a movie ----------------------------------------------------------------------------------


def test_a_100_minute_film_marked_once_is_100_minutes(logged_in_client, movie_route):
    mark_film(logged_in_client)

    assert minutes(logged_in_client) == (100, 0)
    assert Title.objects.get().runtime == 100  # saved from TMDB with the title (design rule 6)


def test_each_watch_again_adds_the_runtime_once_more(logged_in_client, movie_route):
    mark_film(logged_in_client, watched_on='2026-05-01')

    for _ in range(3):
        mark_film(logged_in_client, watched_on='2026-06-01')

    assert minutes(logged_in_client) == (400, 0)  # 100 for the first watch and 300 for the three more


def test_a_watch_with_an_unknown_date_counts_too(logged_in_client, movie_route):
    mark_film(logged_in_client, date_unknown='on')

    assert minutes(logged_in_client) == (100, 0)


def test_taking_a_watch_back_takes_its_minutes_off_again(logged_in_client, movie_route):
    before = watch_snapshot()
    mark_film(logged_in_client, watched_on='2026-05-01')
    mark_film(logged_in_client, watched_on='2026-06-01')
    mark_film(logged_in_client, watched_on='2026-07-01')
    first, second, third = Watch.objects.order_by('id').values_list('id', flat=True)

    remove_watch(logged_in_client, second)
    assert minutes(logged_in_client) == (200, 0)  # only that watch left, and only its 100 minutes
    remove_watch(logged_in_client, third)
    remove_watch(logged_in_client, first)

    assert minutes(logged_in_client) == (0, 0)
    assert watch_snapshot() == before


def test_a_film_with_no_runtime_on_tmdb_counts_as_zero_minutes(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_URL).respond(json={key: value for key, value in MADE_UP_MOVIE.items() if key != 'runtime'})

    mark_film(logged_in_client)

    assert Title.objects.get().runtime is None
    assert minutes(logged_in_client) == (0, 0)


def test_a_film_saved_before_runtimes_were_kept_counts_zero_until_it_is_refreshed(logged_in_client):
    film = Title.objects.create(kind='movie', tmdb_id=603, title='Made-up Movie', year='1999')
    Watch.objects.create(user=logged_in_client.user, title=film, watched_on=datetime.date(2026, 5, 1))

    assert minutes(logged_in_client) == (0, 0)

    film.runtime = 100  # what `refresh_calendar` saves (see test_refresh_calendar.py)
    film.save()
    assert minutes(logged_in_client) == (100, 0)


# --- episodes and seasons -------------------------------------------------------------------------


def test_an_episode_counts_its_own_runtime_and_twice_when_pressed_twice(opened):
    press_circle(opened, 6001)
    assert minutes(opened) == (0, 60)

    watch_again(opened, 6001)  # the green circle again: watched twice

    assert minutes(opened) == (0, 120)


def test_the_minus_takes_one_watch_and_its_minutes_off(opened):
    before = watch_snapshot()
    press_circle(opened, 6001)
    watch_again(opened, 6001)

    minus(opened, 6001)
    assert minutes(opened) == (0, 60)
    minus(opened, 6001)

    assert minutes(opened) == (0, 0) and watch_snapshot() == before


def test_an_episode_with_no_runtime_uses_the_series_typical_one(opened):
    assert Title.objects.get().runtime == 60  # the average of 60, 30 and 90 (not the special, not the empty ones)

    press_circle(opened, 6003)  # no runtime of its own

    assert minutes(opened) == (0, 60)


def test_a_series_with_no_runtime_for_any_episode_counts_zero(opened):
    Episode.objects.update(runtime=None)
    Title.objects.update(runtime=None)

    press_circle(opened, 6001)

    assert minutes(opened) == (0, 0)


def test_a_special_counts_its_own_runtime_but_not_in_the_average(opened):
    press_circle(opened, 6000)

    assert minutes(opened) == (0, 20)
    assert Title.objects.get().runtime == 60


def test_a_season_watched_again_adds_the_minutes_of_every_aired_episode(opened):
    season_post(opened, '/watched/season/add/', 1)
    assert minutes(opened) == (0, 60 + 30 + 60)  # the third one uses the typical 60

    season_post(opened, '/watched/season/again/', 1)

    assert minutes(opened) == (0, 2 * 150)
    season_post(opened, '/watched/season/again/', 1)
    assert minutes(opened) == (0, 3 * 150)


def test_taking_back_a_season_rewatch_takes_exactly_its_minutes_off(opened):
    season_post(opened, '/watched/season/add/', 1)
    before = watch_snapshot()
    season_post(opened, '/watched/season/again/', 1)

    season_post(opened, '/watched/season/again/remove/', 1)

    assert minutes(opened) == (0, 150)
    assert watch_snapshot() == before


def test_marking_a_season_as_not_watched_takes_all_its_minutes_off(opened):
    before = watch_snapshot()
    season_post(opened, '/watched/season/add/', 1)
    season_post(opened, '/watched/season/again/', 1)

    season_post(opened, '/watched/season/remove/', 1)

    assert minutes(opened) == (0, 0) and watch_snapshot() == before


def test_an_episode_that_has_not_aired_adds_nothing(opened):
    press_circle(opened, 6102)  # airs in 2999: it cannot be marked

    assert minutes(opened) == (0, 0)


# --- movies and series together, and whose watches count -----------------------------------------


def test_movies_and_series_are_counted_apart_and_added_for_the_total(opened, movie_route):
    mark_film(opened)
    press_circle(opened, 6001)

    assert minutes(opened) == (100, 60)
    assert profile_shows(opened) == ('1 hour 40 minutes', '1 hour', '2 hours 40 minutes')


def test_only_my_own_watches_count(opened, movie_route):
    other = make_client('second-user')
    mark_film(opened)
    press_circle(opened, 6001)
    mark_film(other)
    mark_film(other)
    press_circle(other, 6002)

    assert minutes(opened) == (100, 60)
    assert minutes(other) == (200, 30)
    remove_watch(opened, Watch.objects.filter(user=opened.user, episode=None).get().id)  # mine only
    assert minutes(opened) == (0, 60) and minutes(other) == (200, 30)


# --- the Profile page -------------------------------------------------------------------------------


def test_the_profile_page_starts_at_zero(logged_in_client):
    assert profile_shows(logged_in_client) == ('0 minutes', '0 minutes', '0 minutes')


def test_the_profile_page_follows_every_watch_and_every_undo(logged_in_client, movie_route):
    mark_film(logged_in_client, watched_on='2026-05-01')
    assert profile_shows(logged_in_client)[0] == '1 hour 40 minutes'  # 100 minutes

    mark_film(logged_in_client, watched_on='2026-06-01')
    assert profile_shows(logged_in_client)[0] == '3 hours 20 minutes'

    remove_watch(logged_in_client, Watch.objects.order_by('-id').first().id)
    assert profile_shows(logged_in_client)[0] == '1 hour 40 minutes'


def test_the_profile_page_never_asks_tmdb(logged_in_client, movie_route):
    mark_film(logged_in_client)
    calls_before = movie_route.call_count

    logged_in_client.get('/profile/')

    assert movie_route.call_count == calls_before  # it works from what is saved (design rule 6)


def test_the_profile_page_still_saves_the_time_zone(logged_in_client):
    response = logged_in_client.post('/profile/', {'timezone': 'Europe/Paris'})

    assert response.status_code == 302 and Profile.objects.get().timezone == 'Europe/Paris'


# --- saying it in words -------------------------------------------------------------------------------

DAY = 24 * 60


@pytest.mark.parametrize(
    ('minutes_', 'words'),
    [
        (0, '0 minutes'),
        (1, '1 minute'),
        (59, '59 minutes'),
        (60, '1 hour'),
        (100, '1 hour 40 minutes'),
        (DAY, '1 day'),
        (DAY + 61, '1 day 1 hour 1 minute'),
        (30 * DAY, '1 month'),
        (30 * DAY - 1, '29 days 23 hours 59 minutes'),
        (365 * DAY, '1 year'),
        (365 * DAY + 2 * 30 * DAY + 3 * DAY + 4 * 60, '1 year 2 months 3 days 4 hours'),
        (3 * 365 * DAY + 30 * DAY + 5, '3 years 1 month 5 minutes'),
    ],
)
def test_the_time_is_said_in_years_months_days_hours_and_minutes(minutes_, words):
    assert describe(minutes_) == words


# --- the runtimes are saved ---------------------------------------------------------------------------


def test_the_typical_runtime_is_the_average_of_the_episodes_that_have_one():
    episodes = [
        {'season_number': 1, 'runtime': 40},
        {'season_number': 1, 'runtime': 45},
        {'season_number': 2, 'runtime': 45},
        {'season_number': 2, 'runtime': None},  # no runtime: left out
        {'season_number': 0, 'runtime': 200},  # a special: left out
    ]

    assert typical_runtime(episodes) == 43  # 130 / 3 = 43.3, a whole minute
    assert typical_runtime([{'season_number': 1, 'runtime': None}]) is None
    assert typical_runtime([]) is None


def test_a_new_episode_changes_the_typical_runtime_when_the_series_is_refreshed(opened):
    assert Title.objects.get().runtime == 60
    opened.routes[2].respond(
        json={'season_number': 2, 'episodes': [*SEASONS[2], made_up_episode(2, 3, 6103, '2011-05-22', 120)]}
    )
    Title.objects.update(episodes_refreshed_at=NOW - datetime.timedelta(days=3))  # the saved copy is old

    opened.get(SERIES_PAGE)

    assert Title.objects.get().runtime == 75  # (60 + 30 + 90 + 120) / 4


def test_adding_a_film_to_to_watch_saves_its_runtime_too(logged_in_client, movie_route):
    logged_in_client.post('/to-watch/add/', {'kind': 'movie', 'tmdb_id': 603})

    assert Title.objects.get().runtime == 100
    assert ToWatchItem.objects.count() == 1


def test_the_profile_page_needs_a_login(db):
    response = Client().get('/profile/')

    assert response.status_code == 302 and response['Location'].startswith('/login/')
