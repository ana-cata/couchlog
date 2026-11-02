"""Friendly messages: "Searching…" while TMDB is asked, and a line under the header bar when Couchlog itself does not
answer a button or a search (no connection) or answers with an error. Both happen in the browser, so most of this is
tested in a real one. TMDB problems have their own messages, tested with each page."""

import os
import re

import pytest
from django.contrib.auth.models import User
from django.test import Client
from playwright.sync_api import expect

from core.models import Profile, ToWatchItem

# The browser's driver runs inside an event loop, and Django refuses database calls from
# there unless told it is fine. It is fine in a test.
os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')

SEARCH = 'https://api.themoviedb.org/3/search/multi'
# Made-up TMDB answer. The tests never call the real TMDB.
MADE_UP_MOVIE = {
    'media_type': 'movie',
    'id': 603,
    'title': 'Made-up Movie',
    'release_date': '1999-03-31',
    'poster_path': '/made-up-movie.jpg',
    'overview': 'A made-up story about a movie.',
}
# The page's own live search requests (not TMDB's).
LIVE_SEARCH = re.compile(r'/search/\?q=')
NO_ANSWER = 'Couchlog did not answer. Check the Wi-Fi and try again.'
ERROR = 'Something went wrong. Try again.'


@pytest.fixture(autouse=True)
def tmdb_key(settings):
    settings.TMDB_API_KEY = 'made-up-secret-key'


@pytest.fixture
def searching(live_server, page, respx_mock):
    """Logged in, on Search with one result already shown (so no suggestions load), and htmx ready."""
    user = User.objects.create_user(username='made-up-user', password='made-up-password')
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    respx_mock.get(SEARCH).respond(json={'page': 1, 'results': [MADE_UP_MOVIE]})
    page.route('https://image.tmdb.org/**', lambda route: route.abort())
    page.goto(live_server.url)
    page.get_by_label('Username').fill('made-up-user')
    page.get_by_label('Password').fill('made-up-password')
    page.get_by_role('button', name='Log in').click()
    page.goto(live_server.url + '/search/?q=made-up')
    page.wait_for_load_state('load')
    expect(page.locator('.tile')).to_have_count(1)
    return user


def test_the_message_line_is_in_the_header_and_hidden_until_needed(db):
    user = User.objects.create_user(username='made-up-user', password='made-up-password')
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    client = Client()
    client.login(username='made-up-user', password='made-up-password')

    html = client.get('/search/').content.decode()

    assert re.search(r'<header class="site-header">.*<p id="problem" role="alert" hidden></p>.*</header>', html, re.DOTALL)
    assert 'hx-indicator="#searching"' in html


def test_searching_shows_while_tmdb_is_asked_and_goes_with_the_results(searching, page):
    # Hold the answer back, as a slow TMDB would.
    held = []
    page.route(LIVE_SEARCH, lambda route: held.append(route))
    expect(page.get_by_text('Searching…')).to_be_hidden()

    page.get_by_label('Search movies and series').fill('made-up again')

    expect(page.get_by_text('Searching…')).to_be_visible()
    while not held:
        page.wait_for_timeout(50)
    with page.expect_response(LIVE_SEARCH):
        held[0].continue_()
    expect(page.get_by_text('Searching…')).to_be_hidden()
    expect(page.locator('.tile')).to_have_count(1)


def test_a_button_with_no_answer_says_so_and_the_next_request_that_works_takes_it_away(searching, page):
    # The connection is gone when the button is pressed.
    page.route('**/to-watch/add/', lambda route: route.abort())
    expect(page.locator('#problem')).to_be_hidden()

    page.get_by_role('button', name='Add to To Watch').click()

    expect(page.locator('#problem')).to_have_text(NO_ANSWER)
    expect(page.locator('#problem')).to_be_visible()
    # Nothing was saved, and the button can be pressed again.
    assert not ToWatchItem.objects.exists()
    expect(page.get_by_role('button', name='Add to To Watch')).to_be_enabled()

    # The connection is back: the next request that works takes the line away.
    page.get_by_label('Search movies and series').fill('made-up again')
    expect(page.locator('#problem')).to_be_hidden()


def test_a_search_with_no_answer_says_so(searching, page):
    page.route(LIVE_SEARCH, lambda route: route.abort())

    page.get_by_label('Search movies and series').fill('made-up again')

    expect(page.locator('#problem')).to_have_text(NO_ANSWER)
    expect(page.get_by_text('Searching…')).to_be_hidden()


def test_an_error_answer_says_something_went_wrong(searching, page):
    page.route(LIVE_SEARCH, lambda route: route.fulfill(status=500, body='Server Error'))

    page.get_by_label('Search movies and series').fill('made-up again')

    expect(page.locator('#problem')).to_have_text(ERROR)
    # The old results stay as they were.
    expect(page.locator('.tile')).to_have_count(1)

    page.unroute(LIVE_SEARCH)
    page.get_by_label('Search movies and series').fill('made-up once more')
    expect(page.locator('#problem')).to_be_hidden()
