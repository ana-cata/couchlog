"""The To Watch button on a poster: a small round + in the poster's corner (a ✓ once the title is on the list) on the tiles
of the Search page (results and suggestions) and nowhere else, and a small button with words on a title's own page.
Pressing it does what the old wide button did."""

import datetime
import re

import pytest
from django.contrib.auth.models import User
from django.test import Client

from core.models import DroppedSeries, Episode, Profile, Title, ToWatchItem, Watch

SEARCH_URL = 'https://api.themoviedb.org/3/search/multi'
MOVIE_URL = 'https://api.themoviedb.org/3/movie/603'

# Made-up TMDB answers. The tests never call the real TMDB.
MADE_UP_MOVIE = {
    'id': 603,
    'title': 'Made-up Movie',
    'release_date': '1999-03-31',
    'poster_path': '/made-up-movie.jpg',
    'overview': 'A made-up story about a movie.',
}
RESULTS = {
    'results': [
        {'media_type': 'movie', 'id': 603, 'title': 'Made-up Movie', 'release_date': '1999-03-31', 'poster_path': '/a.jpg'},
        {'media_type': 'tv', 'id': 1399, 'name': 'Made-up Series', 'first_air_date': '2011-04-17', 'poster_path': '/b.jpg'},
    ]
}
ROUND = 'corner-button'
ROUND_ON_LIST = 'corner-button on-list'
CHECK_ONLY = '<span class="corner-button on-list">'


@pytest.fixture(autouse=True)
def tmdb_key(settings):
    settings.TMDB_API_KEY = 'made-up-secret-key'


@pytest.fixture
def me(db):
    user = User.objects.create_user(username='made-up-user', password='made-up-password')
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    client = Client()
    client.force_login(user)
    client.user = user
    return client


def page(client, url):
    return client.get(url).content.decode()


def round_buttons(html):
    """Every round button on the page as (its class, its hover hint), in page order."""
    return re.findall(r'<button type="submit" class="(corner-button[^"]*)" title="([^"]+)"', html)


def make_item(user, kind, tmdb_id, **extra):
    title = Title.objects.create(kind=kind, tmdb_id=tmdb_id, title=f'Made-up {kind} {tmdb_id}', **extra)
    return ToWatchItem.objects.create(user=user, title=title)


# --- on the Search page's tiles ------------------------------------------------------------------------------------


def test_search_results_have_a_round_button_in_the_poster_corner_and_no_wide_button(me, respx_mock):
    respx_mock.get(SEARCH_URL).respond(json=RESULTS)

    html = page(me, '/search/?q=made-up')

    assert round_buttons(html) == [(ROUND, 'Add to To Watch'), (ROUND, 'Add to To Watch')]
    assert html.count('<div class="to-watch-action to-watch-corner">') == 2
    assert '<button type="submit" class="outline secondary">' not in html


def test_the_round_button_has_words_for_screen_readers(me, respx_mock):
    respx_mock.get(SEARCH_URL).respond(json=RESULTS)

    html = page(me, '/search/?q=made-up')

    # The words are in the button but cannot be seen, so the button has a name without them showing.
    assert html.count('<span class="idle">Add to To Watch</span><span class="busy">Adding…</span>') == 2
    assert html.count('<span class="visually-hidden">') == 2


def test_a_title_on_the_list_has_a_check_that_removes_it(me, respx_mock):
    respx_mock.get(SEARCH_URL).respond(json=RESULTS)
    make_item(me.user, 'movie', 603)

    html = page(me, '/search/?q=made-up')

    assert round_buttons(html) == [(ROUND_ON_LIST, 'Remove from To Watch'), (ROUND, 'Add to To Watch')]
    assert 'action="/to-watch/remove/"' in html
    assert '<span class="idle">Remove from To Watch</span><span class="busy">Removing…</span>' in html


def watch_film(user):
    film = Title.objects.get_or_create(kind='movie', tmdb_id=603, defaults={'title': 'Made-up Movie'})[0]
    return Watch.objects.create(user=user, title=film, watched_on=datetime.date(2026, 1, 1))


def make_series():
    return Title.objects.create(kind='series', tmdb_id=1399, title='Made-up Series')


def test_a_film_in_history_has_a_check_with_nothing_to_press(me, respx_mock):
    respx_mock.get(SEARCH_URL).respond(json=RESULTS)
    watch_film(me.user)

    html = page(me, '/search/?q=made-up')

    assert html.count(CHECK_ONLY) == 1
    assert 'In your History' in html
    assert round_buttons(html) == [(ROUND, 'Add to To Watch')]  # only the series can still be added


def test_a_series_i_started_has_a_check_with_nothing_to_press(me, respx_mock):
    respx_mock.get(SEARCH_URL).respond(json=RESULTS)
    series = make_series()
    episode = Episode.objects.create(title=series, tmdb_id=1, season_number=1, episode_number=1)
    Watch.objects.create(user=me.user, title=series, episode=episode, watched_on=datetime.date(2026, 1, 1))

    html = page(me, '/search/?q=made-up')

    assert html.count(CHECK_ONLY) == 1
    assert 'In your Series lists' in html
    assert round_buttons(html) == [(ROUND, 'Add to To Watch')]  # only the film can still be added


def test_a_dropped_series_has_a_check_with_nothing_to_press(me, respx_mock):
    respx_mock.get(SEARCH_URL).respond(json=RESULTS)
    DroppedSeries.objects.create(user=me.user, title=make_series())

    html = page(me, '/search/?q=made-up')

    assert html.count(CHECK_ONLY) == 1
    assert 'In your Dropped list' in html
    assert round_buttons(html) == [(ROUND, 'Add to To Watch')]


def test_a_film_in_history_of_another_account_can_still_be_added(me, respx_mock):
    respx_mock.get(SEARCH_URL).respond(json=RESULTS)
    watch_film(User.objects.create_user(username='second-user', password='made-up-password'))

    html = page(me, '/search/?q=made-up')

    assert CHECK_ONLY not in html
    assert round_buttons(html) == [(ROUND, 'Add to To Watch'), (ROUND, 'Add to To Watch')]


def test_a_film_on_both_lists_can_be_taken_off_to_watch_and_then_keeps_a_check(me, respx_mock):
    respx_mock.get(SEARCH_URL).respond(json=RESULTS)
    make_item(me.user, 'movie', 603)
    watch_film(me.user)

    html = page(me, '/search/?q=made-up')
    removed = press(me, 'remove')

    assert round_buttons(html)[0] == (ROUND_ON_LIST, 'Remove from To Watch')
    assert CHECK_ONLY in removed
    assert round_buttons(removed) == []
    assert Watch.objects.filter(user=me.user).count() == 1  # History is not touched


def test_the_to_watch_lists_have_no_button_on_their_tiles(me):
    make_item(me.user, 'movie', 603)
    make_item(me.user, 'series', 1399)

    for url in ('/movies/', '/series/'):
        html = page(me, url)
        # The title is there and opens its page, and that page is where "Remove from To Watch" is.
        assert 'class="tile"' in html
        assert round_buttons(html) == []
        assert 'action="/to-watch/remove/"' not in html
        assert '<button' not in html


# --- on a title's own page ----------------------------------------------------------------------------------------


def test_a_title_page_keeps_a_small_button_with_words(me, respx_mock):
    respx_mock.get(MOVIE_URL).respond(json=MADE_UP_MOVIE)

    html = page(me, '/movie/603/')

    assert round_buttons(html) == []
    assert 'to-watch-corner' not in html
    assert re.search(r'<button type="submit" class="outline secondary">\s*<span class="idle">Add to To Watch', html)


# --- what pressing it does ----------------------------------------------------------------------------------------


def press(client, action, corner=True):
    """What htmx sends when the button is pressed, and the page block it gets back."""
    data = {'kind': 'movie', 'tmdb_id': 603, **({'corner': '1'} if corner else {})}
    return client.post(f'/to-watch/{action}/', data, headers={'HX-Request': 'true'}).content.decode()


def test_the_answer_to_a_press_is_drawn_the_way_the_button_was(me, respx_mock):
    respx_mock.get(MOVIE_URL).respond(json=MADE_UP_MOVIE)

    added = press(me, 'add')
    removed = press(me, 'remove')

    assert '<div class="to-watch-action to-watch-corner" data-on-list>' in added
    assert round_buttons(added) == [(ROUND_ON_LIST, 'Remove from To Watch')]
    assert 'data-on-list' not in removed
    assert round_buttons(removed) == [(ROUND, 'Add to To Watch')]


def test_the_answer_to_the_title_page_button_still_has_words(me, respx_mock):
    respx_mock.get(MOVIE_URL).respond(json=MADE_UP_MOVIE)

    added = press(me, 'add', corner=False)

    assert '<div class="to-watch-action" data-on-list>' in added
    assert round_buttons(added) == []
    assert '<span class="idle">Remove from To Watch</span>' in added


def test_removing_with_the_check_is_undone_by_undo_as_before(me):
    item = make_item(me.user, 'movie', 603)
    before = list(ToWatchItem.objects.values())

    press(me, 'remove')
    item.refresh_from_db()
    assert item.removed_at is not None
    removed_page = page(me, '/movies/')
    assert 'Recently removed' in removed_page and 'action="/to-watch/undo/"' in removed_page

    me.post('/to-watch/undo/', {'kind': 'movie', 'tmdb_id': 603})

    assert list(ToWatchItem.objects.values()) == before
