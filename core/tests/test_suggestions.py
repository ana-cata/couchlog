"""The suggested movies and series on the Search page: how they are picked, and that they come and go with the box.

TMDB's answers are made up. An address a test does not set up fails the test if the app asks it, so a test that sets
up fewer addresses also proves that TMDB was not asked for the rest."""

import datetime
import os
import re
import time

import httpx
import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone
from playwright.sync_api import expect

from core.models import DroppedSeries, Episode, Profile, Title, ToWatchItem, Watch
from core.suggestions import top_genres

# The browser's driver runs inside an event loop, and Django refuses database calls from
# there unless told it is fine. It is fine in a test.
os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')

TMDB = 'https://api.themoviedb.org/3'
DISCOVER_MOVIE = f'{TMDB}/discover/movie'
DISCOVER_TV = f'{TMDB}/discover/tv'
TRENDING_MOVIE = f'{TMDB}/trending/movie/week'
TRENDING_TV = f'{TMDB}/trending/tv/week'
SEARCH = f'{TMDB}/search/multi'

# TMDB's genre numbers.
DRAMA, COMEDY, THRILLER, HORROR, ANIMATION, DOCUMENTARY = 18, 35, 53, 27, 16, 99


@pytest.fixture(autouse=True)
def tmdb_key(settings):
    settings.TMDB_API_KEY = 'made-up-secret-key'


@pytest.fixture
def user(db):
    user = User.objects.create_user(username='made-up-user', password='made-up-password')
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    return user


@pytest.fixture
def logged_in_client(client, user):
    client.force_login(user)
    return client


def movie(number):
    """A movie as TMDB's discover and trending lists give it."""
    return {
        'id': number,
        'title': f'Made-up Movie {number}',
        'release_date': '2000-01-01',
        'poster_path': f'/movie-{number}.jpg',
    }


def show(number):
    """A series as TMDB's discover and trending lists give it."""
    return {
        'id': number,
        'name': f'Made-up Series {number}',
        'first_air_date': '2010-01-01',
        'poster_path': f'/show-{number}.jpg',
    }


def tmdb_list(respx_mock, url, results):
    return respx_mock.get(url).respond(json={'page': 1, 'results': results})


def saved(kind, tmdb_id, *genre_ids):
    """A title in our own database, with the given genres."""
    genres = [{'id': genre_id, 'name': f'Genre {genre_id}'} for genre_id in genre_ids]
    return Title.objects.create(kind=kind, tmdb_id=tmdb_id, title=f'Saved {kind} {tmdb_id}', genres=genres)


def watch(user, title):
    return Watch.objects.create(user=user, title=title, watched_on=datetime.date(2026, 10, 1))


def get_suggestions(client):
    return client.get('/search/suggestions/').content.decode()


def shown(page, kind):
    """The TMDB ids of the tiles of one kind in the page, in the order shown."""
    return [int(number) for number in re.findall(rf'class="tile" href="/{kind}/(\d+)/"', page)]


# How they are picked.


def test_the_top_genres_are_the_three_that_most_titles_have(user):
    other = User.objects.create_user(username='other-user', password='made-up-password')
    watch(user, saved('movie', 1, DRAMA, COMEDY))
    ToWatchItem.objects.create(user=user, title=saved('movie', 2, DRAMA, THRILLER))
    watch(user, saved('movie', 3, COMEDY, THRILLER))
    # A film watched three times still counts once, so its genre does not rise above the others.
    rewatched = saved('movie', 4, DOCUMENTARY)
    for _ in range(3):
        watch(user, rewatched)
    watch(user, saved('movie', 5, ANIMATION))
    watch(user, saved('movie', 14, ANIMATION))
    # These count for nothing: removed from To Watch by hand, no genres saved, a series, another account's film.
    ToWatchItem.objects.create(user=user, title=saved('movie', 6, HORROR), removed_at=timezone.now())
    watch(user, saved('movie', 7))
    watch(user, saved('series', 8, HORROR))
    for number in range(9, 14):
        watch(other, saved('movie', number, HORROR))

    # Drama, Comedy, Thriller and Animation each have two titles. The lower number goes first, and only three are kept.
    assert top_genres(user, 'movie') == [ANIMATION, DRAMA, COMEDY]
    assert top_genres(user, 'series') == [HORROR]


def test_movies_and_series_use_their_own_genres(logged_in_client, user, respx_mock):
    watch(user, saved('movie', 1, DRAMA, COMEDY))
    ToWatchItem.objects.create(user=user, title=saved('movie', 2, DRAMA, THRILLER))
    watch(user, saved('series', 3, 10759))
    discover_movie = tmdb_list(respx_mock, DISCOVER_MOVIE, [])
    discover_tv = tmdb_list(respx_mock, DISCOVER_TV, [])
    tmdb_list(respx_mock, TRENDING_MOVIE, [])
    tmdb_list(respx_mock, TRENDING_TV, [])

    get_suggestions(logged_in_client)

    movie_query = discover_movie.calls.last.request.url.params
    # Any of the genres (a pipe), the most popular first.
    assert movie_query['with_genres'] == f'{DRAMA}|{COMEDY}|{THRILLER}'
    assert movie_query['sort_by'] == 'popularity.desc'
    assert discover_tv.calls.last.request.url.params['with_genres'] == '10759'


def test_what_i_saved_or_watched_or_dropped_is_left_out(logged_in_client, user, respx_mock):
    other = User.objects.create_user(username='other-user', password='made-up-password')
    watch(user, saved('movie', 101, DRAMA))
    ToWatchItem.objects.create(user=user, title=saved('movie', 102, DRAMA))
    # Taken off To Watch by hand: it can be suggested again. Another account's watch is not mine.
    ToWatchItem.objects.create(user=user, title=saved('movie', 103, DRAMA), removed_at=timezone.now())
    watch(other, saved('movie', 104, DRAMA))
    series = saved('series', 201, DRAMA)
    DroppedSeries.objects.create(user=user, title=series)
    started = saved('series', 202, DRAMA)
    episode = Episode.objects.create(title=started, tmdb_id=1, season_number=1, episode_number=1)
    Watch.objects.create(user=user, title=started, episode=episode, watched_on=datetime.date(2026, 10, 1))
    # A movie and a series can share a number: the film 201 is not the dropped series 201.
    tmdb_list(respx_mock, DISCOVER_MOVIE, [movie(number) for number in (101, 102, 103, 104, 201)])
    tmdb_list(respx_mock, DISCOVER_TV, [show(number) for number in (201, 202, 203, 204)])
    tmdb_list(respx_mock, TRENDING_MOVIE, [])
    tmdb_list(respx_mock, TRENDING_TV, [])

    page = get_suggestions(logged_in_client)

    assert shown(page, 'movie') == [103, 104, 201]
    assert shown(page, 'series') == [203, 204]


def test_each_account_gets_its_own_suggestions(client, user, respx_mock):
    other = User.objects.create_user(username='other-user', password='made-up-password')
    Profile.objects.create(user=other, timezone='Europe/Lisbon')
    watch(user, saved('movie', 1, DRAMA))
    watch(other, saved('movie', 2, HORROR))
    discover_movie = tmdb_list(respx_mock, DISCOVER_MOVIE, [movie(10)])
    tmdb_list(respx_mock, TRENDING_MOVIE, [])
    tmdb_list(respx_mock, TRENDING_TV, [])
    other_client = Client()
    client.force_login(user)
    other_client.force_login(other)

    get_suggestions(client)
    get_suggestions(other_client)

    asked = [call.request.url.params['with_genres'] for call in discover_movie.calls]
    assert asked == [str(DRAMA), str(HORROR)]


def test_ten_of_each_are_enough_and_trending_is_not_asked(logged_in_client, user, respx_mock):
    watch(user, saved('movie', 1, DRAMA))
    watch(user, saved('series', 2, DRAMA))
    tmdb_list(respx_mock, DISCOVER_MOVIE, [movie(number) for number in range(100, 112)])
    tmdb_list(respx_mock, DISCOVER_TV, [show(number) for number in range(200, 211)])

    page = get_suggestions(logged_in_client)

    # Only the first ten, in TMDB's order. The trending lists were not set up, so asking them would fail the test.
    assert shown(page, 'movie') == list(range(100, 110))
    assert shown(page, 'series') == list(range(200, 210))


def test_trending_fills_up_what_the_genres_do_not(logged_in_client, user, respx_mock):
    watch(user, saved('movie', 1, DRAMA))
    watch(user, saved('movie', 2))
    watch(user, saved('movie', 3))
    # Four of the genre list are left, then trending adds the rest: not twice what is already there, not what I saw.
    tmdb_list(respx_mock, DISCOVER_MOVIE, [movie(number) for number in (1, 10, 11, 2, 12, 13)])
    tmdb_list(respx_mock, TRENDING_MOVIE, [movie(number) for number in (11, 3, 20, 21, 22, 23, 24, 25, 26, 27, 28)])
    tmdb_list(respx_mock, TRENDING_TV, [])

    page = get_suggestions(logged_in_client)

    assert shown(page, 'movie') == [10, 11, 12, 13, 20, 21, 22, 23, 24, 25]


def test_with_no_history_everything_is_trending(logged_in_client, respx_mock):
    # Neither discover address is set up: with no genres to go by, TMDB is not asked for them.
    tmdb_list(respx_mock, TRENDING_MOVIE, [movie(number) for number in range(1, 13)])
    tmdb_list(respx_mock, TRENDING_TV, [show(number) for number in range(101, 104)])

    page = get_suggestions(logged_in_client)

    assert shown(page, 'movie') == list(range(1, 11))
    assert shown(page, 'series') == [101, 102, 103]
    assert 'Suggested movies' in page
    assert 'Suggested series' in page


def test_few_series_registered_means_trending_series(logged_in_client, user, respx_mock):
    # Movies in the history, series not: the series come from trending, the movies from the genres.
    watch(user, saved('movie', 1, DRAMA))
    tmdb_list(respx_mock, DISCOVER_MOVIE, [movie(number) for number in range(10, 20)])
    tmdb_list(respx_mock, TRENDING_TV, [show(number) for number in range(200, 205)])

    page = get_suggestions(logged_in_client)

    assert shown(page, 'movie') == list(range(10, 20))
    assert shown(page, 'series') == list(range(200, 205))


def test_a_suggestion_is_a_normal_tile_with_the_to_watch_button(logged_in_client, respx_mock):
    tmdb_list(respx_mock, TRENDING_MOVIE, [movie(603)])
    tmdb_list(respx_mock, TRENDING_TV, [])

    page = get_suggestions(logged_in_client)

    assert 'class="tile" href="/movie/603/"' in page
    assert 'Made-up Movie 603' in page
    assert '2000 · Movie' in page
    assert 'https://image.tmdb.org/t/p/w342/movie-603.jpg' in page
    assert 'hx-post="/to-watch/add/"' in page
    assert 'Add to To Watch' in page
    assert 'name="tmdb_id" value="603"' in page
    # Nothing is shown for a kind that has no suggestions.
    assert 'Suggested series' not in page


def test_nothing_is_saved_by_suggesting(logged_in_client, user, respx_mock):
    tmdb_list(respx_mock, TRENDING_MOVIE, [movie(603)])
    tmdb_list(respx_mock, TRENDING_TV, [show(1399)])

    get_suggestions(logged_in_client)

    assert not Title.objects.exists()
    assert not ToWatchItem.objects.exists()


# When TMDB does not answer.


def test_when_tmdb_fails_for_one_kind_the_other_still_shows(logged_in_client, respx_mock):
    respx_mock.get(TRENDING_MOVIE).mock(side_effect=httpx.ConnectError('no network'))
    tmdb_list(respx_mock, TRENDING_TV, [show(1399)])

    response = logged_in_client.get('/search/suggestions/')

    page = response.content.decode()
    assert response.status_code == 200
    assert 'Could not reach TMDB' in page
    assert shown(page, 'series') == [1399]


def test_a_tmdb_failure_never_shows_the_key(logged_in_client, respx_mock):
    respx_mock.get(TRENDING_MOVIE).respond(401)
    respx_mock.get(TRENDING_TV).respond(500)

    page = get_suggestions(logged_in_client)

    assert 'TMDB did not accept the key' in page
    assert 'TMDB answered with an error' in page
    assert 'made-up-secret-key' not in page


# Coming and going with the search box.


def test_an_empty_box_loads_the_suggestions_after_the_page(logged_in_client, respx_mock):
    page = logged_in_client.get('/search/').content.decode()

    # The page itself does not ask TMDB. It only says where to load the suggestions from.
    assert respx_mock.calls.call_count == 0
    assert 'hx-get="/search/suggestions/"' in page
    assert 'hx-trigger="load"' in page


def test_clearing_the_box_brings_the_suggestions_back(logged_in_client, respx_mock):
    page = logged_in_client.get('/search/', {'q': ''}, headers={'HX-Request': 'true'}).content.decode()

    assert respx_mock.calls.call_count == 0
    assert '<html' not in page
    assert 'hx-get="/search/suggestions/"' in page


def test_typing_replaces_the_suggestions_with_the_results(logged_in_client, respx_mock):
    tmdb_list(respx_mock, SEARCH, [{'media_type': 'movie', **movie(603)}])

    page = logged_in_client.get('/search/', {'q': 'made-up'}, headers={'HX-Request': 'true'}).content.decode()

    assert 'Made-up Movie 603' in page
    assert '/search/suggestions/' not in page


# In a real browser.


def log_in(page, live_server):
    page.goto(live_server.url)
    page.get_by_label('Username').fill('made-up-user')
    page.get_by_label('Password').fill('made-up-password')
    page.get_by_role('button', name='Log in').click()


def open_search(page, live_server):
    page.goto(live_server.url + '/search/')
    # htmx starts when the page has loaded. Typing before that is ignored.
    page.wait_for_load_state('load')


def test_suggestions_go_when_i_type_and_come_back_when_i_clear_the_box(live_server, page, respx_mock, user):
    tmdb_list(respx_mock, TRENDING_MOVIE, [movie(1), movie(2)])
    tmdb_list(respx_mock, TRENDING_TV, [show(3)])

    def slow_search(request):
        time.sleep(1.5)
        return httpx.Response(200, json={'page': 1, 'results': [{'media_type': 'movie', **movie(9)}]})

    respx_mock.get(SEARCH).mock(side_effect=slow_search)
    page.route('https://image.tmdb.org/**', lambda route: route.abort())
    log_in(page, live_server)
    open_search(page, live_server)

    # An empty box: the suggestions are there.
    expect(page.get_by_role('heading', name='Suggested movies')).to_be_visible()
    expect(page.get_by_role('heading', name='Suggested series')).to_be_visible()
    expect(page.locator('.suggestions .tile')).to_have_count(3)

    # The first letter hides them at once, before the (slow) results arrive.
    box = page.get_by_role('searchbox')
    box.press_sequentially('made-up')
    expect(page.get_by_role('heading', name='Suggested movies')).to_be_hidden()
    expect(page.locator('.suggestions')).to_have_count(1)
    # Then the results take their place.
    expect(page.locator('.tile')).to_have_count(1)
    expect(page.locator('.tile')).to_contain_text('Made-up Movie 9')
    expect(page.locator('.suggestions')).to_have_count(0)

    # Clearing the box brings them back.
    box.fill('')
    expect(page.get_by_role('heading', name='Suggested movies')).to_be_visible()
    expect(page.locator('.suggestions .tile')).to_have_count(3)


def test_suggestions_that_arrive_late_do_not_cover_the_results(live_server, page, respx_mock, user):
    tmdb_list(respx_mock, TRENDING_MOVIE, [movie(1), movie(2)])
    tmdb_list(respx_mock, TRENDING_TV, [show(3)])
    tmdb_list(respx_mock, SEARCH, [{'media_type': 'movie', **movie(9)}])
    page.route('https://image.tmdb.org/**', lambda route: route.abort())
    # Hold the suggestions back, as a slow TMDB would, until the results are already on the screen.
    held = []
    page.route('**/search/suggestions/', lambda route: held.append(route))
    log_in(page, live_server)
    open_search(page, live_server)
    expect(page.get_by_text('Loading suggestions')).to_be_visible()

    page.get_by_role('searchbox').press_sequentially('made-up')
    expect(page.locator('.tile')).to_have_count(1)
    with page.expect_response('**/search/suggestions/'):
        held[0].continue_()
    page.wait_for_timeout(300)

    expect(page.get_by_role('heading', name='Suggested movies')).to_have_count(0)
    expect(page.locator('.tile')).to_have_count(1)
    expect(page.locator('.tile')).to_contain_text('Made-up Movie 9')


def test_add_a_suggestion_to_to_watch_and_take_it_off_again(live_server, page, respx_mock, user):
    tmdb_list(respx_mock, TRENDING_MOVIE, [movie(603)])
    tmdb_list(respx_mock, TRENDING_TV, [])
    # Adding a movie saves its details, and collects its release dates from this same answer (it has none here).
    respx_mock.get(f'{TMDB}/movie/603').respond(json=movie(603))
    page.route('https://image.tmdb.org/**', lambda route: route.abort())
    log_in(page, live_server)
    open_search(page, live_server)

    expect(page.locator('.suggestions .tile')).to_have_count(1)
    page.get_by_role('button', name='Add to To Watch').click()
    expect(page.get_by_role('button', name='Remove from To Watch')).to_be_visible()
    assert ToWatchItem.objects.filter(user=user, removed_at=None).count() == 1

    # Undo: the same button takes it off again, and everything is back as it was.
    page.get_by_role('button', name='Remove from To Watch').click()
    expect(page.get_by_role('button', name='Add to To Watch')).to_be_visible()
    assert ToWatchItem.objects.filter(user=user, removed_at=None).count() == 0

    # Added again, it is on my list, so the next time the suggestions are asked for it is no longer one of them.
    page.get_by_role('button', name='Add to To Watch').click()
    expect(page.get_by_role('button', name='Remove from To Watch')).to_be_visible()
    page.reload()
    expect(page.get_by_text('Loading suggestions')).to_have_count(0)
    expect(page.locator('.tile')).to_have_count(0)
