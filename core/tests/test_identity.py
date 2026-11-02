"""The look of the app (the spec is Identity/identity.md): always dark, the logo in the header and the tab icon.

The colours themselves are checked by eye in the browser, not here. These tests only check what can break
without anyone noticing: a page that lost its dark setting, a logo that does not link home, a missing file."""

import os
import re

import pytest
from django.contrib.auth.models import User
from django.contrib.staticfiles import finders
from django.test import Client
from django.utils import timezone

from core.models import Profile, Title

# The browser's driver runs inside an event loop, and Django refuses database calls from
# there unless told it is fine. It is fine in a test.
os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')

MADE_UP_MOVIE = {
    'id': 603,
    'title': 'Made-up Movie',
    'release_date': '1999-03-31',
    'poster_path': '/made-up-movie.jpg',
    'overview': 'A made-up story about a movie.',
}
OPEN_PAGES = ['/login/', '/about/']
LOGGED_IN_PAGES = [
    '/',
    '/search/',
    '/movies/',
    '/movies/history/',
    '/series/',
    '/series/watching/',
    '/series/finished/',
    '/series/dropped/',
    '/calendar/',
    '/profile/',
]


@pytest.fixture(autouse=True)
def tmdb_key(settings):
    settings.TMDB_API_KEY = 'made-up-secret-key'


@pytest.fixture
def me(db):
    user = User.objects.create_user(username='made-up-user', password='made-up-password')
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    return user


@pytest.fixture
def client(me):
    client = Client()
    client.force_login(me)
    return client


def test_every_page_is_always_dark(client, respx_mock):
    # A movie page asks TMDB (made up here); a series page saved a moment ago does not.
    respx_mock.get('https://api.themoviedb.org/3/movie/603').respond(json=MADE_UP_MOVIE)
    Title.objects.create(kind='series', tmdb_id=1, title='Made-up Series', episodes_refreshed_at=timezone.now())

    # The login and About pages are open to everyone, so they are checked without logging in.
    pages = [(Client(), url) for url in OPEN_PAGES]
    pages += [(client, url) for url in LOGGED_IN_PAGES + ['/movie/603/', '/series/1/']]

    for visitor, url in pages:
        response = visitor.get(url)
        assert response.status_code == 200, url
        # Without data-theme="dark", Pico follows the computer's light or dark setting.
        assert re.search(r'<html[^>]*data-theme="dark"', response.content.decode()), url


def test_the_header_shows_the_logo_and_links_to_home(client):
    logo = r'<a href="/"[^>]*>\s*<img src="/static/core/logo-couchlog\.svg" alt="Couchlog">\s*</a>'

    assert re.search(logo, Client().get('/login/').content.decode())
    assert re.search(logo, client.get('/').content.decode())
    assert finders.find('core/logo-couchlog.svg')


def menu_marked(html):
    """The names in the header's menu that are marked as the page you are on (hot pink and bold, see couchlog.css)."""
    header = html[html.index('<header'):html.index('</header>')]
    return re.findall(r'<a [^>]*aria-current="page"[^>]*>([^<]+)</a>', header)


@pytest.mark.parametrize(
    ('url', 'marked'),
    [
        ('/search/', ['Search']),
        ('/movies/', ['Movies']),
        ('/movies/history/', ['Movies']),
        ('/series/', ['Series']),
        ('/series/watching/', ['Series']),
        ('/series/finished/', ['Series']),
        ('/series/dropped/', ['Series']),
        ('/calendar/', ['Calendar']),
        ('/profile/', ['Profile']),
        ('/about/', ['About']),
        # Home is the logo, not a name in the menu, and a title's own page is no menu item.
        ('/', []),
        ('/movie/603/', []),
    ],
)
def test_the_menu_marks_the_page_you_are_on(client, respx_mock, url, marked):
    respx_mock.get('https://api.themoviedb.org/3/movie/603').respond(json=MADE_UP_MOVIE)

    assert menu_marked(client.get(url).content.decode()) == marked


def test_the_about_page_is_marked_when_logged_out_too():
    html = Client().get('/about/').content.decode()

    assert menu_marked(html) == ['About']


def test_the_tab_icon_link_points_to_a_file_that_exists(client):
    html = client.get('/').content.decode()

    icon = re.search(r'<link rel="icon" href="/static/([^"]+)"', html)
    assert icon
    assert finders.find(icon.group(1))


def test_our_logo_is_bigger_than_the_tmdb_logo(live_server, page):
    page.goto(f'{live_server.url}/about/')
    page.wait_for_load_state('load')

    ours = page.get_by_role('img', name='Couchlog').bounding_box()
    tmdb = page.get_by_role('img', name='TMDB').bounding_box()

    # Design rule 4: the TMDB credit is shown, but less prominently than the app's own name.
    assert ours['width'] > tmdb['width']
    assert ours['height'] > tmdb['height']
