"""Adding a series to To Watch is quick: the series is on the list at once and its episodes and Calendar dates are
collected right after, by a second request the button sends.

TMDB's and TVmaze's answers are made up. An address a test does not set up fails the test if the app asks it, so a test
that sets up fewer addresses also proves that the rest was not asked."""

import datetime
import io
import os

import httpx
import pytest
import time_machine
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import Client
from playwright.sync_api import expect

from core.models import Episode, Profile, Title, ToWatchItem, UpcomingEpisode

# The browser's driver runs inside an event loop, and Django refuses database calls from
# there unless told it is fine. It is fine in a test.
os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')

TMDB = 'https://api.themoviedb.org/3'
TVMAZE = 'https://api.tvmaze.com'
SERIES_URL = f'{TMDB}/tv/800'
SEASON_URL = f'{TMDB}/tv/800/season/1'
MOVIE_URL = f'{TMDB}/movie/700'

# The fixed "today": 8 pm UTC on Wed 28 Oct 2026. The episodes below air on the Fridays after it.
NOW = datetime.datetime(2026, 10, 28, 20, 0, tzinfo=datetime.UTC)
FRIDAY = datetime.date(2026, 11, 6)
NEXT_FRIDAY = datetime.date(2026, 11, 13)

HTMX = {'headers': {'HX-Request': 'true'}}


@pytest.fixture(autouse=True)
def clock():
    with time_machine.travel(NOW, tick=False) as traveller:
        yield traveller


@pytest.fixture(autouse=True)
def tmdb_key(settings):
    settings.TMDB_API_KEY = 'made-up-secret-key'


def make_client(name='made-up-user', **options):
    """A browser logged in as a new account (with a time zone chosen, so no redirect to Profile)."""
    user = User.objects.create_user(username=name, password='made-up-password')
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    client = Client(**options)
    client.force_login(user)
    client.user = user
    return client


@pytest.fixture
def client(db):
    return make_client()


SEASON = {
    'season_number': 1,
    'episodes': [
        {'id': 9001, 'season_number': 1, 'episode_number': 1, 'name': 'Premiere', 'air_date': FRIDAY.isoformat()},
        {'id': 9002, 'season_number': 1, 'episode_number': 2, 'name': 'Second', 'air_date': NEXT_FRIDAY.isoformat()},
    ],
}


def mock_series(respx_mock, imdb_id=None):
    """TMDB's answers for series 800: its details, and its one season of two episodes. Returns the season's route."""
    respx_mock.get(SERIES_URL).respond(
        json={
            'id': 800, 'name': 'Made-up Series 800', 'first_air_date': '2026-01-01', 'status': 'Returning Series',
            'seasons': [{'season_number': 1}], 'external_ids': {'imdb_id': imdb_id},
            'genres': [{'id': 18, 'name': 'Drama'}],
        }
    )
    return respx_mock.get(SEASON_URL).respond(json=SEASON)


def mock_tvmaze(respx_mock, imdb_id='tt800', show_id=48830):
    """TVmaze knowing the show, with one more upcoming episode than TMDB lists."""
    respx_mock.get(f'{TVMAZE}/lookup/shows', params={'imdb': imdb_id}).respond(json={'id': show_id, 'name': 'Made-up'})
    episode = {'id': 3003, 'season': 1, 'number': 3, 'name': 'Third', 'type': 'regular', 'airdate': '2026-11-20'}
    return respx_mock.get(f'{TVMAZE}/shows/{show_id}/episodes').respond(json=[episode])


def add(client, tmdb_id=800, kind='series', **options):
    """Press the button the way htmx does (unless `options` say otherwise)."""
    return client.post('/to-watch/add/', {'kind': kind, 'tmdb_id': tmdb_id}, **{**HTMX, **options})


def remove(client, tmdb_id=800, kind='series'):
    return client.post('/to-watch/remove/', {'kind': kind, 'tmdb_id': tmdb_id}, **HTMX)


def undo(client, tmdb_id=800, kind='series'):
    return client.post('/to-watch/undo/', {'kind': kind, 'tmdb_id': tmdb_id}, **HTMX)


def collect(client, tmdb_id=800, kind='series'):
    """The second request the button sends right after the add."""
    return client.post('/to-watch/collect/', {'kind': kind, 'tmdb_id': tmdb_id}, **HTMX)


def on_the_list(client):
    return list(ToWatchItem.objects.filter(user=client.user, removed_at=None).values_list('title__tmdb_id', flat=True))


def calendar_text(client):
    """What the Calendar page shows, as one line of text."""
    return ' '.join(client.get('/calendar/').content.decode().split())


# --- the series first, its episodes after ------------------------------------------------------------------------


def test_a_series_is_on_the_list_before_its_episodes_are_collected(client, respx_mock):
    season = mock_series(respx_mock)

    response = add(client)

    assert response.status_code == 200
    assert on_the_list(client) == [800]
    assert 'action="/to-watch/remove/"' in response.content.decode()  # the button already says Remove
    # Only the series itself was asked for, not its seasons: nothing of the slow part has happened yet.
    assert season.call_count == 0
    assert Episode.objects.count() == 0
    assert Title.objects.get().episodes_refreshed_at is None
    assert 'Made-up Series 800' not in calendar_text(client)


def test_the_answer_asks_the_server_to_collect_the_rest_right_away(client, respx_mock):
    mock_series(respx_mock)

    body = add(client).content.decode()

    assert 'hx-post="/to-watch/collect/"' in body and 'hx-trigger="load"' in body
    assert 'name="kind" value="series"' in body and 'name="tmdb_id" value="800"' in body
    # It has the form's token, like every button, and nothing secret.
    assert 'csrfmiddlewaretoken' in body and 'made-up-secret-key' not in body


def test_the_episodes_status_genres_and_calendar_dates_are_there_after_the_second_request(client, respx_mock):
    mock_series(respx_mock, imdb_id='tt800')
    mock_tvmaze(respx_mock)
    add(client)

    response = collect(client)

    assert response.status_code == 204 and response.content == b''  # nothing for htmx to swap in
    series = Title.objects.get()
    assert series.status == 'Returning Series'
    assert [genre['name'] for genre in series.genres] == ['Drama']
    assert series.episodes_refreshed_at is not None
    assert list(Episode.objects.order_by('episode_number').values_list('name', 'air_date')) == [
        ('Premiere', FRIDAY), ('Second', NEXT_FRIDAY),
    ]
    assert UpcomingEpisode.objects.get().name == 'Third'  # from TVmaze
    page = calendar_text(client)
    assert 'S1E1 · Premiere' in page and 'S1E2 · Second' in page and 'S1E3 · Third' in page


def test_pressing_the_button_on_a_series_already_on_the_list_asks_for_no_collecting(client, respx_mock):
    mock_series(respx_mock)
    add(client)
    asked = respx_mock.calls.call_count

    again = add(client)

    assert 'hx-post="/to-watch/collect/"' not in again.content.decode()
    assert respx_mock.calls.call_count == asked


def test_adding_a_series_again_after_removing_it_collects_again(client, respx_mock):
    mock_series(respx_mock)
    add(client)
    remove(client)

    again = add(client)

    assert 'hx-post="/to-watch/collect/"' in again.content.decode()
    assert on_the_list(client) == [800]


def test_a_series_collected_a_moment_ago_is_not_asked_for_again(client, respx_mock):
    season = mock_series(respx_mock)
    add(client)
    collect(client)
    asked = season.call_count

    # Removed and added again: the episodes are less than a day old, so TMDB is not asked for them again.
    remove(client)
    add(client)
    collect(client)

    assert season.call_count == asked == 1


def test_a_movie_still_gets_its_dates_during_the_add(client, respx_mock):
    respx_mock.get(MOVIE_URL).respond(
        json={
            'id': 700, 'title': 'Made-up Movie 700', 'release_date': '2027-03-11',
            'release_dates': {
                'results': [
                    {'iso_3166_1': 'US', 'release_dates': [{'type': 3, 'release_date': '2027-03-11T00:00:00.000Z'}]}
                ]
            },
        }
    )

    response = add(client, tmdb_id=700, kind='movie')

    assert response.status_code == 200
    assert 'hx-post="/to-watch/collect/"' not in response.content.decode()  # nothing left to collect later
    assert Title.objects.get().cinema_at == datetime.datetime(2027, 3, 11, tzinfo=datetime.UTC)


def test_without_htmx_the_series_is_collected_during_the_add_as_before(client, respx_mock):
    mock_series(respx_mock)

    response = client.post('/to-watch/add/', {'kind': 'series', 'tmdb_id': 800})

    assert response.status_code == 302
    assert on_the_list(client) == [800]
    assert Episode.objects.count() == 2  # nothing could ask later, so it was done now


# --- when TMDB or TVmaze does not answer ---------------------------------------------------------------------------


def test_if_tmdb_fails_in_the_second_request_the_series_stays_and_the_command_catches_up(client, respx_mock):
    season = mock_series(respx_mock)
    season.mock(side_effect=httpx.ConnectError('no network'))
    add(client)

    response = collect(client)

    assert response.status_code == 204
    assert on_the_list(client) == [800]
    assert Episode.objects.count() == 0  # nothing half saved
    assert Title.objects.get().episodes_refreshed_at is None

    mock_series(respx_mock)  # TMDB is back
    call_command('refresh_calendar', stdout=io.StringIO(), stderr=io.StringIO())

    assert Episode.objects.count() == 2
    assert on_the_list(client) == [800]
    assert 'S1E1 · Premiere' in calendar_text(client)


def test_if_tvmaze_fails_in_the_second_request_tmdbs_part_is_kept_and_the_command_catches_up(client, respx_mock):
    mock_series(respx_mock, imdb_id='tt800')
    respx_mock.get(f'{TVMAZE}/lookup/shows', params={'imdb': 'tt800'}).mock(side_effect=httpx.ConnectError('no network'))
    add(client)

    response = collect(client)

    assert response.status_code == 204
    assert on_the_list(client) == [800]
    assert Episode.objects.count() == 2  # TMDB's part is there
    assert UpcomingEpisode.objects.count() == 0

    mock_tvmaze(respx_mock)  # TVmaze is back
    call_command('refresh_calendar', stdout=io.StringIO(), stderr=io.StringIO())

    assert UpcomingEpisode.objects.get().name == 'Third'


# --- removing while it is being collected ------------------------------------------------------------------------


def test_removing_before_the_second_request_arrives_works_and_collects_nothing(client, respx_mock):
    season = mock_series(respx_mock)
    add(client)
    on_list_before = list(ToWatchItem.objects.order_by('id').values())

    remove(client)
    response = collect(client)

    assert response.status_code == 204
    assert on_the_list(client) == []
    assert ToWatchItem.objects.get().removed_at is not None
    assert season.call_count == 0 and Episode.objects.count() == 0  # a series that left the list is left alone

    # Undo puts the entry back exactly as it was.
    undo(client)
    assert list(ToWatchItem.objects.order_by('id').values()) == on_list_before


def test_removing_while_the_episodes_are_being_collected_works_and_undo_puts_it_back(client, respx_mock):
    season = mock_series(respx_mock)
    add(client)
    on_list_before = list(ToWatchItem.objects.order_by('id').values())

    def removed_in_the_middle(request):
        # The press of Remove arrives while TMDB is being asked for the seasons.
        assert remove(client).status_code == 200
        return httpx.Response(200, json=SEASON)

    season.mock(side_effect=removed_in_the_middle)

    response = collect(client)

    assert response.status_code == 204
    assert on_the_list(client) == []  # the removal was not undone by the collecting
    assert ToWatchItem.objects.get().removed_at is not None
    assert Episode.objects.count() == 2  # the episodes belong to the series, not to the list

    undo(client)
    assert list(ToWatchItem.objects.order_by('id').values()) == on_list_before
    assert on_the_list(client) == [800]


# --- each account its own --------------------------------------------------------------------------------------


def test_the_second_request_of_an_account_that_does_not_have_the_series_collects_nothing(client, respx_mock):
    season = mock_series(respx_mock)
    add(client)
    other = make_client('second-user')

    response = collect(other)

    assert response.status_code == 204
    assert season.call_count == 0 and Episode.objects.count() == 0
    assert on_the_list(other) == [] and on_the_list(client) == [800]


def test_each_account_has_its_own_entry_and_the_episodes_are_shared(client, respx_mock):
    season = mock_series(respx_mock)
    other = make_client('second-user')

    add(client)
    add(other)
    collect(client)
    collect(other)

    assert on_the_list(client) == [800] and on_the_list(other) == [800]
    assert ToWatchItem.objects.count() == 2
    assert Episode.objects.count() == 2 and season.call_count == 1  # the second account found them already saved
    remove(client)
    assert on_the_list(client) == [] and on_the_list(other) == [800]


def test_the_second_request_for_a_title_that_is_not_saved_asks_tmdb_nothing(client, respx_mock):
    response = collect(client, tmdb_id=12345)

    assert response.status_code == 204
    assert respx_mock.calls.call_count == 0


# --- safety ------------------------------------------------------------------------------------------------------


def test_the_collect_address_is_closed_when_logged_out(db, respx_mock):
    response = Client().post('/to-watch/collect/', {'kind': 'series', 'tmdb_id': 800})

    assert response.status_code == 302 and response['Location'].startswith('/login/')
    assert respx_mock.calls.call_count == 0


def test_the_collect_address_only_accepts_posts(client, respx_mock):
    assert client.get('/to-watch/collect/').status_code == 405
    assert respx_mock.calls.call_count == 0


@pytest.mark.parametrize(
    'form', [{'kind': 'person', 'tmdb_id': 800}, {'kind': 'series', 'tmdb_id': 'abc'}, {'kind': 'series', 'tmdb_id': 0}, {}]
)
def test_the_collect_address_refuses_nonsense(client, respx_mock, form):
    assert client.post('/to-watch/collect/', form).status_code == 400
    assert respx_mock.calls.call_count == 0


def test_the_collect_address_needs_the_csrf_token(db, respx_mock):
    strict = make_client(enforce_csrf_checks=True)

    response = strict.post('/to-watch/collect/', {'kind': 'series', 'tmdb_id': 800})

    assert response.status_code == 403
    assert respx_mock.calls.call_count == 0


# --- in a real browser ---------------------------------------------------------------------------------------------


@pytest.fixture
def user(db):
    user = User.objects.create_user(username='made-up-user', password='made-up-password')
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    return user


def log_in(page, live_server):
    page.goto(live_server.url)
    page.get_by_label('Username').fill('made-up-user')
    page.get_by_label('Password').fill('made-up-password')
    page.get_by_role('button', name='Log in').click()


def test_the_button_says_adding_until_the_series_is_on_the_list_and_the_rest_comes_after(
    live_server, page, respx_mock, user
):
    respx_mock.get(f'{TMDB}/search/multi').respond(
        json={
            'results': [
                {'media_type': 'tv', 'id': 800, 'name': 'Made-up Series 800', 'first_air_date': '2026-01-01', 'poster_path': '/a.jpg'}
            ]
        }
    )
    mock_series(respx_mock)
    page.route('https://image.tmdb.org/**', lambda route: route.abort())
    # Hold both requests back, as a slow TMDB would: the add first, then the collecting that comes after it.
    held = {'add': [], 'collect': []}
    page.route('**/to-watch/add/', lambda route: held['add'].append(route))
    page.route('**/to-watch/collect/', lambda route: held['collect'].append(route))
    log_in(page, live_server)
    page.goto(live_server.url + '/search/?q=made-up')
    page.wait_for_load_state('load')

    button = page.locator('.to-watch-action button')
    # The button holds both wordings (only one shows), so the text on the screen is what counts.
    expect(button).to_have_text('Add to To Watch', use_inner_text=True)
    button.click()

    # While the server works the button says so, and pressing it again does nothing.
    expect(button).to_have_text('Adding…', use_inner_text=True)
    expect(button).to_be_disabled()
    button.click(force=True)
    page.wait_for_timeout(200)
    assert len(held['add']) == 1

    with page.expect_response('**/to-watch/add/'):
        held['add'][0].continue_()

    # The series is on the list and the button is back, but the episodes have not been collected yet.
    expect(button).to_have_text('Remove from To Watch', use_inner_text=True)
    expect(button).to_be_enabled()
    assert ToWatchItem.objects.filter(user=user, removed_at=None, title__tmdb_id=800).count() == 1
    expect(page.locator('form[hx-post="/to-watch/collect/"]')).to_have_count(1)  # the second request is on its way
    page.wait_for_timeout(200)
    assert len(held['collect']) == 1
    assert Episode.objects.count() == 0

    with page.expect_response('**/to-watch/collect/') as collected:
        held['collect'][0].continue_()
    assert collected.value.status == 204
    assert Episode.objects.count() == 2
    expect(button).to_have_text('Remove from To Watch', use_inner_text=True)
    assert ToWatchItem.objects.filter(user=user, removed_at=None).count() == 1
