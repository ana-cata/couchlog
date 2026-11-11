"""The security check (card #99): what the app itself promises, proved on every address it has.

- Every page needs a login, except the few that are meant to be open.
- Every button that changes something only works with a POST that carries Django's form code (CSRF), so another
  website cannot press it for me.
- One account can never read or change another account's history, lists, ratings, notes or time zone.
- Text typed by a person (a note, a search) and names from TMDB are shown as plain text, never run as code.
- A "come back to" address in a form (`next`) can never send someone to another website.

The list of addresses below must name every address in core/urls.py, so a new address cannot be added without
deciding which group it is in (the first test fails until it is).
"""

import datetime

import pytest
import time_machine
from django.contrib.auth.models import User
from django.core import serializers
from django.test import Client
from django.urls import URLPattern, get_resolver

from core.models import (
    DemoEvent,
    DroppedSeries,
    Episode,
    Profile,
    Rating,
    RemovedSeries,
    Title,
    ToWatchItem,
    Watch,
)

# The fixed "today": noon UTC on 28 Oct 2026.
NOW = datetime.datetime(2026, 10, 28, 12, 0, tzinfo=datetime.UTC)
EARLIER = datetime.date(2026, 10, 1)

SECRET_NOTE = 'Only the other account may ever see this note'
OTHER_FILM = 'Film Only The Other Account Has'
DRAMA = [{'id': 18, 'name': 'Drama'}]
EVIL = 'https://evil.example/stolen'

# Open to everyone, logged in or not.
OPEN = {
    'about': '/about/',
    'login': '/login/',
    'demo_start': '/demo/start/',  # "not found" outside the demo
}

# Pages that only read. Each needs a login.
READS = {
    'home': '/',
    'search': '/search/',
    'search_suggestions': '/search/suggestions/',
    'movies': '/movies/',
    'history': '/movies/history/',
    'series': '/series/',
    'series_watching': '/series/watching/',
    'series_finished': '/series/finished/',
    'series_dropped': '/series/dropped/',
    'calendar': '/calendar/',
    'to_watch_removed': '/to-watch/removed/?kind=series',
    'title': '/movie/501/',
}

# Addresses that change data. Each needs a login, a POST and the form code. The profile page is also a page that
# reads (GET), and its form changes the time zone (POST).
CHANGES = {
    'series_drop': '/series/drop/',
    'series_bring_back': '/series/bring-back/',
    'series_remove_all': '/series/remove-all/',
    'series_remove_all_undo': '/series/remove-all/undo/',
    'to_watch_add': '/to-watch/add/',
    'to_watch_collect': '/to-watch/collect/',
    'to_watch_remove': '/to-watch/remove/',
    'to_watch_undo': '/to-watch/undo/',
    'rating_save': '/rating/save/',
    'watched_add': '/watched/add/',
    'episode_watched_add': '/watched/episode/add/',
    'season_watched_add': '/watched/season/add/',
    'season_watched_remove': '/watched/season/remove/',
    'season_watched_again': '/watched/season/again/',
    'season_watched_again_remove': '/watched/season/again/remove/',
    'episodes_watched_up_to': '/watched/up-to/add/',
    'watched_remove': '/watched/remove/',
    'profile': '/profile/',
    'logout': '/logout/',
}

# The two old addresses that only send to their new place. They have no name.
OLD_ADDRESSES = ['/to-watch/', '/history/']


@pytest.fixture(autouse=True)
def clock():
    with time_machine.travel(NOW, tick=False):
        yield


@pytest.fixture(autouse=True)
def no_dates_collected(monkeypatch):
    # Adding a title collects its Calendar dates from TMDB. Nothing here is about that, so it does nothing.
    monkeypatch.setattr('core.views._collect_dates', lambda title: None)


def make_account(name):
    account = User.objects.create_user(username=name, password='made-up-password')
    Profile.objects.create(user=account, timezone='Europe/Lisbon')
    return account


def logged_in(account, **options):
    client = Client(**options)
    client.force_login(account)
    return client


@pytest.fixture
def other(db):
    """Another account with something of every kind: the data the first account must never reach."""
    account = make_account('other-account')
    # Length and genres are saved, so the film's page never asks TMDB.
    film = Title.objects.create(kind='movie', tmdb_id=501, title=OTHER_FILM, runtime=100, genres=DRAMA)
    removed = Title.objects.create(kind='movie', tmdb_id=502, title='Removed Film', runtime=90, genres=DRAMA)
    listed = Title.objects.create(kind='movie', tmdb_id=503, title='Listed Film', runtime=90, genres=DRAMA)
    series = Title.objects.create(kind='series', tmdb_id=601, title='Dropped Series', episodes_refreshed_at=NOW)
    first = Episode.objects.create(title=series, tmdb_id=1, season_number=1, episode_number=1, air_date=EARLIER)
    second = Episode.objects.create(title=series, tmdb_id=2, season_number=1, episode_number=2, air_date=EARLIER)
    gone = Title.objects.create(kind='series', tmdb_id=602, title='Removed Series', episodes_refreshed_at=NOW)

    watch = Watch.objects.create(user=account, title=film, watched_on=EARLIER)
    Rating.objects.create(user=account, title=film, stars=4, note=SECRET_NOTE)
    ToWatchItem.objects.create(user=account, title=removed, removed_at=NOW - datetime.timedelta(seconds=2))
    ToWatchItem.objects.create(user=account, title=listed)
    # The first episode watched twice (so a rewatch can be taken back), the second not at all.
    Watch.objects.create(user=account, title=series, episode=first, watched_on=EARLIER)
    Watch.objects.create(user=account, title=series, episode=first, watched_on=EARLIER)
    DroppedSeries.objects.create(user=account, title=series)
    # A series taken off all lists a moment ago, so its Undo is still possible.
    item = ToWatchItem.objects.create(user=account, title=gone)
    RemovedSeries.objects.create(user=account, title=gone, rows=serializers.serialize('json', [item]))
    item.delete()

    account.film_watch, account.second_episode = watch, second
    return account


def everything_of(account):
    """All of an account's own rows, as they are now."""
    tables = (Profile, Watch, ToWatchItem, DroppedSeries, RemovedSeries, Rating)
    return {table.__name__: list(table.objects.filter(user=account).order_by('id').values()) for table in tables}


def form_aimed_at(other, name):
    """What the button `name` sends when it is pressed for the other account's things."""
    film = {'kind': 'movie', 'tmdb_id': 501}
    series = {'kind': 'series', 'tmdb_id': 601}
    season = {'tmdb_id': 601, 'season': 1}
    return {
        'series_drop': series,
        'series_bring_back': series,
        'series_remove_all': series,
        'series_remove_all_undo': {'kind': 'series', 'tmdb_id': 602},
        'to_watch_add': {'kind': 'movie', 'tmdb_id': 503},
        'to_watch_collect': {'kind': 'movie', 'tmdb_id': 503},
        'to_watch_remove': {'kind': 'movie', 'tmdb_id': 503},
        'to_watch_undo': {'kind': 'movie', 'tmdb_id': 502},
        'rating_save': {**film, 'stars': '1', 'note': 'Written by someone else'},
        'watched_add': {**film, 'watched_on': EARLIER.isoformat()},
        'episode_watched_add': {'episode_id': other.second_episode.id, 'only_this': '1'},
        'season_watched_add': season,
        'season_watched_remove': season,
        'season_watched_again': season,
        'season_watched_again_remove': season,
        'episodes_watched_up_to': {'episode_id': other.second_episode.id},
        'watched_remove': {'watch_id': other.film_watch.id},
        'profile': {'timezone': 'Asia/Tokyo'},
        'logout': {},
    }[name]


def test_every_address_is_in_one_of_the_groups():
    named = {
        pattern.name
        for pattern in get_resolver().url_patterns[-1].url_patterns
        if isinstance(pattern, URLPattern) and pattern.name
    }
    assert named == set(OPEN) | set(READS) | set(CHANGES)


@pytest.mark.parametrize('address', [*READS.values(), *CHANGES.values(), *OLD_ADDRESSES])
@pytest.mark.parametrize('method', ['get', 'post'])
@pytest.mark.django_db
def test_every_address_but_the_open_ones_needs_a_login(client, address, method):
    response = getattr(client, method)(address)

    assert response.status_code == 302
    assert response['Location'].startswith('/login/')


@pytest.mark.django_db
def test_admin_needs_its_own_login(client):
    response = client.get('/admin/')

    assert response.status_code == 302
    assert response['Location'].startswith('/admin/login/')


@pytest.mark.parametrize('name', sorted(set(CHANGES) - {'profile'}))
def test_a_change_cannot_be_made_with_a_link(other, name):
    # A link or an image on another website can only make the browser GET. GET changes nothing here.
    me = make_account('me')
    before = everything_of(me), everything_of(other)

    response = logged_in(me).get(CHANGES[name], form_aimed_at(other, name))

    assert response.status_code == 405
    assert (everything_of(me), everything_of(other)) == before


@pytest.mark.parametrize('name', sorted(CHANGES))
def test_a_change_without_the_form_code_is_refused(other, name):
    # Another website can make the browser POST a form here, but it cannot know the form code.
    me = make_account('me')
    before = everything_of(me), everything_of(other)
    browser = logged_in(me, enforce_csrf_checks=True)

    response = browser.post(CHANGES[name], form_aimed_at(other, name))

    assert response.status_code == 403
    assert (everything_of(me), everything_of(other)) == before


@pytest.mark.django_db
def test_logging_in_without_the_form_code_is_refused():
    make_account('me')
    browser = Client(enforce_csrf_checks=True)

    response = browser.post('/login/', {'username': 'me', 'password': 'made-up-password'})

    assert response.status_code == 403
    assert '_auth_user_id' not in browser.session


@pytest.mark.django_db
def test_starting_a_demo_account_without_the_form_code_is_refused(settings):
    settings.DEMO_MODE = True
    browser = Client(enforce_csrf_checks=True)

    response = browser.post('/demo/start/', {'time_zone': 'UTC'})

    assert response.status_code == 403
    assert not User.objects.exists()


@pytest.mark.parametrize('name', sorted(CHANGES))
def test_one_account_cannot_change_another_accounts_data(other, name):
    # The buttons are pressed with the other account's titles, episodes and watch: only my own rows may change.
    before = everything_of(other)
    me = logged_in(make_account('me'))

    response = me.post(CHANGES[name], form_aimed_at(other, name))

    assert response.status_code in (200, 204, 302)
    assert everything_of(other) == before


@pytest.mark.parametrize('address', [*READS.values(), '/profile/', '/series/601/', '/to-watch/removed/?kind=movie'])
def test_one_account_cannot_read_another_accounts_data(other, address, respx_mock):
    # TMDB is never really asked; the suggestions get an empty answer.
    respx_mock.get(url__regex=r'https://api\.themoviedb\.org/.*').respond(json={'page': 1, 'results': []})
    me = logged_in(make_account('me'))

    page = me.get(address).content.decode()

    assert SECRET_NOTE not in page
    assert 'other-account' not in page
    if address != '/movie/501/':  # the film's own page shows its name to anyone who opens it
        assert OTHER_FILM not in page


def test_the_film_page_does_not_show_another_accounts_watches(other):
    me = logged_in(make_account('me'))

    page = me.get('/movie/501/').content.decode()

    assert 'Watch again' not in page  # what the button says once the film has a watch of mine
    assert 'Mark as watched' in page


@pytest.mark.django_db
def test_a_note_is_shown_as_plain_text():
    me = make_account('me')
    Title.objects.create(kind='movie', tmdb_id=501, title='A Film', runtime=100, genres=DRAMA)
    browser = logged_in(me)
    browser.post('/rating/save/', {'kind': 'movie', 'tmdb_id': 501, 'stars': '', 'note': '<script>alert("note")</script>'})

    page = browser.get('/movie/501/').content.decode()

    assert '<script>alert("note")</script>' not in page
    assert '&lt;script&gt;alert(&quot;note&quot;)&lt;/script&gt;' in page


@pytest.mark.django_db
def test_a_title_name_from_tmdb_is_shown_as_plain_text():
    me = make_account('me')
    film = Title.objects.create(kind='movie', tmdb_id=501, title='<img src=x onerror=alert(1)>', runtime=100)
    ToWatchItem.objects.create(user=me, title=film)

    page = logged_in(me).get('/movies/').content.decode()

    assert '<img src=x onerror=alert(1)>' not in page
    assert '&lt;img src=x onerror=alert(1)&gt;' in page


@pytest.mark.django_db
def test_what_is_typed_in_search_is_shown_as_plain_text(respx_mock):
    respx_mock.get('https://api.themoviedb.org/3/search/multi').respond(json={'page': 1, 'results': []})

    page = logged_in(make_account('me')).get('/search/', {'q': '"><script>alert("q")</script>'}).content.decode()

    assert '<script>alert("q")</script>' not in page
    assert '&lt;script&gt;alert(&quot;q&quot;)&lt;/script&gt;' in page


@pytest.mark.parametrize('evil', [EVIL, '//evil.example/stolen', '/\\evil.example', 'https:evil.example'])
@pytest.mark.parametrize('name', sorted(set(CHANGES) - {'profile', 'logout', 'to_watch_collect'}))
def test_a_button_never_sends_me_to_another_website(other, name, evil):
    # The other account presses its own buttons here, so each one really does its work.
    response = logged_in(other).post(CHANGES[name], {**form_aimed_at(other, name), 'next': evil})

    assert response.status_code == 302
    assert 'evil.example' not in response['Location']
    assert response['Location'].startswith('/')


@pytest.mark.parametrize('evil', [EVIL, '//evil.example/stolen'])
@pytest.mark.django_db
def test_logging_in_never_sends_me_to_another_website(client, evil):
    make_account('me')

    response = client.post(f'/login/?next={evil}', {'username': 'me', 'password': 'made-up-password'})

    assert response.status_code == 302
    assert 'evil.example' not in response['Location']


@pytest.mark.django_db
def test_logging_out_never_sends_me_to_another_website():
    response = logged_in(make_account('me')).post('/logout/', {'next': EVIL})

    assert response.status_code == 302
    assert 'evil.example' not in response['Location']


@pytest.mark.django_db
def test_a_demo_limit_never_sends_me_to_another_website(settings):
    settings.DEMO_MODE = True
    settings.DEMO_CHANGES_PER_DAY = 0
    me = make_account('demo-me')
    Title.objects.create(kind='movie', tmdb_id=501, title='A Film', runtime=100, genres=DRAMA)

    response = logged_in(me).post('/to-watch/add/', {'kind': 'movie', 'tmdb_id': 501, 'next': EVIL})

    assert response.status_code == 302
    assert 'evil.example' not in response['Location']
    assert not ToWatchItem.objects.exists()
    assert not DemoEvent.objects.exists()
