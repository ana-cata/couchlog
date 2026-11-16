"""Where to watch: at the end of a movie's or a series' page, the streaming services that have it in my country (the
country of my time zone), grouped. The JustWatch credit is on the About page. Asked from TMDB each time, never saved."""

import datetime
import os

import httpx
import pytest
import time_machine
from django.contrib.auth.models import User
from django.test import Client
from playwright.sync_api import expect

from core.models import Profile, Title
from core.where_to_watch import country_of

# The browser's driver runs inside an event loop, and Django refuses database calls from
# there unless told it is fine. It is fine in a test.
os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')

MOVIE_URL = 'https://api.themoviedb.org/3/movie/603'
SERIES_URL = 'https://api.themoviedb.org/3/tv/1399'
MOVIE_PROVIDERS_URL = f'{MOVIE_URL}/watch/providers'
SERIES_PROVIDERS_URL = f'{SERIES_URL}/watch/providers'

CREDIT = 'Streaming data from JustWatch'
PT_LINK = 'https://www.themoviedb.org/movie/603-made-up-movie/watch?locale=PT'


def provider(name, priority):
    return {'logo_path': f'/{name}.jpg', 'provider_id': priority, 'provider_name': name, 'display_priority': priority}


# Made-up TMDB answers. The tests never call the real TMDB.
MADE_UP_MOVIE = {
    'id': 603,
    'title': 'Made-up Movie',
    'release_date': '2023-03-31',
    'poster_path': '/made-up-movie.jpg',
    'overview': 'A made-up story about a movie.',
    'runtime': 100,
    'genres': [{'id': 18, 'name': 'Drama'}],
}
PROVIDERS = {
    'id': 603,
    'results': {
        'PT': {
            'link': PT_LINK,
            # Out of order on purpose: TMDB's display_priority decides the order.
            'flatrate': [provider('Max', 2), provider('Netflix', 1)],
            'rent': [provider('Apple TV', 3)],
            'buy': [provider('Apple TV', 3), provider('Google Play Movies', 4)],
            'free': [provider('RTP Play', 5)],
            'ads': [provider('Pluto TV', 6)],
        },
        'GB': {
            'link': 'https://www.themoviedb.org/movie/603-made-up-movie/watch?locale=GB',
            'flatrate': [provider('BBC iPlayer', 1)],
        },
    },
}
ONLY_IN_THE_US = {'id': 603, 'results': {'US': {'link': 'https://www.themoviedb.org/x', 'flatrate': [provider('Hulu', 1)]}}}

# The fixed "now" for every test here: 8 pm UTC on 16 Nov 2026.
NOW = datetime.datetime(2026, 11, 16, 20, 0, tzinfo=datetime.UTC)


@pytest.fixture(autouse=True)
def tmdb_key(settings):
    settings.TMDB_API_KEY = 'made-up-secret-key'


@pytest.fixture(autouse=True)
def clock():
    with time_machine.travel(NOW, tick=False) as traveller:
        yield traveller


def client_in(zone):
    user = User.objects.create_user(username=f'made-up-user-{zone}', password='made-up-password')
    Profile.objects.create(user=user, timezone=zone)
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def logged_in_client(db):
    return client_in('Europe/Lisbon')


def line(client, kind='movie'):
    """The Where to watch line as htmx loads it, with the spaces evened out."""
    return ' '.join(client.get(f'/{kind}/{603 if kind == "movie" else 1399}/where-to-watch/').content.decode().split())


# --- the title pages ---------------------------------------------------------------------------------


def test_a_movie_page_loads_the_line_once_it_is_shown_and_does_not_wait_for_it(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_URL).respond(json=MADE_UP_MOVIE)
    providers = respx_mock.get(MOVIE_PROVIDERS_URL).respond(json=PROVIDERS)

    page = logged_in_client.get('/movie/603/').content.decode()

    assert 'hx-get="/movie/603/where-to-watch/"' in page
    assert 'Where to watch: loading…' in page
    assert not providers.called  # the page itself never asks for the services
    # At the end of the page: after the description, the rating and the watched section.
    assert page.index('class="where-to-watch"') > page.index('class="watched-section"')
    assert page.index('class="where-to-watch"') > page.index('A made-up story about a movie.')


def test_a_series_page_has_the_same_line_after_the_seasons(logged_in_client, respx_mock):
    Title.objects.create(
        kind='series', tmdb_id=1399, title='Made-up Series', year='2023', episodes_refreshed_at=NOW
    )

    page = logged_in_client.get('/series/1399/').content.decode()

    assert 'hx-get="/series/1399/where-to-watch/"' in page
    assert page.index('class="where-to-watch"') > page.index('id="ask"')  # the last part of the seasons block


# --- the line ----------------------------------------------------------------------------------------


def test_a_movie_shows_my_countrys_services_grouped(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_PROVIDERS_URL).respond(json=PROVIDERS)

    text = line(logged_in_client)

    assert (
        '<p class="where-to-watch"> <small> <strong>Where to watch</strong> in Portugal: Stream on Netflix, Max · '
        'Rent on Apple TV · Buy on Apple TV, Google Play Movies · Free on RTP Play, Pluto TV (with ads) </small> </p>'
    ) == text
    assert 'BBC iPlayer' not in text  # another country's services are left out


def test_the_line_has_no_tmdb_link_and_no_credit_because_about_has_the_credit(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_PROVIDERS_URL).respond(json=PROVIDERS)

    text = line(logged_in_client)

    assert 'See all on TMDB' not in text and PT_LINK not in text and '<a ' not in text
    assert CREDIT not in text
    assert 'JustWatch' in logged_in_client.get('/about/').content.decode()


def test_a_series_shows_its_services_too(logged_in_client, respx_mock):
    respx_mock.get(SERIES_PROVIDERS_URL).respond(json=PROVIDERS)

    text = line(logged_in_client, 'series')

    assert 'in Portugal: Stream on Netflix, Max' in text


def test_only_the_groups_that_have_a_service_show(logged_in_client, respx_mock):
    answer = {'id': 603, 'results': {'PT': {'link': PT_LINK, 'rent': [provider('Apple TV', 1)]}}}
    respx_mock.get(MOVIE_PROVIDERS_URL).respond(json=answer)

    text = line(logged_in_client)

    assert 'in Portugal: Rent on Apple TV </small>' in text
    assert 'Stream on' not in text and 'Buy on' not in text and 'Free on' not in text


def test_a_title_with_no_services_says_so(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_PROVIDERS_URL).respond(json={'id': 603, 'results': {}})

    text = line(logged_in_client)

    assert 'Not on any streaming service in Portugal yet.' in text


def test_a_title_with_services_only_in_another_country_says_none_in_mine(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_PROVIDERS_URL).respond(json=ONLY_IN_THE_US)

    text = line(logged_in_client)

    assert 'Not on any streaming service in Portugal yet.' in text
    assert 'Hulu' not in text


def test_the_country_follows_my_time_zone(db, respx_mock):
    respx_mock.get(MOVIE_PROVIDERS_URL).respond(json=PROVIDERS)

    text = line(client_in('Europe/London'))

    assert 'in Britain (UK): Stream on BBC iPlayer' in text
    assert 'Netflix' not in text


def test_tmdb_not_answering_shows_the_usual_message(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_PROVIDERS_URL).mock(side_effect=httpx.ConnectError('no network'))

    response = logged_in_client.get('/movie/603/where-to-watch/')

    assert response.status_code == 200  # htmx only swaps in a normal answer, so the message shows in the line
    assert 'Could not reach TMDB.' in response.content.decode()


def test_a_service_name_is_shown_as_plain_text(logged_in_client, respx_mock):
    answer = {'id': 603, 'results': {'PT': {'flatrate': [provider('<b>Odd</b> & Co', 1)]}}}
    respx_mock.get(MOVIE_PROVIDERS_URL).respond(json=answer)

    text = line(logged_in_client)

    assert 'Stream on &lt;b&gt;Odd&lt;/b&gt; &amp; Co' in text


def test_nothing_is_saved(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_PROVIDERS_URL).respond(json=PROVIDERS)

    line(logged_in_client)

    assert Title.objects.count() == 0


def test_the_line_needs_a_login(db):
    response = Client().get('/movie/603/where-to-watch/')

    assert response.status_code == 302


# --- my country --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ('zone', 'country'),
    [
        ('Europe/Lisbon', ('PT', 'Portugal')),
        ('Atlantic/Azores', ('PT', 'Portugal')),
        ('Europe/London', ('GB', 'Britain (UK)')),
        ('America/New_York', ('US', 'United States')),
        ('America/Sao_Paulo', ('BR', 'Brazil')),
        ('Europe/Madrid', ('ES', 'Spain')),
        # No one country: Portugal.
        ('UTC', ('PT', 'Portugal')),
        ('', ('PT', 'Portugal')),
    ],
)
def test_my_country_is_the_country_of_my_time_zone(zone, country):
    assert country_of(zone) == country


# --- on a phone (a real browser) ---------------------------------------------------------------------


def test_on_a_phone_a_long_line_wraps_and_pushes_nothing_off_the_screen(live_server, browser, respx_mock, monkeypatch):
    from core import tmdb

    many = [f'Made-up Streaming Service Number {number}' for number in range(1, 9)]
    groups = [{'label': label, 'names': many} for label in ('Stream', 'Rent', 'Buy', 'Free')]
    monkeypatch.setattr(tmdb, 'get_watch_providers', lambda kind, tmdb_id, country: groups)
    respx_mock.get(MOVIE_URL).respond(json=MADE_UP_MOVIE)
    user = User.objects.create_user(username='made-up-user', password='made-up-password')
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    context = browser.new_context(viewport={'width': 360, 'height': 700}, has_touch=True, is_mobile=True)
    page = context.new_page()
    page.goto(live_server.url)
    page.get_by_label('Username').fill('made-up-user')
    page.get_by_label('Password').fill('made-up-password')
    page.get_by_role('button', name='Log in').click()
    page.wait_for_url(live_server.url + '/')

    page.goto(live_server.url + '/movie/603/')

    expect(page.locator('.where-to-watch')).to_contain_text('Free on Made-up Streaming Service Number 1,')
    assert page.evaluate('document.documentElement.scrollWidth') <= 360  # nothing sticks out to the side
    line_box = page.locator('.where-to-watch').bounding_box()
    assert line_box['x'] + line_box['width'] <= 360
    button = page.get_by_role('button', name='Mark as watched').bounding_box()
    assert button['x'] >= 0 and button['x'] + button['width'] <= 360
    context.close()
