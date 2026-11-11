"""The public demo (card #98, docs/demo.md): throwaway accounts with sample titles, the limits, and demo mode off.

Made-up TMDB answers for the sample titles, and a fixed "today".
"""

import datetime
import runpy

import httpx
import pytest
import time_machine
from django.conf import settings as django_settings
from django.contrib.auth.models import User
from django.test import Client

from core import demo, tvmaze
from core.models import DemoEvent, Profile, Title, ToWatchItem, Watch
from core.tests.test_production_settings import run_python

NOW = datetime.datetime(2026, 11, 11, 12, 0, tzinfo=datetime.UTC)
TODAY = NOW.date()
TMDB = 'https://api.themoviedb.org/3'
TVMAZE = 'https://api.tvmaze.com'
NOTICE = 'This product uses the TMDB API but is not endorsed or certified by TMDB.'

MOVIES = {
    278: ('The Shawshank Redemption', '1994-09-23'),
    129: ('Spirited Away', '2001-07-20'),
    496243: ('Parasite', '2019-05-30'),
    666277: ('Past Lives', '2023-06-02'),
    1170608: ('Dune: Part Three', '2026-12-15'),  # in cinemas after "today"
    1386618: ('Black Panther 3', '2028-12-13'),  # in cinemas long after "today"
    700: ('Made-up Extra Movie', '2020-01-01'),  # not a sample: for adding one more
}
# name, TMDB status, the air dates of season 1's episodes
SERIES = {
    67070: ('Fleabag', 'Ended', ['2016-07-21', '2016-07-28', '2016-08-04']),
    95396: ('Severance', 'Returning Series', ['2022-02-18', '2022-02-25', '2022-03-04', '2022-03-11', '2022-03-18']),
    153312: ('Tulsa King', 'Returning Series', ['2026-10-30', '2026-11-06', '2026-11-08', '2026-11-13', '2026-11-20']),
    87108: ('Chernobyl', 'Ended', ['2019-05-06', '2019-05-13']),
    84773: ('The Rings of Power', 'Returning Series', ['2026-11-18', '2026-11-25']),
}


def made_up_tmdb(request):
    """A made-up TMDB: answers for the sample titles, and one search result."""
    parts = request.url.path.removeprefix('/3/').split('/')
    if parts == ['search', 'multi']:
        return httpx.Response(200, json={'results': [{'media_type': 'movie', 'id': 700, 'title': 'Made-up Extra Movie'}]})
    if parts[0] == 'movie':
        tmdb_id = int(parts[1])
        name, date = MOVIES[tmdb_id]
        moment = f'{date}T00:00:00.000Z'
        release_dates = {'results': [{'iso_3166_1': 'US', 'release_dates': [{'type': 3, 'release_date': moment}]}]}
        movie = {'id': tmdb_id, 'title': name, 'release_date': date, 'runtime': 120, 'genres': [{'id': 18, 'name': 'Drama'}]}
        return httpx.Response(200, json={**movie, 'release_dates': release_dates})
    tmdb_id = int(parts[1])
    name, status, dates = SERIES[tmdb_id]
    if len(parts) == 2:
        series = {'id': tmdb_id, 'name': name, 'first_air_date': dates[0], 'status': status}
        return httpx.Response(200, json={**series, 'seasons': [{'season_number': 1}], 'external_ids': {}})
    episodes = [
        {'id': tmdb_id * 100 + number, 'season_number': 1, 'episode_number': number, 'name': f'Episode {number}',
         'air_date': date, 'runtime': 30}
        for number, date in enumerate(dates, start=1)
    ]
    return httpx.Response(200, json={'episodes': episodes})


@pytest.fixture(autouse=True)
def clock():
    with time_machine.travel(NOW, tick=False) as traveller:
        yield traveller


@pytest.fixture
def tmdb_route(respx_mock, settings):
    settings.TMDB_API_KEY = 'made-up-secret-key'
    return respx_mock.route(host='api.themoviedb.org').mock(side_effect=made_up_tmdb)


@pytest.fixture
def demo_on(settings, db, tmdb_route):
    settings.DEMO_MODE = True
    return tmdb_route


def start(client=None, time_zone='Europe/Lisbon'):
    """Press Try the demo in a new browser (or `client`). Returns the browser, signed in, and the answer."""
    client = client or Client()
    response = client.post('/demo/start/', {'time_zone': time_zone})
    return client, response


def account_of(client):
    return User.objects.get(id=client.session['_auth_user_id'])


def watches(user, kind):
    return {watch.title.title: watch.watched_on for watch in Watch.objects.filter(user=user, title__kind=kind)}


# Demo mode off


@pytest.mark.django_db
def test_with_demo_mode_off_the_login_page_is_the_password_form():
    page = Client().get('/login/').content.decode()

    assert 'type="password"' in page
    assert 'Try the demo' not in page and 'This is a demo' not in page


@pytest.mark.django_db
def test_with_demo_mode_off_there_is_no_demo_button_and_admin_works():
    client = Client()

    assert client.post('/demo/start/').status_code == 404
    assert User.objects.count() == 0
    assert client.get('/admin/').status_code == 302  # to the admin's own login, as before
    assert client.get('/admin/login/').status_code == 200


def test_with_demo_mode_off_nothing_is_counted_and_tvmaze_is_asked(db, tmdb_route, respx_mock):
    user = User.objects.create_user(username='made-up-user')
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    client = Client()
    client.force_login(user)
    respx_mock.get(f'{TVMAZE}/shows/1/episodes').respond(json=[])

    for _ in range(3):
        client.get('/search/', {'q': 'made-up'})
    client.post('/to-watch/add/', {'kind': 'movie', 'tmdb_id': 700})

    assert DemoEvent.objects.count() == 0
    assert tvmaze.get_upcoming_episodes(1, TODAY) == []


def test_the_app_is_not_in_demo_mode_unless_the_setting_says_so():
    result = run_python('from django.conf import settings; print(settings.DEMO_MODE)', DEMO_MODE='')

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'False'


# The safety catch

REAL_COUCHLOG_SETTINGS = {
    'R2_ACCOUNT_ID': '',
    'R2_ACCESS_KEY_ID': '',
    'R2_SECRET_ACCESS_KEY': '',
    'R2_BUCKET': '',
    'CLOUDFLARE_ACCESS_TEAM_DOMAIN': '',
    'CLOUDFLARE_ACCESS_AUD': '',
    'CLOUDFLARE_ACCESS_ADDRESS': '',
}
CLOUDFLARE_SIGN_IN = {
    'CLOUDFLARE_ACCESS_TEAM_DOMAIN': 'made-up.cloudflareaccess.com',
    'CLOUDFLARE_ACCESS_AUD': 'made-up-aud',
    'CLOUDFLARE_ACCESS_ADDRESS': 'couchlog.example.com',
}


@pytest.mark.parametrize(
    'found',
    [{'R2_ACCOUNT_ID': 'x'}, {'R2_ACCESS_KEY_ID': 'x'}, {'R2_SECRET_ACCESS_KEY': 'x'}, {'R2_BUCKET': 'x'}, CLOUDFLARE_SIGN_IN],
)
def test_the_app_refuses_to_start_in_demo_mode_with_backup_keys_or_the_cloudflare_sign_in(found):
    result = run_python(
        'import django; django.setup()', DEMO_MODE='true', **{**REAL_COUCHLOG_SETTINGS, **found}
    )

    assert result.returncode != 0
    assert 'DEMO_MODE is on' in result.stderr


def test_the_demo_starts_without_them():
    result = run_python(
        'from django.conf import settings; print(settings.DEMO_MODE)', DEMO_MODE='true', **REAL_COUCHLOG_SETTINGS
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'True'


# The login page, /admin/ and the banner


def test_in_the_demo_the_login_page_is_only_the_demo_button(demo_on):
    page = Client().get('/login/').content.decode()

    assert 'Try the demo' in page and 'action="/demo/start/"' in page
    assert 'type="password"' not in page and 'name="username"' not in page


def test_in_the_demo_a_username_and_password_sent_to_the_login_page_do_nothing(demo_on):
    User.objects.create_user(username='made-up-user', password='made-up-password')
    client = Client()

    client.post('/login/', {'username': 'made-up-user', 'password': 'made-up-password'})

    assert '_auth_user_id' not in client.session
    assert client.get('/').status_code == 302


@pytest.mark.parametrize('path', ['/admin/', '/admin/login/', '/admin/auth/user/'])
def test_in_the_demo_admin_does_not_exist(demo_on, path):
    visitor, _ = start()

    assert Client().get(path).status_code == 404
    assert visitor.get(path).status_code == 404


def test_the_banner_is_on_every_page_of_the_demo(demo_on):
    visitor, _ = start()

    for page in ['/login/', '/about/']:
        assert 'This is a demo of Couchlog' in Client().get(page).content.decode()
    for page in ['/', '/movies/', '/series/watching/', '/calendar/', '/profile/']:
        content = visitor.get(page).content.decode()
        assert 'This is a demo of Couchlog' in content and 'href="https://github.com/ana-cata/couchlog"' in content


def test_the_about_page_of_the_demo_says_what_it_stores_and_keeps_the_tmdb_credit(demo_on):
    page = Client().get('/about/').content.decode()

    assert NOTICE in page and 'tmdb-logo.svg' in page
    assert 'It stores no email and no IP address, and keeps no backups.' in page
    assert 'Each account is deleted after 24 hours' in page
    assert 'tvmaze' not in page.lower()


# Try the demo: a new account with the sample data


def test_try_the_demo_makes_an_account_with_no_password_and_signs_in(demo_on):
    visitor, response = start()

    assert response.status_code == 302 and response['Location'] == '/'
    user = account_of(visitor)
    assert user.username.startswith('demo-')
    assert not user.has_usable_password()
    assert user.email == ''
    # The time zone is chosen, so Home opens and not the time zone step.
    assert Profile.objects.get(user=user).timezone == 'Europe/Lisbon'
    assert visitor.get('/').status_code == 200


def test_a_time_zone_that_is_not_real_becomes_utc(demo_on):
    visitor, _ = start(time_zone='Made/Up')

    assert Profile.objects.get(user=account_of(visitor)).timezone == 'UTC'


def test_a_new_account_gets_the_sample_data_dated_from_today(demo_on):
    visitor, _ = start()
    user = account_of(visitor)

    assert watches(user, 'movie') == {
        'The Shawshank Redemption': TODAY - datetime.timedelta(days=2),
        'Spirited Away': TODAY - datetime.timedelta(days=9),
        'Parasite': None,
    }
    on_list = set(ToWatchItem.objects.filter(user=user, removed_at=None).values_list('title__title', flat=True))
    assert on_list == {'Past Lives', 'Dune: Part Three', 'Black Panther 3', 'Chernobyl', 'The Rings of Power'}
    # Fleabag: every episode, the last 20 days ago. Severance: the first 4. Tulsa King: the 3 aired, the last yesterday.
    episodes = Watch.objects.filter(user=user, episode__isnull=False)
    fleabag = episodes.filter(title__tmdb_id=67070).order_by('episode__episode_number')
    assert [watch.watched_on for watch in fleabag] == [TODAY - datetime.timedelta(days=days) for days in (22, 21, 20)]
    assert episodes.filter(title__tmdb_id=95396).count() == 4
    tulsa = episodes.filter(title__tmdb_id=153312)
    assert sorted(watch.episode.episode_number for watch in tulsa) == [1, 2, 3]
    assert max(watch.watched_on for watch in tulsa) == TODAY - datetime.timedelta(days=1)


def test_the_sample_series_land_in_the_right_tabs_and_the_calendar_is_not_empty(demo_on):
    visitor, _ = start()

    assert 'Fleabag' in visitor.get('/series/finished/').content.decode()
    watching = visitor.get('/series/watching/').content.decode()
    assert 'Severance' in watching and 'Tulsa King' in watching
    calendar = visitor.get('/calendar/').content.decode()
    assert 'Tulsa King' in calendar and 'The Rings of Power' in calendar and 'Dune: Part Three' in calendar
    assert 'Black Panther 3' in calendar


def test_today_is_the_visitors_own_today(demo_on):
    # 12:00 UTC is already the next day at UTC+14.
    visitor, _ = start(time_zone='Pacific/Kiritimati')

    shawshank = Watch.objects.get(user=account_of(visitor), title__tmdb_id=278)
    assert shawshank.watched_on == TODAY + datetime.timedelta(days=1) - datetime.timedelta(days=2)


def test_only_the_first_account_asks_tmdb_for_the_samples(demo_on):
    start()
    asked = demo_on.call_count

    start()

    assert asked > 0
    assert demo_on.call_count == asked
    assert Title.objects.count() == 11


def test_tmdb_not_answering_shows_a_friendly_message_and_makes_no_account(settings, db, respx_mock):
    settings.DEMO_MODE = True
    settings.TMDB_API_KEY = 'made-up-secret-key'
    respx_mock.route(host='api.themoviedb.org').respond(500)

    _, response = start()

    assert response.status_code == 200
    assert demo.SAMPLES_UNREACHABLE in response.content.decode()
    assert User.objects.count() == 0
    assert not DemoEvent.objects.filter(kind=DemoEvent.Kind.ACCOUNT).exists()


# Two visitors


def test_two_visitors_get_separate_accounts_and_cannot_see_each_others_changes(demo_on):
    first, _ = start()
    second, _ = start(Client())
    first_user, second_user = account_of(first), account_of(second)
    assert first_user != second_user

    first.post('/watched/add/', {'kind': 'movie', 'tmdb_id': 666277, 'watched_on': TODAY.isoformat()})
    first.post('/to-watch/add/', {'kind': 'movie', 'tmdb_id': 700})

    assert 'Past Lives' in first.get('/movies/history/').content.decode()
    assert 'Past Lives' not in second.get('/movies/history/').content.decode()
    assert 'Made-up Extra Movie' not in second.get('/movies/').content.decode()
    assert first_user.username not in second.get('/profile/').content.decode()
    # Nor take back what the other one did.
    watch = Watch.objects.get(user=first_user, title__tmdb_id=666277)
    second.post('/watched/remove/', {'watch_id': watch.id})
    assert Watch.objects.filter(id=watch.id).exists()


# The limits


def test_a_visitor_has_a_limited_number_of_searches_an_hour(demo_on, settings, clock):
    settings.DEMO_SEARCHES_PER_HOUR = 2
    visitor, _ = start()
    searches = demo_on.calls

    def search(client):
        """The search page, and whether TMDB was asked for it."""
        before = len(searches)
        page = client.get('/search/', {'q': 'made-up'}).content.decode()
        return page, len(searches) > before

    for _ in range(2):
        page, asked_tmdb = search(visitor)
        assert 'Made-up Extra Movie' in page and asked_tmdb
    page, asked_tmdb = search(visitor)

    assert 'The demo allows 2 searches an hour.' in page
    assert not asked_tmdb
    # Another visitor has searches of their own.
    other, _ = start(Client())
    assert 'Made-up Extra Movie' in search(other)[0]
    # An hour later the first visitor can search again.
    clock.shift(datetime.timedelta(hours=1, seconds=1))
    assert 'Made-up Extra Movie' in search(visitor)[0]


def test_a_change_past_the_limit_is_refused_with_a_friendly_message_and_saves_nothing(demo_on, settings):
    settings.DEMO_CHANGES_PER_DAY = 1
    visitor, _ = start()
    user = account_of(visitor)

    visitor.post('/to-watch/add/', {'kind': 'movie', 'tmdb_id': 700})
    asked = demo_on.call_count
    with_htmx = visitor.post('/watched/add/', {'kind': 'movie', 'tmdb_id': 666277}, headers={'HX-Request': 'true'})
    without = visitor.post('/series/drop/', {'kind': 'series', 'tmdb_id': 95396, 'next': '/series/watching/'})

    message = demo.CHANGE_LIMIT.format(limit=1)
    assert with_htmx.status_code == 429 and with_htmx.content.decode() == message
    assert without.status_code == 302 and without['Location'] == '/series/watching/'
    assert message in visitor.get('/series/watching/').content.decode()
    # Nothing saved, and TMDB not asked.
    assert not Watch.objects.filter(user=user, title__tmdb_id=666277).exists()
    assert not user.droppedseries_set.exists()
    assert demo_on.call_count == asked
    assert DemoEvent.objects.filter(kind=DemoEvent.Kind.CHANGE, user=user).count() == 1


@pytest.mark.parametrize(
    'address',
    ['/to-watch/add/', '/watched/add/', '/watched/episode/add/', '/watched/season/add/', '/watched/season/again/',
     '/watched/up-to/add/', '/series/drop/', '/series/remove-all/'],
)
def test_every_button_that_adds_something_counts_as_a_change(demo_on, settings, address):
    settings.DEMO_CHANGES_PER_DAY = 0
    visitor, _ = start()

    response = visitor.post(address, {'kind': 'movie', 'tmdb_id': 700}, headers={'HX-Request': 'true'})

    assert response.status_code == 429


def test_undo_still_works_at_the_limit_and_never_counts(demo_on, settings):
    settings.DEMO_CHANGES_PER_DAY = 2
    visitor, _ = start()
    user = account_of(visitor)
    visitor.post('/watched/add/', {'kind': 'movie', 'tmdb_id': 666277, 'watched_on': TODAY.isoformat()})
    visitor.post('/series/drop/', {'kind': 'series', 'tmdb_id': 95396})
    assert visitor.post('/to-watch/add/', {'kind': 'movie', 'tmdb_id': 700}).status_code == 302
    assert not ToWatchItem.objects.filter(user=user, title__tmdb_id=700).exists()  # the limit is reached

    # Mark as not watched puts Past Lives back on To Watch, Bring back undoes the drop, and Remove and its Undo work.
    watch = Watch.objects.get(user=user, title__tmdb_id=666277)
    visitor.post('/watched/remove/', {'watch_id': watch.id})
    visitor.post('/series/bring-back/', {'kind': 'series', 'tmdb_id': 95396})
    visitor.post('/to-watch/remove/', {'kind': 'movie', 'tmdb_id': 1170608})
    visitor.post('/to-watch/undo/', {'kind': 'movie', 'tmdb_id': 1170608})
    severance = Watch.objects.filter(user=user, title__tmdb_id=95396).order_by('episode__episode_number').first()
    visitor.post('/watched/remove/', {'watch_id': severance.id})

    assert not Watch.objects.filter(user=user, title__tmdb_id=666277).exists()
    assert ToWatchItem.objects.get(user=user, title__tmdb_id=666277).removed_at is None
    assert not user.droppedseries_set.exists()
    assert ToWatchItem.objects.get(user=user, title__tmdb_id=1170608).removed_at is None
    assert not Watch.objects.filter(id=severance.id).exists()
    assert DemoEvent.objects.filter(kind=DemoEvent.Kind.CHANGE, user=user).count() == 2


def test_tmdb_requests_past_the_hourly_limit_are_refused_with_a_friendly_message(demo_on, settings, clock):
    visitor, _ = start()
    settings.DEMO_TMDB_REQUESTS_PER_HOUR = DemoEvent.objects.filter(kind=DemoEvent.Kind.TMDB).count()
    asked = demo_on.call_count

    page = visitor.get('/search/', {'q': 'made-up'}).content.decode()

    assert demo.TMDB_LIMIT in page
    assert demo_on.call_count == asked
    clock.shift(datetime.timedelta(hours=1, seconds=1))
    assert 'Made-up Extra Movie' in visitor.get('/search/', {'q': 'made-up'}).content.decode()


def test_past_the_daily_accounts_the_demo_is_full(demo_on, settings, clock):
    settings.DEMO_ACCOUNTS_PER_DAY = 1
    start()

    page = Client().get('/login/').content.decode()
    visitor, response = start()

    assert 'The demo is full for today. Try again tomorrow.' in page and 'action="/demo/start/"' not in page
    assert demo.DEMO_FULL in response.content.decode()
    assert '_auth_user_id' not in visitor.session
    assert User.objects.count() == 1
    clock.shift(datetime.timedelta(hours=24, seconds=1))
    assert 'action="/demo/start/"' in Client().get('/login/').content.decode()


# Old accounts


def test_accounts_older_than_a_day_are_deleted_with_their_data_when_a_new_one_starts(demo_on, clock):
    old, _ = start()
    old_user = account_of(old)
    old.get('/search/', {'q': 'made-up'})
    clock.shift(datetime.timedelta(hours=2))
    newer, _ = start(Client())
    newer_user = account_of(newer)
    owner = User.objects.create_user(username='made-up-owner')  # not a demo account: never deleted
    clock.shift(datetime.timedelta(hours=23))

    start(Client())

    assert not User.objects.filter(id=old_user.id).exists()
    assert not Watch.objects.filter(user_id=old_user.id).exists()
    assert not ToWatchItem.objects.filter(user_id=old_user.id).exists()
    assert not Profile.objects.filter(user_id=old_user.id).exists()
    assert not DemoEvent.objects.filter(user_id=old_user.id).exists()
    assert not DemoEvent.objects.filter(at__lt=NOW + datetime.timedelta(hours=1)).exists()
    assert User.objects.filter(id__in=[newer_user.id, owner.id]).count() == 2
    assert Watch.objects.filter(user=newer_user).exists()
    # The visitor whose account was deleted is just signed out.
    assert old.get('/').status_code == 302


# TVmaze and the size on Render


@pytest.mark.respx(assert_all_called=False)
def test_no_tvmaze_request_in_the_demo(demo_on, respx_mock):
    tvmaze_route = respx_mock.route(host='api.tvmaze.com').respond(json={'id': 1})
    visitor, _ = start()
    # So the app would look the series up on TVmaze if it could.
    Title.objects.filter(kind='series').update(imdb_id='tt0000001')

    # Collecting a series' dates is where TVmaze is asked outside the demo.
    for tmdb_id in (87108, 84773):
        assert visitor.post('/to-watch/collect/', {'kind': 'series', 'tmdb_id': tmdb_id}).status_code == 204
    with pytest.raises(tvmaze.TvmazeError):
        tvmaze.find_show_id('tt0000001')

    assert not tvmaze_route.called


@pytest.mark.parametrize('demo_mode, workers', [('true', 1), ('', 2)])
def test_the_demo_runs_one_worker_on_the_port_render_gives(monkeypatch, demo_mode, workers):
    monkeypatch.setenv('DEMO_MODE', demo_mode)
    monkeypatch.setenv('PORT', '10000')

    config = runpy.run_path(str(django_settings.BASE_DIR / 'gunicorn.conf.py'))

    assert config['workers'] == workers
    assert config['bind'] == '0.0.0.0:10000'


def test_without_a_port_gunicorn_listens_on_8000_as_before(monkeypatch):
    monkeypatch.delenv('PORT', raising=False)
    monkeypatch.delenv('DEMO_MODE', raising=False)

    config = runpy.run_path(str(django_settings.BASE_DIR / 'gunicorn.conf.py'))

    assert config['bind'] == '0.0.0.0:8000' and config['workers'] == 2 and config['threads'] == 4
