"""Share a title (feature 20, card #122). A title's page has a Share button whose link is the title's TMDB page. On a phone
it opens the phone's share menu with the title's name and that link; on a computer it copies the link and says "Link
copied"; without JavaScript it is a plain link to the TMDB page. Nothing is saved and Couchlog's server is not asked."""

import os

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone
from playwright.sync_api import expect

from core.models import Profile, Title

# The browser's driver runs inside an event loop, and Django refuses database calls from
# there unless told it is fine. It is fine in a test.
os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')

MOVIE_LINK = 'https://www.themoviedb.org/movie/603'
SERIES_LINK = 'https://www.themoviedb.org/tv/1396'


@pytest.fixture(autouse=True)
def tmdb_key(settings):
    settings.TMDB_API_KEY = 'made-up-secret-key'


def make_user():
    user = User.objects.create_user(username='made-up-user', password='made-up-password')
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    return user


def saved_movie(year='1999'):
    """A movie saved with its length and genres, so its page never asks TMDB."""
    return Title.objects.create(
        kind='movie', tmdb_id=603, title='Made-up Movie', year=year, runtime=136, genres=[{'id': 18, 'name': 'Drama'}]
    )


def saved_series():
    """A series whose episodes were just refreshed, so its page never asks TMDB."""
    return Title.objects.create(
        kind='series', tmdb_id=1396, title='Made-up Series', year='2008', episodes_refreshed_at=timezone.now()
    )


def logged_in_client():
    client = Client()
    client.force_login(make_user())
    return client


def share_link(page_html):
    """The Share link's opening tag on the page."""
    start = page_html.index('data-share ')
    return page_html[page_html.rindex('<a ', 0, start) : page_html.index('>', start)]


@pytest.mark.django_db
def test_a_movie_shares_its_tmdb_movie_page():
    saved_movie()
    html = logged_in_client().get('/movie/603/').content.decode()
    link = share_link(html)
    assert f'href="{MOVIE_LINK}"' in link
    assert 'data-share-text="Made-up Movie (1999)"' in link


@pytest.mark.django_db
def test_a_series_shares_its_tmdb_tv_page():
    saved_series()
    html = logged_in_client().get('/series/1396/').content.decode()
    link = share_link(html)
    assert f'href="{SERIES_LINK}"' in link
    assert 'data-share-text="Made-up Series (2008)"' in link


@pytest.mark.django_db
def test_a_title_with_no_year_shares_only_its_name():
    saved_movie(year='')
    link = share_link(logged_in_client().get('/movie/603/').content.decode())
    assert 'data-share-text="Made-up Movie"' in link


@pytest.mark.django_db
def test_without_javascript_share_is_a_plain_link_to_the_tmdb_page_in_a_new_tab():
    saved_movie()
    link = share_link(logged_in_client().get('/movie/603/').content.decode())
    # A normal link: no form, nothing sent to Couchlog. It opens TMDB in a new tab.
    assert link.startswith('<a ')
    assert 'target="_blank"' in link and 'rel="noopener"' in link


@pytest.mark.django_db
def test_share_is_with_the_small_buttons_under_the_poster():
    saved_movie()
    html = logged_in_client().get('/movie/603/').content.decode()
    actions = html[html.index('class="poster-actions"') : html.index('tags-section')]
    assert 'data-share ' in actions


# In a real browser.


def log_in(page, live_server):
    page.route('https://image.tmdb.org/**', lambda route: route.abort())
    page.goto(live_server.url)
    page.get_by_label('Username').fill('made-up-user')
    page.get_by_label('Password').fill('made-up-password')
    page.get_by_role('button', name='Log in').click()
    page.wait_for_url(live_server.url + '/')


def test_on_a_computer_share_copies_the_link_and_says_so(live_server, browser):
    make_user()
    saved_movie()
    context = browser.new_context(permissions=['clipboard-read', 'clipboard-write'])
    # Chrome and Edge on Windows have a share menu too. With a mouse it is still not used: the link is copied.
    context.add_init_script('navigator.share = data => { window.shared = data; return Promise.resolve(); };')
    page = context.new_page()
    log_in(page, live_server)
    page.goto(live_server.url + '/movie/603/')
    asked = []
    page.on('request', lambda request: asked.append(request.url))
    page.wait_for_load_state('networkidle')
    asked.clear()

    page.get_by_role('button', name='Share').click()

    expect(page.locator('.share-said')).to_have_text('Link copied')
    assert page.evaluate('navigator.clipboard.readText()') == MOVIE_LINK
    assert page.evaluate('window.shared') is None
    # The page stayed, no new tab opened, and nothing was sent anywhere.
    assert page.url == live_server.url + '/movie/603/'
    assert context.pages == [page]
    assert asked == []
    # The words go away again after a few seconds.
    expect(page.get_by_text('Link copied')).to_have_count(0, timeout=5000)
    context.close()


def test_on_a_phone_share_opens_the_share_menu_with_the_name_and_link(live_server, browser):
    make_user()
    saved_series()
    context = browser.new_context(viewport={'width': 390, 'height': 700}, has_touch=True, is_mobile=True)
    # The phone's share menu, made up: it remembers what it was given.
    context.add_init_script('navigator.share = data => { window.shared = data; return Promise.resolve(); };')
    page = context.new_page()
    log_in(page, live_server)
    page.goto(live_server.url + '/series/1396/')

    page.get_by_role('button', name='Share').tap()

    page.wait_for_function('window.shared !== undefined')
    assert page.evaluate('window.shared') == {'text': 'Made-up Series (2008)', 'url': SERIES_LINK}
    assert page.url == live_server.url + '/series/1396/'
    assert context.pages == [page]
    context.close()


def test_closing_the_share_menu_without_picking_does_nothing(live_server, browser):
    make_user()
    saved_movie()
    context = browser.new_context(has_touch=True, is_mobile=True)
    context.add_init_script(
        'navigator.share = () => { window.asked = true; return Promise.reject(new DOMException("closed", "AbortError")); };'
    )
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(error))
    log_in(page, live_server)
    page.goto(live_server.url + '/movie/603/')

    page.get_by_role('button', name='Share').tap()

    page.wait_for_function('window.asked === true')
    expect(page.locator('.share-said')).to_have_text('')
    assert page.url == live_server.url + '/movie/603/'
    assert errors == []
    context.close()


def test_where_the_browser_can_neither_share_nor_copy_the_link_opens_tmdb(live_server, browser):
    # Like a phone opening the PC by its plain http:// address: no share menu and no clipboard.
    make_user()
    saved_movie()
    context = browser.new_context()
    context.add_init_script(
        'Object.defineProperty(navigator, "clipboard", {value: undefined});'
        'Object.defineProperty(navigator, "share", {value: undefined});'
    )
    context.route('https://www.themoviedb.org/**', lambda route: route.fulfill(body='made-up TMDB page'))
    page = context.new_page()
    log_in(page, live_server)
    page.goto(live_server.url + '/movie/603/')

    with context.expect_page() as opened:
        page.get_by_role('button', name='Share').click()

    assert opened.value.url == MOVIE_LINK
    assert page.url == live_server.url + '/movie/603/'
    context.close()
