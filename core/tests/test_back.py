"""The "← Back" link on a title's page: it goes back to the page the title was opened from.

Going back is the browser's own history, so most of this is tested in a real browser. The link itself points to
Search, which is where a title opened directly (no page before it in this tab) lands. Buttons on the page that used to
reload it (Mark as watched, Rate, Stop watching ...) must not add history entries, or one press of Back would only
return to the same page."""

import datetime
import os
import re

import pytest
from django.contrib.auth.models import User
from django.test import Client
from playwright.sync_api import expect

from core.models import Profile, Title, ToWatchItem, Watch

# The browser's driver runs inside an event loop, and Django refuses database calls from
# there unless told it is fine. It is fine in a test.
os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')

# Made-up TMDB answers. The tests never call the real TMDB.
MADE_UP_MOVIE = {
    'id': 603,
    'title': 'Made-up Movie',
    'release_date': '1999-03-31',
    'poster_path': '/made-up-movie.jpg',
    'overview': 'A made-up story about a movie.',
}
OTHER_MOVIE = {**MADE_UP_MOVIE, 'id': 604, 'title': 'Other Made-up Movie'}
BACK = '← Back'


@pytest.fixture(autouse=True)
def tmdb_key(settings):
    settings.TMDB_API_KEY = 'made-up-secret-key'


def make_user():
    user = User.objects.create_user(username='made-up-user', password='made-up-password')
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    return user


def log_in(page, live_server):
    page.goto(live_server.url)
    page.get_by_label('Username').fill('made-up-user')
    page.get_by_label('Password').fill('made-up-password')
    page.get_by_role('button', name='Log in').click()


def open_tile(page):
    """Click the (only) tile, then wait for the page to finish loading: htmx starts after that, and a button
    pressed before it would send the form the old way."""
    page.locator('.tile').click()
    page.wait_for_load_state('load')


def test_a_title_page_says_back_and_the_link_goes_to_search(db, respx_mock):
    make_user()
    client = Client()
    client.login(username='made-up-user', password='made-up-password')
    respx_mock.get('https://api.themoviedb.org/3/movie/603').respond(json=MADE_UP_MOVIE)

    html = client.get('/movie/603/').content.decode()

    # The link is what a page opened directly follows, and what is followed without JavaScript.
    assert re.search(r'<a href="/search/" data-back>← Back</a>', html.replace('&larr;', '←'))
    assert 'Back to search' not in html


def test_back_from_search_keeps_what_i_typed_and_its_results(live_server, page, respx_mock):
    make_user()
    respx_mock.get('https://api.themoviedb.org/3/search/multi').respond(
        json={'page': 1, 'results': [{'media_type': 'movie', **MADE_UP_MOVIE}]}
    )
    respx_mock.get('https://api.themoviedb.org/3/movie/603').respond(json=MADE_UP_MOVIE)
    page.route('https://image.tmdb.org/**', lambda route: route.abort())
    log_in(page, live_server)

    page.get_by_role('link', name='Search', exact=True).click()
    page.wait_for_load_state('load')
    page.get_by_role('searchbox').press_sequentially('made-up')
    expect(page.locator('.tile')).to_have_count(1)

    open_tile(page)
    expect(page.get_by_role('heading', name='Made-up Movie')).to_be_visible()
    page.get_by_role('link', name=BACK, exact=True).click()

    expect(page.get_by_role('heading', name='Search')).to_be_visible()
    expect(page.get_by_role('searchbox')).to_have_value('made-up')
    expect(page.locator('.tile')).to_have_count(1)


def test_back_from_the_movies_to_watch_tab_and_from_history(live_server, page, respx_mock):
    user = make_user()
    ToWatchItem.objects.create(user=user, title=Title.objects.create(kind='movie', tmdb_id=603, title='Made-up Movie'))
    seen = Title.objects.create(kind='movie', tmdb_id=604, title='Other Made-up Movie')
    Watch.objects.create(user=user, title=seen, watched_on=datetime.date(2026, 10, 1))
    respx_mock.get('https://api.themoviedb.org/3/movie/603').respond(json=MADE_UP_MOVIE)
    respx_mock.get('https://api.themoviedb.org/3/movie/604').respond(json=OTHER_MOVIE)
    page.route('https://image.tmdb.org/**', lambda route: route.abort())
    log_in(page, live_server)

    page.get_by_role('link', name='Movies', exact=True).click()
    open_tile(page)
    expect(page.get_by_role('heading', name='Made-up Movie')).to_be_visible()
    page.get_by_role('link', name=BACK, exact=True).click()
    expect(page).to_have_url(live_server.url + '/movies/')
    expect(page.locator('.tile')).to_contain_text('Made-up Movie')

    page.get_by_role('link', name='History', exact=True).click()
    open_tile(page)
    expect(page.get_by_role('heading', name='Other Made-up Movie')).to_be_visible()
    page.get_by_role('link', name=BACK, exact=True).click()
    expect(page).to_have_url(live_server.url + '/movies/history/')
    expect(page.locator('.tile')).to_contain_text('Other Made-up Movie')


def test_one_press_of_back_is_enough_after_marking_watching_again_and_rating(live_server, page, respx_mock):
    user = make_user()
    ToWatchItem.objects.create(user=user, title=Title.objects.create(kind='movie', tmdb_id=603, title='Made-up Movie'))
    respx_mock.get('https://api.themoviedb.org/3/movie/603').respond(json=MADE_UP_MOVIE)
    page.route('https://image.tmdb.org/**', lambda route: route.abort())
    log_in(page, live_server)

    page.get_by_role('link', name='Movies', exact=True).click()
    open_tile(page)
    entries = page.evaluate('history.length')

    # Each of these used to reload the page and add a history entry. Now the page changes in place.
    page.get_by_role('button', name='Mark as watched').click()
    expect(page.get_by_text('Marked “Made-up Movie” as watched.')).to_be_visible()
    page.get_by_role('button', name='Watch again').click()
    expect(page.get_by_text('Watched 2 times')).to_be_visible()
    page.get_by_text('Rate it or add a note').click()
    page.get_by_label('4 out of 5 stars').check()
    page.get_by_role('button', name='Save', exact=True).click()
    expect(page.get_by_text('Your rating: ★★★★☆')).to_be_visible()
    page.get_by_role('button', name='Remove this watch').first.click()
    expect(page.get_by_role('button', name='Mark as not watched')).to_be_visible()
    assert page.evaluate('history.length') == entries

    # One press of Back, and I am on the Movies page again (the film left To Watch only once it was watched).
    page.get_by_role('link', name=BACK, exact=True).click()
    expect(page).to_have_url(live_server.url + '/movies/')


def test_one_press_of_back_is_enough_after_stopping_watching_and_bringing_a_series_back(
    live_server, page, respx_mock
):
    user = make_user()
    show = Title.objects.create(kind='series', tmdb_id=1399, title='Made-up Series', year='2011')
    ToWatchItem.objects.create(user=user, title=show)
    respx_mock.get('https://api.themoviedb.org/3/tv/1399').respond(
        json={'id': 1399, 'name': 'Made-up Series', 'seasons': [{'season_number': 1}]}
    )
    episode = {'id': 6001, 'season_number': 1, 'episode_number': 1, 'name': 'Made-up pilot', 'air_date': '2011-04-17'}
    respx_mock.get('https://api.themoviedb.org/3/tv/1399/season/1').respond(
        json={'season_number': 1, 'episodes': [episode]}
    )
    page.route('https://image.tmdb.org/**', lambda route: route.abort())
    log_in(page, live_server)

    page.get_by_role('link', name='Series', exact=True).click()
    page.get_by_role('link', name='To Watch', exact=True).click()
    open_tile(page)
    expect(page.get_by_text('Made-up pilot')).to_be_visible()
    entries = page.evaluate('history.length')

    page.get_by_role('button', name='Stop watching').click()
    expect(page.get_by_role('button', name='Bring back')).to_be_visible()
    page.get_by_role('button', name='Bring back').click()
    expect(page.get_by_role('button', name='Stop watching')).to_be_visible()
    assert page.evaluate('history.length') == entries

    page.get_by_role('link', name=BACK, exact=True).click()
    expect(page).to_have_url(live_server.url + '/series/')


def test_a_title_opened_directly_goes_back_to_search(live_server, page, context, respx_mock):
    user = make_user()
    ToWatchItem.objects.create(user=user, title=Title.objects.create(kind='movie', tmdb_id=603, title='Made-up Movie'))
    respx_mock.get('https://api.themoviedb.org/3/movie/603').respond(json=MADE_UP_MOVIE)
    page.route('https://image.tmdb.org/**', lambda route: route.abort())
    context.route('https://image.tmdb.org/**', lambda route: route.abort())
    log_in(page, live_server)

    # Typed into the address bar (no page before it), although this tab has history from logging in.
    page.goto(live_server.url + '/movie/603/')
    page.wait_for_load_state('load')
    page.get_by_role('link', name=BACK, exact=True).click()
    expect(page).to_have_url(live_server.url + '/search/')

    # Opened in a new tab (Ctrl+click on a tile): the Movies page is its referrer, but the tab has nothing to go back to.
    page.get_by_role('link', name='Movies', exact=True).click()
    with context.expect_page() as new_tab:
        page.locator('.tile').click(modifiers=['ControlOrMeta'])
    other = new_tab.value
    other.wait_for_load_state('load')
    other.get_by_role('link', name=BACK, exact=True).click()
    expect(other).to_have_url(live_server.url + '/search/')
