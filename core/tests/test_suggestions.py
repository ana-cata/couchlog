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


def tile_ids(html, kind):
    return [int(number) for number in re.findall(rf'class="tile" href="/{kind}/(\d+)/"', html)]


def shown(page, kind):
    """The TMDB ids of the tiles of one kind that are on the screen, in the order shown (the spares are not)."""
    return tile_ids(re.sub(r'<template>.*?</template>', '', page, flags=re.DOTALL), kind)


def spares(page, kind):
    """The TMDB ids of the spare tiles of one kind: the ones in the <template>, which is never drawn."""
    return tile_ids(''.join(re.findall(r'<template>(.*?)</template>', page, flags=re.DOTALL)), kind)


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
    # What is left of the genre lists is kept as spares.
    assert shown(page, 'movie') == list(range(100, 110))
    assert shown(page, 'series') == list(range(200, 210))
    assert spares(page, 'movie') == [110, 111]
    assert spares(page, 'series') == [210]


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
    assert spares(page, 'movie') == [26, 27, 28]


def test_with_no_history_everything_is_trending(logged_in_client, respx_mock):
    # Neither discover address is set up: with no genres to go by, TMDB is not asked for them.
    tmdb_list(respx_mock, TRENDING_MOVIE, [movie(number) for number in range(1, 13)])
    tmdb_list(respx_mock, TRENDING_TV, [show(number) for number in range(101, 104)])

    page = get_suggestions(logged_in_client)

    assert shown(page, 'movie') == list(range(1, 11))
    assert spares(page, 'movie') == [11, 12]
    assert shown(page, 'series') == [101, 102, 103]
    assert spares(page, 'series') == []
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
    # Nothing is shown for a kind that has no suggestions, and with no spare there is no place for spares either.
    assert 'Suggested series' not in page
    assert '<template>' not in page
    # Before it is added, a suggestion does not say it is on the list.
    assert 'data-on-list' not in page


def test_nothing_is_saved_by_suggesting(logged_in_client, user, respx_mock):
    # Twelve movies: ten are shown and two wait as spares. Neither the shown nor the spares are saved.
    tmdb_list(respx_mock, TRENDING_MOVIE, [movie(number) for number in range(1, 13)])
    tmdb_list(respx_mock, TRENDING_TV, [show(1399)])

    page = get_suggestions(logged_in_client)

    assert spares(page, 'movie') == [11, 12]
    assert not Title.objects.exists()
    assert not ToWatchItem.objects.exists()


# The spares: what is left of the same lists, kept to replace a suggestion once it is added.


def test_what_is_left_over_comes_as_spares_in_the_same_order_and_hidden(logged_in_client, user, respx_mock):
    watch(user, saved('movie', 1, DRAMA))
    tmdb_list(respx_mock, DISCOVER_MOVIE, [movie(number) for number in range(100, 114)])
    tmdb_list(respx_mock, TRENDING_TV, [show(200)])

    page = get_suggestions(logged_in_client)

    assert shown(page, 'movie') == list(range(100, 110))
    assert spares(page, 'movie') == [110, 111, 112, 113]
    # They are inside a <template>, which the browser never draws, and each is a whole tile with its button.
    spare_part = re.search(r'<template>(.*?)</template>', page, flags=re.DOTALL).group(1)
    assert spare_part.count('<li>') == 4
    assert spare_part.count('hx-post="/to-watch/add/"') == 4
    assert 'name="tmdb_id" value="113"' in spare_part
    # Series had one suggestion and no spare: only movies have a template.
    assert page.count('<template>') == 1


def test_the_spares_never_repeat_a_title_shown_saved_watched_or_dropped(logged_in_client, user, respx_mock):
    watch(user, saved('movie', 101, DRAMA))
    ToWatchItem.objects.create(user=user, title=saved('movie', 102, DRAMA))
    DroppedSeries.objects.create(user=user, title=saved('series', 201, DRAMA))
    watch(user, saved('series', 202, DRAMA))
    # TMDB repeats 105 in the same list, and the left-out titles are in both lists.
    tmdb_list(respx_mock, DISCOVER_MOVIE, [movie(number) for number in (101, 102, 103, 104, 105, 105, *range(106, 118))])
    tmdb_list(respx_mock, DISCOVER_TV, [show(number) for number in (201, 202, *range(203, 217))])

    page = get_suggestions(logged_in_client)

    assert shown(page, 'movie') + spares(page, 'movie') == list(range(103, 118))
    assert shown(page, 'series') + spares(page, 'series') == list(range(203, 217))
    assert spares(page, 'movie') == list(range(113, 118))
    assert spares(page, 'series') == list(range(213, 217))


def test_spares_that_come_from_trending_are_kept_too_without_asking_for_more(logged_in_client, user, respx_mock):
    watch(user, saved('movie', 1, DRAMA))
    tmdb_list(respx_mock, DISCOVER_MOVIE, [movie(number) for number in (10, 11)])
    trending = tmdb_list(respx_mock, TRENDING_MOVIE, [movie(number) for number in (11, *range(20, 40))])
    tmdb_list(respx_mock, TRENDING_TV, [])

    page = get_suggestions(logged_in_client)

    # Only the first page of each list is used: no second page was asked for.
    assert shown(page, 'movie') == [10, 11, *range(20, 28)]
    assert spares(page, 'movie') == list(range(28, 40))
    assert trending.call_count == 1
    assert 'page' not in trending.calls.last.request.url.params


def test_each_account_gets_its_own_spares(client, user, respx_mock):
    other = User.objects.create_user(username='other-user', password='made-up-password')
    Profile.objects.create(user=other, timezone='Europe/Lisbon')
    # The same TMDB list for both. One account already watched 105, so it has one title fewer to show.
    watch(user, saved('movie', 105, DRAMA))
    watch(other, saved('movie', 1, DRAMA))
    tmdb_list(respx_mock, DISCOVER_MOVIE, [movie(number) for number in range(100, 112)])
    tmdb_list(respx_mock, TRENDING_TV, [])
    other_client = Client()
    client.force_login(user)
    other_client.force_login(other)

    mine = get_suggestions(client)
    theirs = get_suggestions(other_client)

    assert shown(mine, 'movie') == [100, 101, 102, 103, 104, 106, 107, 108, 109, 110]
    assert spares(mine, 'movie') == [111]
    assert shown(theirs, 'movie') == list(range(100, 110))
    assert spares(theirs, 'movie') == [110, 111]


# The button says when the title is on the list: suggestions.js replaces a suggested tile then and only then.


def press_add(client, tmdb_id=603):
    return client.post('/to-watch/add/', {'kind': 'movie', 'tmdb_id': tmdb_id}, headers={'HX-Request': 'true'})


def test_the_button_says_when_the_title_is_on_the_list(logged_in_client, respx_mock):
    respx_mock.get(f'{TMDB}/movie/603').respond(json=movie(603))

    added = press_add(logged_in_client).content.decode()
    again = press_add(logged_in_client).content.decode()  # already on the list: it is on the list all the same
    removed = logged_in_client.post(
        '/to-watch/remove/', {'kind': 'movie', 'tmdb_id': 603}, headers={'HX-Request': 'true'}
    ).content.decode()

    assert '<div class="to-watch-action" data-on-list>' in added
    assert '<div class="to-watch-action" data-on-list>' in again
    assert 'data-on-list' not in removed
    assert 'Add to To Watch' in removed


def test_when_tmdb_fails_the_button_does_not_say_the_title_is_on_the_list(logged_in_client, user, respx_mock):
    respx_mock.get(f'{TMDB}/movie/603').respond(500)

    answer = press_add(logged_in_client).content.decode()

    assert 'data-on-list' not in answer
    assert 'role="alert"' in answer
    assert not ToWatchItem.objects.filter(user=user).exists()


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


def mock_movies(respx_mock, *numbers):
    """TMDB's answer for each movie, which is asked for once, when the movie is first added."""
    for number in numbers:
        respx_mock.get(f'{TMDB}/movie/{number}').respond(json=movie(number))


def tile(page, number, kind='Movie'):
    """The suggested tile of one made-up title."""
    return page.locator('.suggestions li', has=page.get_by_text(f'Made-up {kind} {number}', exact=True))


def add_button(page, number):
    return tile(page, number).get_by_role('button', name='Add to To Watch')


def names(page):
    """The names of the suggested tiles on the screen, in order."""
    return page.locator('.suggestions .tile strong').all_inner_texts()


def movie_names(*numbers):
    return [f'Made-up Movie {number}' for number in numbers]


def on_my_list(user):
    return sorted(ToWatchItem.objects.filter(user=user, removed_at=None).values_list('title__tmdb_id', flat=True))


def test_adding_a_suggestion_replaces_its_tile_with_the_next_spare(live_server, page, respx_mock, user):
    tmdb_list(respx_mock, TRENDING_MOVIE, [movie(number) for number in range(1, 13)])
    tmdb_list(respx_mock, TRENDING_TV, [])
    mock_movies(respx_mock, 1, 2, 11)
    page.route('https://image.tmdb.org/**', lambda route: route.abort())
    log_in(page, live_server)
    open_search(page, live_server)
    expect(page.locator('.suggestions .tile')).to_have_count(10)
    # The spares wait in the page, and none of them is drawn.
    assert page.locator('.suggestions template').count() == 1
    expect(page.get_by_text('Made-up Movie 11', exact=True)).to_have_count(0)

    # The first tile leaves and the next spare takes its place, so the list still has ten.
    add_button(page, 1).click()
    expect(page.get_by_text('Made-up Movie 1', exact=True)).to_have_count(0)
    expect(page.locator('.suggestions .tile')).to_have_count(10)
    assert names(page) == movie_names(11, 2, 3, 4, 5, 6, 7, 8, 9, 10)
    assert on_my_list(user) == [1]
    # The new tile has a working button: it is replaced in turn, by the last spare.
    add_button(page, 11).click()
    expect(page.get_by_text('Made-up Movie 11', exact=True)).to_have_count(0)
    assert names(page) == movie_names(12, 2, 3, 4, 5, 6, 7, 8, 9, 10)
    assert on_my_list(user) == [1, 11]
    # No spare is left: the tile just goes, and the others stay as they were.
    add_button(page, 2).click()
    expect(page.locator('.suggestions .tile')).to_have_count(9)
    assert names(page) == movie_names(12, 3, 4, 5, 6, 7, 8, 9, 10)
    assert on_my_list(user) == [1, 2, 11]
    # Nothing on the screen says "Remove": a suggestion that was added is not there any more.
    expect(page.get_by_role('button', name='Remove from To Watch')).to_have_count(0)

    # Reloading picks the suggestions again, without the three that are on my list.
    page.reload()
    expect(page.locator('.suggestions .tile')).to_have_count(9)
    assert names(page) == movie_names(3, 4, 5, 6, 7, 8, 9, 10, 12)
    assert on_my_list(user) == [1, 2, 11]


def test_quick_presses_on_different_tiles_never_bring_the_same_replacement(live_server, page, respx_mock, user):
    tmdb_list(respx_mock, TRENDING_MOVIE, [movie(number) for number in range(1, 15)])
    tmdb_list(respx_mock, TRENDING_TV, [])
    mock_movies(respx_mock, 1, 2, 3)
    page.route('https://image.tmdb.org/**', lambda route: route.abort())
    log_in(page, live_server)
    open_search(page, live_server)
    expect(page.locator('.suggestions .tile')).to_have_count(10)

    # Three presses one right after the other, without waiting for any answer.
    for number in (1, 2, 3):
        add_button(page, number).click()
    expect(page.get_by_text('Made-up Movie 1', exact=True)).to_have_count(0)
    expect(page.get_by_text('Made-up Movie 2', exact=True)).to_have_count(0)
    expect(page.get_by_text('Made-up Movie 3', exact=True)).to_have_count(0)

    expect(page.locator('.suggestions .tile')).to_have_count(10)
    assert sorted(names(page)) == sorted(movie_names(*range(4, 14)))
    assert on_my_list(user) == [1, 2, 3]


def test_a_suggested_series_is_replaced_and_still_collects_its_episodes(live_server, page, respx_mock, user):
    tmdb_list(respx_mock, TRENDING_MOVIE, [])
    tmdb_list(respx_mock, TRENDING_TV, [show(number) for number in range(800, 812)])
    respx_mock.get(f'{TMDB}/tv/800').respond(
        json={
            'id': 800, 'name': 'Made-up Series 800', 'first_air_date': '2010-01-01', 'status': 'Returning Series',
            'seasons': [{'season_number': 1}], 'external_ids': {'imdb_id': None},
            'genres': [{'id': 18, 'name': 'Drama'}],
        }
    )
    respx_mock.get(f'{TMDB}/tv/800/season/1').respond(
        json={
            'season_number': 1,
            'episodes': [
                {'id': 9001, 'season_number': 1, 'episode_number': 1, 'name': 'Premiere', 'air_date': '2026-11-06'}
            ],
        }
    )
    page.route('https://image.tmdb.org/**', lambda route: route.abort())
    log_in(page, live_server)
    open_search(page, live_server)
    expect(page.locator('.suggestions .tile')).to_have_count(10)

    # The tile is replaced at once, but the second request (the episodes and Calendar dates) is still sent for it.
    with page.expect_response('**/to-watch/collect/') as collected:
        tile(page, 800, 'Series').get_by_role('button', name='Add to To Watch').click()
    assert collected.value.status == 204
    expect(page.get_by_text('Made-up Series 800', exact=True)).to_have_count(0)
    expect(page.get_by_text('Made-up Series 810', exact=True)).to_have_count(1)
    expect(page.locator('.suggestions .tile')).to_have_count(10)
    assert on_my_list(user) == [800]
    assert Episode.objects.filter(title__tmdb_id=800).count() == 1


def test_a_kind_with_nothing_left_loses_its_heading(live_server, page, respx_mock, user):
    tmdb_list(respx_mock, TRENDING_MOVIE, [movie(1)])
    tmdb_list(respx_mock, TRENDING_TV, [show(800)])
    mock_movies(respx_mock, 1)
    page.route('https://image.tmdb.org/**', lambda route: route.abort())
    log_in(page, live_server)
    open_search(page, live_server)

    add_button(page, 1).click()

    # Like a kind that never had suggestions, it shows no heading; the other kind is untouched.
    expect(page.get_by_role('heading', name='Suggested movies')).to_have_count(0)
    expect(page.get_by_role('heading', name='Suggested series')).to_be_visible()
    expect(page.locator('.suggestions .tile')).to_have_count(1)


def test_a_search_result_keeps_its_tile_and_its_button_turns_into_remove(live_server, page, respx_mock, user):
    tmdb_list(respx_mock, SEARCH, [{'media_type': 'movie', **movie(9)}])
    mock_movies(respx_mock, 9)
    page.route('https://image.tmdb.org/**', lambda route: route.abort())
    log_in(page, live_server)
    page.goto(live_server.url + '/search/?q=made-up')
    page.wait_for_load_state('load')

    page.get_by_role('button', name='Add to To Watch').click()

    expect(page.get_by_role('button', name='Remove from To Watch')).to_be_visible()
    expect(page.locator('.tile')).to_have_count(1)
    assert on_my_list(user) == [9]
    # And it can be taken off again from the same button.
    page.get_by_role('button', name='Remove from To Watch').click()
    expect(page.get_by_role('button', name='Add to To Watch')).to_be_visible()
    assert on_my_list(user) == []


def test_taking_a_suggestion_off_to_watch_and_undoing_it_puts_everything_back(live_server, page, respx_mock, user):
    tmdb_list(respx_mock, TRENDING_MOVIE, [movie(1), movie(2)])
    tmdb_list(respx_mock, TRENDING_TV, [])
    mock_movies(respx_mock, 1)
    page.route('https://image.tmdb.org/**', lambda route: route.abort())
    log_in(page, live_server)
    open_search(page, live_server)
    expect(page.locator('.suggestions .tile')).to_have_count(2)

    add_button(page, 1).click()
    expect(page.get_by_text('Made-up Movie 1', exact=True)).to_have_count(0)
    assert on_my_list(user) == [1]
    added_at = ToWatchItem.objects.get(user=user, title__tmdb_id=1).added_at

    # The title is on To Watch, and is taken off from its own page. Removing it takes it off the list...
    page.goto(live_server.url + '/movies/')
    expect(page.locator('.tile')).to_contain_text('Made-up Movie 1')
    page.locator('.tile').click()
    page.get_by_role('button', name='Remove from To Watch').click()
    expect(page.get_by_role('button', name='Add to To Watch')).to_be_visible()
    assert on_my_list(user) == []
    # ...so it can be suggested again...
    open_search(page, live_server)
    expect(page.locator('.suggestions .tile')).to_have_count(2)
    assert names(page) == movie_names(1, 2)

    # ...and Undo, which the list offers for 10 seconds, puts it back on the list exactly as it was.
    page.goto(live_server.url + '/movies/')
    page.get_by_role('button', name='Undo').click()
    expect(page.locator('.tile')).to_contain_text('Made-up Movie 1')
    assert on_my_list(user) == [1]
    assert ToWatchItem.objects.get(user=user, title__tmdb_id=1).added_at == added_at
    open_search(page, live_server)
    expect(page.locator('.suggestions .tile')).to_have_count(1)
    assert names(page) == movie_names(2)
