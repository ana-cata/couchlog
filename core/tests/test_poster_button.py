"""The To Watch button on a poster: a small round + in the poster's corner (a ✓ once the title is on the list) on every
tile, and a small button with words on a title's own page. Pressing it does what the old wide button did."""

import re

import pytest
from django.contrib.auth.models import User
from django.test import Client

from core.models import Profile, Title, ToWatchItem

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


# --- on the tiles -------------------------------------------------------------------------------------------------


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


def test_the_to_watch_lists_have_the_round_button_too(me):
    make_item(me.user, 'movie', 603)
    make_item(me.user, 'series', 1399)

    assert round_buttons(page(me, '/movies/')) == [(ROUND_ON_LIST, 'Remove from To Watch')]
    assert round_buttons(page(me, '/series/')) == [(ROUND_ON_LIST, 'Remove from To Watch')]


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
