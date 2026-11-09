"""The movie page on a phone: one tap is enough, the page stays where it was, Back never shows an old list, and a saved
movie does not wait for TMDB."""

import os

import pytest
from django.contrib.auth.models import User
from django.test import Client
from playwright.sync_api import expect

from core.models import Profile, Title, Watch

# The browser's driver runs inside an event loop, and Django refuses database calls from
# there unless told it is fine. It is fine in a test.
os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')

MOVIE_URL = 'https://api.themoviedb.org/3/movie/603'
# Made-up TMDB answer. The tests never call the real TMDB.
MADE_UP_MOVIE = {
    'id': 603,
    'title': 'Made-up Movie',
    'release_date': '1999-03-31',
    'poster_path': None,
    'overview': 'A made-up story about a movie.',
}


@pytest.fixture(autouse=True)
def tmdb_key(settings):
    settings.TMDB_API_KEY = 'made-up-secret-key'


def make_user():
    user = User.objects.create_user(username='made-up-user', password='made-up-password')
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    return user


def logged_in_client(db):
    client = Client()
    client.force_login(make_user())
    return client


def log_in(page, live_server):
    page.goto(live_server.url)
    page.get_by_label('Username').fill('made-up-user')
    page.get_by_label('Password').fill('made-up-password')
    page.get_by_role('button', name='Log in').click()
    page.wait_for_url(live_server.url + '/')


def test_one_tap_on_a_phone_adds_one_watch_and_the_page_stays_where_it_was(live_server, browser, respx_mock):
    make_user()
    respx_mock.get(MOVIE_URL).respond(json=MADE_UP_MOVIE)
    context = browser.new_context(viewport={'width': 390, 'height': 400}, has_touch=True, is_mobile=True)
    page = context.new_page()
    log_in(page, live_server)
    page.goto(live_server.url + '/movie/603/')
    page.wait_for_load_state('load')
    page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
    assert page.evaluate('window.scrollY') > 0

    page.get_by_role('button', name='Mark as watched').tap()

    expect(page.get_by_role('button', name='Watch again')).to_be_visible()
    # htmx moves the page just after the swap, so give it the time to do so.
    page.wait_for_timeout(200)
    assert page.evaluate('window.scrollY') > 0
    assert Watch.objects.count() == 1
    context.close()


def test_a_page_the_phone_brings_back_from_memory_is_loaded_again(live_server, page):
    """A real frozen page cannot be made in the test browser, so this sends the event the browser sends for one."""
    make_user()
    log_in(page, live_server)
    page.wait_for_load_state('load')
    page.evaluate('window.stillTheOldPage = true')

    with page.expect_navigation():
        page.evaluate("window.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true}))")

    assert page.evaluate('window.stillTheOldPage') is None


def test_the_button_says_saving_and_locks_while_the_server_works(db, respx_mock):
    respx_mock.get(MOVIE_URL).respond(json=MADE_UP_MOVIE)

    html = logged_in_client(db).get('/movie/603/').content.decode()

    assert 'class="watched-form" hx-boost="true" hx-push-url="false" hx-disabled-elt="find button"' in html
    assert '<span class="idle">Mark as watched</span><span class="busy">Saving…</span>' in html


def test_a_saved_movie_page_does_not_ask_tmdb(db, respx_mock):
    """No TMDB answer is made up here, so a call to TMDB would fail the test."""
    Title.objects.create(
        kind='movie',
        tmdb_id=603,
        title='Saved Movie',
        year='1999',
        overview='A saved story.',
        runtime=100,
        genres=[{'id': 18, 'name': 'Drama'}],
    )

    html = logged_in_client(db).get('/movie/603/').content.decode()

    assert 'Saved Movie' in html
    assert 'A saved story.' in html
    assert '1999 · Movie · 1h 40min · Drama' in html
    assert 'Mark as watched' in html


def test_a_saved_movie_without_its_length_and_genres_still_reads_tmdb(db, respx_mock):
    Title.objects.create(kind='movie', tmdb_id=603, title='Old Saved Movie')
    route = respx_mock.get(MOVIE_URL).respond(json=MADE_UP_MOVIE)

    html = logged_in_client(db).get('/movie/603/').content.decode()

    assert route.called
    assert 'A made-up story about a movie.' in html
