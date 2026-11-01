"""The line under a title's name on its page: the year, the kind, a series' status, the length and the genres. The length
and the genres are left out when TMDB has none, and the genres are saved on the title wherever a title is saved."""

import datetime

import pytest
import time_machine
from django.contrib.auth.models import User
from django.test import Client

from core.models import Profile, Title
from core.title_line import length, title_line

MOVIE_URL = 'https://api.themoviedb.org/3/movie/603'
SERIES_URL = 'https://api.themoviedb.org/3/tv/1399'

DRAMA = {'id': 18, 'name': 'Drama'}
THRILLER = {'id': 53, 'name': 'Thriller'}
COMEDY = {'id': 35, 'name': 'Comedy'}

# Made-up TMDB answers. The tests never call the real TMDB.
MADE_UP_MOVIE = {
    'id': 603,
    'title': 'Made-up Movie',
    'release_date': '2023-03-31',
    'poster_path': '/made-up-movie.jpg',
    'overview': 'A made-up story about a movie.',
    'runtime': 100,
    'genres': [DRAMA, THRILLER],
}
MADE_UP_SERIES = {
    'id': 1399,
    'name': 'Made-up Series',
    'first_air_date': '2023-04-17',
    'poster_path': '/made-up-series.jpg',
    'overview': 'A made-up story about a series.',
    'status': 'Returning Series',
    'seasons': [{'season_number': 1}],
    'genres': [DRAMA, COMEDY],
}


def season(*runtimes):
    """A season 1 with one episode for each runtime (None means TMDB gives no runtime for it)."""
    return {
        'season_number': 1,
        'episodes': [
            {
                'id': 6000 + number,
                'season_number': 1,
                'episode_number': number,
                'name': f'Made-up episode {number}',
                'air_date': '2023-04-17',
                'runtime': runtime,
            }
            for number, runtime in enumerate(runtimes, start=1)
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


@pytest.fixture
def logged_in_client(db):
    user = User.objects.create_user(username='made-up-user', password='made-up-password')
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    client = Client()
    client.force_login(user)
    return client


def movie_page(client, respx_mock, **changes):
    """The movie page, with TMDB answering the made-up movie changed by `changes` (None leaves a key out)."""
    answer = {key: value for key, value in {**MADE_UP_MOVIE, **changes}.items() if value is not None}
    respx_mock.get(MOVIE_URL).respond(json=answer)
    return client.get('/movie/603/').content.decode()


def series_page(client, respx_mock, runtimes=(40, 50), **changes):
    """The series page, with TMDB answering the made-up series changed by `changes` (None leaves a key out) and a
    season 1 with one episode for each of the runtimes."""
    answer = {key: value for key, value in {**MADE_UP_SERIES, **changes}.items() if value is not None}
    respx_mock.get(SERIES_URL).respond(json=answer)
    respx_mock.get(f'{SERIES_URL}/season/1').respond(json=season(*runtimes))
    return client.get('/series/1399/').content.decode()


# --- movies ----------------------------------------------------------------------------------------


def test_a_movie_page_shows_its_length_and_genres_even_when_the_movie_is_not_saved(logged_in_client, respx_mock):
    page = movie_page(logged_in_client, respx_mock)

    assert '<small>2023 · Movie · 1h 40min · Drama, Thriller</small>' in page
    assert Title.objects.count() == 0  # looking at a movie saves nothing


def test_a_movie_saved_before_genres_were_kept_still_shows_them(logged_in_client, respx_mock):
    Title.objects.create(kind='movie', tmdb_id=603, title='Made-up Movie', year='2023', runtime=100)

    page = movie_page(logged_in_client, respx_mock)

    assert '<small>2023 · Movie · 1h 40min · Drama, Thriller</small>' in page


@pytest.mark.parametrize('runtime', [None, 0])
def test_a_movie_with_no_length_shows_the_line_without_it(logged_in_client, respx_mock, runtime):
    # TMDB sometimes says 0 for a movie it knows nothing about.
    answer = {**MADE_UP_MOVIE, 'runtime': runtime}
    respx_mock.get(MOVIE_URL).respond(json=answer)

    page = logged_in_client.get('/movie/603/').content.decode()

    assert '<small>2023 · Movie · Drama, Thriller</small>' in page


@pytest.mark.parametrize('genres', [None, []])
def test_a_movie_with_no_genres_shows_the_line_without_them(logged_in_client, respx_mock, genres):
    page = movie_page(logged_in_client, respx_mock, genres=genres)

    assert '<small>2023 · Movie · 1h 40min</small>' in page


def test_a_movie_with_neither_shows_just_the_year_and_the_kind(logged_in_client, respx_mock):
    page = movie_page(logged_in_client, respx_mock, runtime=None, genres=None)

    assert '<small>2023 · Movie</small>' in page


def test_genre_names_are_shown_as_text_not_as_html(logged_in_client, respx_mock):
    # TMDB has genres such as "Sci-Fi & Fantasy" for series.
    page = movie_page(logged_in_client, respx_mock, genres=[{'id': 10765, 'name': 'Sci-Fi & <b>Fantasy</b>'}])

    assert 'Sci-Fi &amp; &lt;b&gt;Fantasy&lt;/b&gt;' in page and '<b>Fantasy</b>' not in page


# --- series ----------------------------------------------------------------------------------------


def test_a_series_page_shows_status_episode_length_and_genres(logged_in_client, respx_mock):
    page = series_page(logged_in_client, respx_mock)  # episodes of 40 and 50 minutes: 45 on average

    assert '<small>2023 · Series · Returning Series · ~45 min per episode · Drama, Comedy</small>' in page


def test_a_series_page_saves_the_genres_and_the_episode_length(logged_in_client, respx_mock):
    series_page(logged_in_client, respx_mock)

    series = Title.objects.get()
    assert series.genres == [DRAMA, COMEDY] and series.runtime == 45


def test_a_series_with_no_episode_length_shows_the_line_without_it(logged_in_client, respx_mock):
    page = series_page(logged_in_client, respx_mock, runtimes=(None, None))

    assert '<small>2023 · Series · Returning Series · Drama, Comedy</small>' in page


def test_a_series_with_no_genres_shows_the_line_without_them(logged_in_client, respx_mock):
    page = series_page(logged_in_client, respx_mock, genres=None)

    assert '<small>2023 · Series · Returning Series · ~45 min per episode</small>' in page
    assert Title.objects.get().genres == []


def test_a_series_with_neither_status_length_nor_genres_shows_the_year_and_the_kind(logged_in_client, respx_mock):
    page = series_page(logged_in_client, respx_mock, runtimes=(None,), genres=None, status=None)

    assert '<small>2023 · Series</small>' in page


def test_a_series_saved_before_genres_were_kept_gets_them_at_its_next_refresh(logged_in_client, respx_mock):
    Title.objects.create(
        kind='series',
        tmdb_id=1399,
        title='Made-up Series',
        year='2023',
        status='Returning Series',
        runtime=45,
        episodes_refreshed_at=NOW - datetime.timedelta(days=2),  # over a day old, so the page asks TMDB again
    )

    page = series_page(logged_in_client, respx_mock)

    assert '<small>2023 · Series · Returning Series · ~45 min per episode · Drama, Comedy</small>' in page
    assert Title.objects.get().genres == [DRAMA, COMEDY]


def test_a_series_refreshed_recently_waits_for_its_next_refresh_to_show_genres(logged_in_client, respx_mock):
    Title.objects.create(
        kind='series',
        tmdb_id=1399,
        title='Made-up Series',
        year='2023',
        status='Returning Series',
        runtime=45,
        episodes_refreshed_at=NOW - datetime.timedelta(hours=1),  # fresh: TMDB is not asked
    )

    page = logged_in_client.get('/series/1399/').content.decode()

    assert '<small>2023 · Series · Returning Series · ~45 min per episode</small>' in page
    assert respx_mock.calls.call_count == 0


# --- saving the genres -----------------------------------------------------------------------------


def test_marking_a_movie_as_watched_saves_its_genres(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_URL).respond(json=MADE_UP_MOVIE)

    logged_in_client.post('/watched/add/', {'kind': 'movie', 'tmdb_id': 603, 'watched_on': '2026-10-28'})

    assert Title.objects.get().genres == [DRAMA, THRILLER]


def test_rating_a_movie_saves_its_genres(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_URL).respond(json=MADE_UP_MOVIE)

    logged_in_client.post('/rating/save/', {'kind': 'movie', 'tmdb_id': 603, 'stars': 4, 'note': ''})

    assert Title.objects.get().genres == [DRAMA, THRILLER]


# --- the wording -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ('minutes', 'words'),
    [(1, '1 min'), (45, '45 min'), (59, '59 min'), (60, '1h'), (61, '1h 1min'), (100, '1h 40min'), (120, '2h'), (185, '3h 5min')],
)
def test_a_length_is_written_in_minutes_under_an_hour_and_in_hours_above(minutes, words):
    assert length(minutes) == words


def test_a_series_length_has_a_tilde_and_per_episode_also_above_an_hour():
    assert title_line('series', '2023', 'Ended', 75, [DRAMA]) == '2023 · Series · Ended · ~1h 15min per episode · Drama'


def test_a_movie_with_no_year_says_so():
    assert title_line('movie', '', '', 100, [DRAMA]) == 'Year unknown · Movie · 1h 40min · Drama'
