import datetime

import pytest
import time_machine
from django.contrib.auth.models import User

from core.models import Profile

# Every empty list speaks to someone using Couchlog, not to a developer (card #116): no command names, no "TMDB".
# The texts themselves are checked with each page's own tests; this file checks them all together for code words.

NOW = datetime.datetime(2026, 11, 16, 12, 0, tzinfo=datetime.UTC)
SEARCH_URL = 'https://api.themoviedb.org/3/search/multi'
CODE_WORDS = ['refresh_calendar', 'command', '<code>', 'TMDB']

# Each empty list, with words from its text and the link it offers as the next step.
EMPTY_LISTS = [
    ('/', 'Nothing from your lists comes out in the next 7 days.', 'href="/calendar/"'),
    ('/', 'Up Next shows the next episode of each series', 'href="/search/"'),
    ('/movies/', 'Keep the movies you want to see here.', 'href="/search/"'),
    ('/series/', 'Keep the series you want to see here.', 'href="/search/"'),
    ('/movies/history/', 'Every movie you mark as watched is kept here', 'href="/search/"'),
    ('/series/watching/', 'A series shows up here once you mark one of its episodes as watched.', 'href="/search/"'),
    ('/series/finished/', 'watched to the end land here.', 'href="/series/watching/"'),
    ('/series/dropped/', 'A series you stop watching moves here.', 'href="/series/watching/"'),
    ('/calendar/', 'Nothing coming up.', 'href="/search/"'),
]


@pytest.fixture(autouse=True)
def fixed_today():
    with time_machine.travel(NOW, tick=False):
        yield


@pytest.fixture
def client(client, db, settings):
    settings.TMDB_API_KEY = 'made-up-secret-key'
    user = User.objects.create_user(username='made-up-user', password='made-up-password')
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    client.force_login(user)
    return client


@pytest.mark.parametrize(('url', 'text', 'link'), EMPTY_LISTS)
def test_an_empty_list_says_what_it_is_for_and_links_to_the_next_step(client, url, text, link):
    html = client.get(url).content.decode()

    assert text in html
    assert link in html


@pytest.mark.parametrize('url', sorted({url for url, _, _ in EMPTY_LISTS}))
def test_no_empty_list_shows_code_words(client, url):
    html = client.get(url).content.decode()

    for word in CODE_WORDS:
        assert word not in html


def test_a_search_with_no_results_says_what_to_try_without_code_words(client, respx_mock):
    respx_mock.get(SEARCH_URL).respond(json={'page': 1, 'results': []})

    html = client.get('/search/', {'q': 'zzzz'}).content.decode()

    assert 'Nothing found for “zzzz”. Check the spelling, or try fewer words or the original title.' in html
    for word in CODE_WORDS:
        assert word not in html
