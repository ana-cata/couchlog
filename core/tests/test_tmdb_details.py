"""TMDB's terms allow keeping its details for at most 6 months: `refresh_calendar` asks again about every saved title,
followed or not, once its details are older than 5 months (core/details.py)."""

import datetime
import io

import httpx
import pytest
import time_machine
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError

from core.models import Episode, Profile, Title, ToWatchItem, Watch

TV_URL = 'https://api.themoviedb.org/3/tv/{}'
MOVIE_URL = 'https://api.themoviedb.org/3/movie/{}'

# A fixed "today", and details asked just over and just under 5 months before it.
NOW = datetime.datetime(2026, 11, 12, 10, 0, tzinfo=datetime.UTC)
OLD = NOW - datetime.timedelta(days=151)
RECENT = NOW - datetime.timedelta(days=149)

DRAMA = {'id': 18, 'name': 'Drama'}

# Made-up TMDB answers. The tests never call the real TMDB.


def movie_answer(tmdb_id):
    return {
        'id': tmdb_id,
        'title': 'New Movie Name',
        'release_date': '2010-07-16',
        'poster_path': '/new-poster.jpg',
        'backdrop_path': '/new-banner.jpg',
        'overview': 'The new summary.',
        'runtime': 148,
        'genres': [DRAMA],
        'release_dates': {
            'results': [
                {'iso_3166_1': 'US', 'release_dates': [{'type': 3, 'release_date': '2010-07-16T00:00:00.000Z', 'note': ''}]}
            ]
        },
    }


def series_answer(tmdb_id):
    return {
        'id': tmdb_id,
        'name': 'New Series Name',
        'first_air_date': '2019-02-15',
        'poster_path': '/new-series-poster.jpg',
        'backdrop_path': None,
        'overview': 'The new series summary.',
        'status': 'Ended',
        'seasons': [{'season_number': 1}],
        'genres': [DRAMA],
    }


def season_answer():
    episodes = [
        {'id': 2101, 'season_number': 1, 'episode_number': 1, 'name': 'Pilot', 'air_date': '2019-02-15', 'runtime': 50},
        {'id': 2102, 'season_number': 1, 'episode_number': 2, 'name': 'New Episode', 'air_date': '2019-02-22', 'runtime': 54},
    ]
    return {'season_number': 1, 'episodes': episodes}


@pytest.fixture(autouse=True)
def tmdb_key(settings):
    settings.TMDB_API_KEY = 'made-up-secret-key'


@pytest.fixture(autouse=True)
def clock():
    with time_machine.travel(NOW, tick=False):
        yield


@pytest.fixture
def user(db):
    return User.objects.create_user(username='made-up-user', password='made-up-password')


def make_movie(tmdb_id, refreshed_at):
    return Title.objects.create(
        kind='movie',
        tmdb_id=tmdb_id,
        title='Old Movie Name',
        year='2009',
        poster_url='https://image.tmdb.org/t/p/w342/old-poster.jpg',
        overview='The old summary.',
        runtime=140,
        genres=[DRAMA],
        details_refreshed_at=refreshed_at,
    )


def make_series(tmdb_id, refreshed_at):
    return Title.objects.create(
        kind='series', tmdb_id=tmdb_id, title='Old Series Name', overview='The old series summary.', details_refreshed_at=refreshed_at
    )


def mock_series(respx_mock, tmdb_id):
    route = respx_mock.get(TV_URL.format(tmdb_id)).respond(json=series_answer(tmdb_id))
    respx_mock.get(TV_URL.format(tmdb_id) + '/season/1').respond(json=season_answer())
    return route


def run():
    """Run the command. Returns what it printed, and what it said about problems."""
    out, err = io.StringIO(), io.StringIO()
    try:
        call_command('refresh_calendar', stdout=out, stderr=err)
    except CommandError as problem:
        err.write(str(problem))
    return out.getvalue(), err.getvalue()


def test_a_watched_movie_with_details_older_than_5_months_gets_all_of_them_again(user, respx_mock):
    movie = make_movie(27205, OLD)
    watch = Watch.objects.create(user=user, title=movie, watched_on=datetime.date(2026, 1, 3))
    respx_mock.get(MOVIE_URL.format(27205)).respond(json=movie_answer(27205))

    out, err = run()

    movie.refresh_from_db()
    assert (movie.title, movie.year, movie.overview, movie.runtime) == ('New Movie Name', '2010', 'The new summary.', 148)
    assert movie.poster_url == 'https://image.tmdb.org/t/p/w342/new-poster.jpg'
    assert movie.backdrop_url == 'https://image.tmdb.org/t/p/w780/new-banner.jpg'
    assert movie.cinema_at == datetime.datetime(2010, 7, 16, tzinfo=datetime.UTC)
    assert movie.details_refreshed_at == NOW
    assert '“New Movie Name”: details refreshed' in out
    assert 'Refreshed the details of 1 title.' in out
    assert err == ''
    # My watch is not touched: same row, same date.
    assert list(Watch.objects.values_list('id', 'title', 'watched_on')) == [(watch.id, movie.id, datetime.date(2026, 1, 3))]


def test_a_title_saved_before_the_date_was_kept_is_refreshed_once(user, respx_mock):
    movie = make_movie(27205, None)
    route = respx_mock.get(MOVIE_URL.format(27205)).respond(json=movie_answer(27205))

    run()
    run()

    movie.refresh_from_db()
    assert movie.title == 'New Movie Name'
    assert movie.details_refreshed_at == NOW
    # Two TMDB calls in the first run (its dates, then its details), none in the second.
    assert route.call_count == 2


def test_details_younger_than_5_months_are_left_alone(user, respx_mock):
    make_movie(27205, RECENT)
    make_series(1396, RECENT)

    out, _ = run()

    # No TMDB route is set up, so any call would fail the test.
    assert 'Refreshed the details of 0 titles.' in out
    assert Title.objects.get(kind='movie').title == 'Old Movie Name'


def test_a_series_nobody_follows_gets_its_details_and_episodes_and_keeps_its_typical_runtime(user, respx_mock):
    series = make_series(1396, OLD)
    pilot = Episode.objects.create(title=series, tmdb_id=2101, season_number=1, episode_number=1, name='Old Pilot Name')
    watch = Watch.objects.create(user=user, title=series, episode=pilot)
    ToWatchItem.objects.create(user=user, title=series, removed_at=OLD)  # taken off the list long ago
    watch.delete()  # and its watches removed, so nobody follows it any more
    mock_series(respx_mock, 1396)

    _, err = run()

    series.refresh_from_db()
    assert (series.title, series.year, series.overview) == ('New Series Name', '2019', 'The new series summary.')
    assert series.poster_url == 'https://image.tmdb.org/t/p/w342/new-series-poster.jpg'
    assert series.status == 'Ended'
    # The series' runtime is the typical runtime of its episodes, not something TMDB's details overwrite.
    assert series.runtime == 52
    assert list(series.episodes.order_by('episode_number').values_list('name', flat=True)) == ['Pilot', 'New Episode']
    assert series.details_refreshed_at == NOW
    assert err == ''


def test_a_followed_title_with_old_details_is_not_asked_twice_for_its_dates(user, respx_mock):
    movie = make_movie(27205, OLD)
    ToWatchItem.objects.create(user=user, title=movie)
    route = respx_mock.get(MOVIE_URL.format(27205)).respond(json=movie_answer(27205))

    run()

    # One call for its dates (the To Watch step), one for its details. Not a third for the dates again.
    assert route.call_count == 2
    movie.refresh_from_db()
    assert movie.title == 'New Movie Name'
    assert movie.details_refreshed_at == NOW


def test_tmdb_failing_keeps_the_old_details_and_tries_again_the_next_day(user, respx_mock):
    broken = make_movie(27205, OLD)
    fine = make_movie(603, OLD)
    respx_mock.get(MOVIE_URL.format(27205)).mock(return_value=httpx.Response(500))
    respx_mock.get(MOVIE_URL.format(603)).respond(json=movie_answer(603))

    _, err = run()

    broken.refresh_from_db()
    assert broken.title == 'Old Movie Name'
    assert broken.details_refreshed_at == OLD  # still old, so the next run asks again
    assert 'Could not refresh the details of “Old Movie Name”' in err
    assert '1 title could not be refreshed' in err
    fine.refresh_from_db()
    assert fine.title == 'New Movie Name'


def test_a_title_tmdb_no_longer_has_keeps_its_details_and_is_not_an_error(user, respx_mock):
    movie = make_movie(27205, OLD)
    Watch.objects.create(user=user, title=movie)
    respx_mock.get(MOVIE_URL.format(27205)).mock(return_value=httpx.Response(404))

    out, err = run()

    movie.refresh_from_db()
    assert movie.title == 'Old Movie Name'
    assert movie.details_refreshed_at == OLD
    assert 'TMDB no longer has “Old Movie Name”. Its saved details are kept.' in out
    assert err == ''
    assert Watch.objects.filter(title=movie).count() == 1


def test_a_title_added_from_search_is_not_asked_about_again_for_5_months(user, client, respx_mock):
    Profile.objects.create(user=user, timezone='Europe/Lisbon')  # a time zone chosen, so no redirect to Profile
    client.force_login(user)
    route = respx_mock.get(MOVIE_URL.format(27205)).respond(json=movie_answer(27205))

    client.post('/to-watch/add/', {'kind': 'movie', 'tmdb_id': 27205})

    assert Title.objects.get(tmdb_id=27205).details_refreshed_at == NOW
    calls = route.call_count
    with time_machine.travel(NOW + datetime.timedelta(days=149), tick=False):
        call_command('refresh_calendar', stdout=io.StringIO(), stderr=io.StringIO())
    # Only the To Watch step asked (for its dates), not the details step.
    assert route.call_count == calls + 1
