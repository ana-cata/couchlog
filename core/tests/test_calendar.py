"""The Calendar page: what is coming up for the series being watched and the To Watch list.

The page only reads what is saved (the episodes' air dates and a movie's streaming date), so none of these tests
mock TMDB; the one that checks the page never asks TMDB would fail if it did.
"""

import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest
import time_machine
from django.contrib.auth.models import User
from django.test import Client

from core.models import Episode, Profile, Title, ToWatchItem, Watch
from core.releases import upcoming

# The fixed "today": 8 pm UTC on Wed 28 Oct 2026 (still the 28th in Lisbon, already the 29th in Auckland).
NOW = datetime.datetime(2026, 10, 28, 20, 0, tzinfo=datetime.UTC)
TODAY = datetime.date(2026, 10, 28)
YESTERDAY = datetime.date(2026, 10, 27)
FRIDAY = datetime.date(2026, 11, 6)
LISBON = ZoneInfo('Europe/Lisbon')


def midnight_utc(year, month, day):
    """How TMDB gives a streaming date: the day, at midnight UTC."""
    return datetime.datetime(year, month, day, tzinfo=datetime.UTC)


@pytest.fixture(autouse=True)
def clock():
    with time_machine.travel(NOW, tick=False) as traveller:
        yield traveller


def make_client(name='made-up-user', zone='Europe/Lisbon'):
    account = User.objects.create_user(username=name, password='made-up-password')
    Profile.objects.create(user=account, timezone=zone)
    client = Client()
    client.force_login(account)
    client.user = account
    return client


@pytest.fixture
def client(db):
    return make_client()


def make_series(tmdb_id=1, name=None):
    return Title.objects.create(kind='series', tmdb_id=tmdb_id, title=name or f'Made-up Series {tmdb_id}')


def make_movie(tmdb_id=500, streaming_at=None, name=None, cinema_at=None):
    return Title.objects.create(
        kind='movie',
        tmdb_id=tmdb_id,
        title=name or f'Made-up Movie {tmdb_id}',
        streaming_at=streaming_at,
        cinema_at=cinema_at,
    )


def make_episode(series, season, number, air_date=FRIDAY, name=''):
    tmdb_id = series.tmdb_id * 1000 + season * 100 + number
    return Episode.objects.create(
        title=series, tmdb_id=tmdb_id, season_number=season, episode_number=number, air_date=air_date, name=name
    )


def put_on_list(user, title):
    return ToWatchItem.objects.create(user=user, title=title)


def watch(user, episode):
    return Watch.objects.create(user=user, title=episode.title, episode=episode, watched_on=TODAY)


def coming(user, zone=LISBON):
    """What the calendar lists, as [(day, [(title, text), ...]), ...]."""
    return [
        (day['day'], [(item['title'].title, item['text']) for item in day['items']])
        for day in upcoming(user, TODAY, zone)
    ]


# --- series -----------------------------------------------------------------------------------


def test_an_upcoming_episode_of_a_series_on_the_to_watch_list_is_on_its_air_date(client):
    series = make_series(1)
    make_episode(series, 2, 4, FRIDAY, name='The Return')
    put_on_list(client.user, series)

    assert coming(client.user) == [(FRIDAY, [('Made-up Series 1', 'S2E4 · The Return')])]


def test_an_upcoming_episode_of_a_series_being_watched_is_on_its_air_date(client):
    series = make_series(1)
    watch(client.user, make_episode(series, 1, 1, datetime.date(2011, 4, 17)))
    make_episode(series, 1, 2, FRIDAY, name='Second')
    # It is on no To Watch list at all: marking an episode is enough to be watching it.

    assert coming(client.user) == [(FRIDAY, [('Made-up Series 1', 'S1E2 · Second')])]


def test_an_episode_without_a_name_is_still_listed(client):
    series = make_series(1)
    make_episode(series, 1, 2, FRIDAY)
    put_on_list(client.user, series)

    assert coming(client.user) == [(FRIDAY, [('Made-up Series 1', 'S1E2 · Untitled episode')])]


def test_a_series_that_is_neither_watched_nor_on_the_list_is_not_there(client):
    make_episode(make_series(1), 1, 1)

    assert coming(client.user) == []


def test_a_series_on_someone_elses_list_is_not_there(client):
    series = make_series(1)
    make_episode(series, 1, 1)
    put_on_list(make_client('someone-else').user, series)

    assert coming(client.user) == []


def test_episodes_without_an_air_date_are_left_out(client):
    series = make_series(1)
    make_episode(series, 1, 1, None)
    make_episode(series, 1, 2, FRIDAY, name='Dated')
    put_on_list(client.user, series)

    assert coming(client.user) == [(FRIDAY, [('Made-up Series 1', 'S1E2 · Dated')])]


def test_a_series_whose_episodes_have_no_dates_adds_nothing_and_does_not_break(client):
    series = make_series(1)
    make_episode(series, 1, 1, None)
    put_on_list(client.user, series)

    assert coming(client.user) == []
    assert 'Nothing coming up' in client.get('/calendar/').content.decode()


def test_episodes_in_the_past_are_left_out_and_one_airing_today_stays(client):
    series = make_series(1)
    make_episode(series, 1, 1, YESTERDAY)
    make_episode(series, 1, 2, TODAY, name='Tonight')
    put_on_list(client.user, series)

    assert coming(client.user) == [(TODAY, [('Made-up Series 1', 'S1E2 · Tonight')])]


def test_specials_are_left_out(client):
    series = make_series(1)
    make_episode(series, 0, 1, FRIDAY)
    put_on_list(client.user, series)

    assert coming(client.user) == []


def test_several_episodes_of_one_series_on_one_day_share_a_line(client):
    series = make_series(1)
    for number in (3, 1, 2):  # saved out of order on purpose
        make_episode(series, 2, number, FRIDAY)
    put_on_list(client.user, series)

    assert coming(client.user) == [(FRIDAY, [('Made-up Series 1', 'S2E1–E3 · 3 episodes')])]


def test_episodes_of_one_day_that_cross_a_season_say_so(client):
    series = make_series(1)
    make_episode(series, 1, 9, FRIDAY)
    make_episode(series, 2, 1, FRIDAY)
    put_on_list(client.user, series)

    assert coming(client.user) == [(FRIDAY, [('Made-up Series 1', 'S1E9 – S2E1 · 2 episodes')])]


def test_days_are_in_date_order_and_titles_of_a_day_in_name_order(client):
    later = datetime.date(2026, 12, 1)
    zebra, apple = make_series(1, 'Zebra'), make_series(2, 'apple')
    make_episode(zebra, 1, 1, FRIDAY, name='Z')
    make_episode(apple, 1, 1, FRIDAY, name='A')
    make_episode(zebra, 1, 2, later, name='Z2')
    put_on_list(client.user, zebra)
    put_on_list(client.user, apple)

    assert coming(client.user) == [
        (FRIDAY, [('apple', 'S1E1 · A'), ('Zebra', 'S1E1 · Z')]),
        (later, [('Zebra', 'S1E2 · Z2')]),
    ]


def test_removing_a_series_from_the_list_removes_it_from_the_calendar_and_undo_brings_it_back(client):
    series = make_series(1)
    make_episode(series, 1, 1, FRIDAY, name='Pilot')
    put_on_list(client.user, series)
    assert 'Made-up Series 1' in client.get('/calendar/').content.decode()

    client.post('/to-watch/remove/', {'kind': 'series', 'tmdb_id': 1})
    removed_page = client.get('/calendar/').content.decode()
    client.post('/to-watch/undo/', {'kind': 'series', 'tmdb_id': 1})
    restored_page = client.get('/calendar/').content.decode()

    assert 'Made-up Series 1' not in removed_page and 'Nothing coming up' in removed_page
    assert 'Made-up Series 1' in restored_page and 'S1E1 · Pilot' in restored_page


def test_a_series_that_is_being_watched_stays_after_it_is_removed_from_the_list(client):
    series = make_series(1)
    watch(client.user, make_episode(series, 1, 1, datetime.date(2011, 4, 17)))
    make_episode(series, 1, 2, FRIDAY, name='Second')
    put_on_list(client.user, series)

    client.post('/to-watch/remove/', {'kind': 'series', 'tmdb_id': 1})

    assert coming(client.user) == [(FRIDAY, [('Made-up Series 1', 'S1E2 · Second')])]


def test_unmarking_the_only_watched_episode_of_a_series_not_on_the_list_removes_it_from_the_calendar(client):
    series = make_series(1)
    marked = watch(client.user, make_episode(series, 1, 1, datetime.date(2011, 4, 17)))
    make_episode(series, 1, 2, FRIDAY)
    assert len(coming(client.user)) == 1

    marked.delete()

    assert coming(client.user) == []


def test_today_follows_the_account_time_zone_for_episodes(db):
    # At the fixed moment it is still the 28th in Lisbon but already the 29th in Auckland.
    series = make_series(1)
    make_episode(series, 1, 1, TODAY, name='Same day')
    lisbon, auckland = make_client('lisbon', 'Europe/Lisbon'), make_client('auckland', 'Pacific/Auckland')
    put_on_list(lisbon.user, series)
    put_on_list(auckland.user, series)

    assert 'S1E1 · Same day' in lisbon.get('/calendar/').content.decode()
    assert 'S1E1 · Same day' not in auckland.get('/calendar/').content.decode()


# --- movies -----------------------------------------------------------------------------------


def test_a_movie_on_the_list_is_on_its_streaming_date(client):
    put_on_list(client.user, make_movie(500, midnight_utc(2026, 11, 20)))

    assert coming(client.user) == [(datetime.date(2026, 11, 20), [('Made-up Movie 500', 'Streaming release')])]


@pytest.mark.parametrize(
    ('zone', 'day'),
    [
        ('Europe/Lisbon', 20),  # 00:00 UTC is 00:00 (winter) in Lisbon: the same day
        ('Asia/Tokyo', 20),  # 09:00: the same day
        ('Pacific/Auckland', 20),  # 13:00: the same day
        ('America/New_York', 19),  # 19:00 the evening before: the day before
    ],
)
def test_a_streaming_date_is_turned_into_a_day_in_the_account_time_zone(db, zone, day):
    account = make_client(zone=zone).user
    put_on_list(account, make_movie(500, midnight_utc(2026, 11, 20)))

    assert coming(account, ZoneInfo(zone)) == [(datetime.date(2026, 11, day), [('Made-up Movie 500', 'Streaming release')])]


def test_a_movie_whose_streaming_day_has_passed_in_the_account_time_zone_is_left_out(db):
    # 00:00 UTC on the 28th is still the 27th evening in New York, where "today" is the 28th afternoon.
    film = make_movie(500, midnight_utc(2026, 10, 28))
    lisbon, new_york = make_client('lisbon', 'Europe/Lisbon').user, make_client('new-york', 'America/New_York').user
    put_on_list(lisbon, film)
    put_on_list(new_york, film)

    assert coming(lisbon, LISBON) == [(TODAY, [('Made-up Movie 500', 'Streaming release')])]
    assert coming(new_york, ZoneInfo('America/New_York')) == []


def test_a_movie_that_already_streams_is_left_out(client):
    put_on_list(client.user, make_movie(500, midnight_utc(2026, 9, 1)))

    assert coming(client.user) == []


def test_a_movie_with_no_dates_at_all_is_left_out(client):
    put_on_list(client.user, make_movie(500, None))

    assert coming(client.user) == []


# A film that is not out yet usually has a cinema date long before TMDB knows when it will stream.


def test_a_movie_not_out_yet_with_only_a_cinema_date_is_on_that_date(client):
    put_on_list(client.user, make_movie(500, cinema_at=midnight_utc(2026, 12, 16), name='Not Out Yet'))

    assert coming(client.user) == [(datetime.date(2026, 12, 16), [('Not Out Yet', 'In cinemas')])]


def test_a_movie_with_both_dates_is_on_both_days(client):
    put_on_list(
        client.user,
        make_movie(500, cinema_at=midnight_utc(2026, 12, 16), streaming_at=midnight_utc(2027, 3, 5), name='Both'),
    )

    assert coming(client.user) == [
        (datetime.date(2026, 12, 16), [('Both', 'In cinemas')]),
        (datetime.date(2027, 3, 5), [('Both', 'Streaming release')]),
    ]


def test_a_movie_already_in_cinemas_is_only_on_its_streaming_date(client):
    put_on_list(
        client.user,
        make_movie(500, cinema_at=midnight_utc(2026, 9, 1), streaming_at=midnight_utc(2026, 11, 20), name='Out'),
    )

    assert coming(client.user) == [(datetime.date(2026, 11, 20), [('Out', 'Streaming release')])]


def test_a_movie_in_cinemas_and_streaming_on_the_same_day_has_two_lines(client):
    put_on_list(
        client.user,
        make_movie(500, cinema_at=midnight_utc(2026, 11, 20), streaming_at=midnight_utc(2026, 11, 20), name='Same'),
    )

    assert coming(client.user) == [
        (datetime.date(2026, 11, 20), [('Same', 'In cinemas'), ('Same', 'Streaming release')])
    ]


def test_a_cinema_date_is_turned_into_a_day_in_the_account_time_zone_too(db):
    film = make_movie(500, cinema_at=midnight_utc(2026, 12, 16), name='Film')
    lisbon, new_york = make_client('lisbon', 'Europe/Lisbon').user, make_client('new-york', 'America/New_York').user
    put_on_list(lisbon, film)
    put_on_list(new_york, film)

    assert coming(lisbon, LISBON) == [(datetime.date(2026, 12, 16), [('Film', 'In cinemas')])]
    assert coming(new_york, ZoneInfo('America/New_York')) == [(datetime.date(2026, 12, 15), [('Film', 'In cinemas')])]


def test_a_movie_not_out_yet_that_is_not_on_the_list_or_was_watched_is_left_out(client):
    make_movie(500, cinema_at=midnight_utc(2026, 12, 16))
    watched = make_movie(501, cinema_at=midnight_utc(2026, 12, 16))
    watch_of_it = Watch.objects.create(user=client.user, title=watched)
    ToWatchItem.objects.create(
        user=client.user, title=watched, removed_at=NOW, removed_by_watch=watch_of_it
    )

    assert coming(client.user) == []


def test_a_movie_that_is_not_on_the_list_is_left_out(client):
    make_movie(500, midnight_utc(2026, 11, 20))

    assert coming(client.user) == []


def test_a_movie_that_was_watched_is_left_out_and_comes_back_when_unmarked(client):
    film = make_movie(500, midnight_utc(2026, 11, 20))
    put_on_list(client.user, film)

    client.post('/watched/add/', {'kind': 'movie', 'tmdb_id': 500, 'watched_on': '2026-10-28'})
    after_watching = coming(client.user)
    client.post('/watched/remove/', {'watch_id': Watch.objects.get(user=client.user, title=film).id})

    assert after_watching == []
    assert coming(client.user) == [(datetime.date(2026, 11, 20), [('Made-up Movie 500', 'Streaming release')])]


def test_removing_a_movie_from_the_list_removes_it_from_the_calendar_and_undo_brings_it_back(client):
    put_on_list(client.user, make_movie(500, midnight_utc(2026, 11, 20)))

    client.post('/to-watch/remove/', {'kind': 'movie', 'tmdb_id': 500})
    removed = coming(client.user)
    client.post('/to-watch/undo/', {'kind': 'movie', 'tmdb_id': 500})

    assert removed == []
    assert len(coming(client.user)) == 1


def test_movies_and_episodes_of_the_same_day_are_mixed_in_name_order(client):
    series = make_series(1, 'Beta Show')
    make_episode(series, 1, 1, datetime.date(2026, 11, 20), name='Pilot')
    put_on_list(client.user, series)
    put_on_list(client.user, make_movie(500, midnight_utc(2026, 11, 20), name='Alpha Film'))

    assert coming(client.user) == [
        (datetime.date(2026, 11, 20), [('Alpha Film', 'Streaming release'), ('Beta Show', 'S1E1 · Pilot')])
    ]


# --- the page ---------------------------------------------------------------------------------


def test_the_page_shows_months_days_and_titles_with_links(client):
    series = make_series(1, 'Made-up Show')
    make_episode(series, 2, 4, FRIDAY, name='The Return')
    put_on_list(client.user, series)
    put_on_list(client.user, make_movie(500, midnight_utc(2026, 12, 1), name='Made-up Film'))
    put_on_list(client.user, make_movie(501, cinema_at=midnight_utc(2026, 12, 16), name='Made-up Blockbuster'))

    response = client.get('/calendar/')

    assert response.status_code == 200
    page = response.content.decode()
    # Months and days in order, each month named once.
    assert page.index('November 2026') < page.index('Friday 6') < page.index('December 2026') < page.index('Tuesday 1')
    assert page.index('Tuesday 1') < page.index('Wednesday 16')
    assert page.count('November 2026') == 1 and page.count('December 2026') == 1
    assert 'S2E4 · The Return' in page and 'Streaming release' in page
    assert 'Made-up Blockbuster' in page and 'In cinemas' in page
    assert 'href="/series/1/"' in page and 'href="/movie/500/"' in page
    assert '00:00' not in page and 'midnight' not in page  # only the day, never an hour


def test_two_days_of_one_month_share_the_month_heading(client):
    series = make_series(1)
    make_episode(series, 1, 1, datetime.date(2026, 11, 6))
    make_episode(series, 1, 2, datetime.date(2026, 11, 13))
    put_on_list(client.user, series)

    page = client.get('/calendar/').content.decode()

    assert page.count('November 2026') == 1 and 'Friday 6' in page and 'Friday 13' in page


def test_the_page_says_so_when_nothing_is_coming_up(client):
    page = client.get('/calendar/').content.decode()

    assert 'Nothing coming up' in page and 'refresh_calendar' in page


def test_the_page_only_reads_what_is_saved_and_never_asks_tmdb(client, respx_mock, tmdb_key):
    series = make_series(1)
    make_episode(series, 1, 1, FRIDAY)
    put_on_list(client.user, series)
    put_on_list(client.user, make_movie(500, midnight_utc(2026, 11, 20)))
    # Nothing is mocked: any call to TMDB would fail the test.

    response = client.get('/calendar/')

    assert response.status_code == 200 and respx_mock.calls.call_count == 0


def test_each_account_sees_only_its_own_list(client):
    mine, theirs = make_series(1, 'Mine'), make_series(2, 'Theirs')
    make_episode(mine, 1, 1)
    make_episode(theirs, 1, 1)
    put_on_list(client.user, mine)
    put_on_list(make_client('someone-else').user, theirs)

    page = client.get('/calendar/').content.decode()

    assert 'Mine' in page and 'Theirs' not in page


def test_the_calendar_needs_a_login(db):
    response = Client().get('/calendar/')

    assert response.status_code == 302 and response['Location'].startswith('/login/')


def test_the_header_links_to_the_calendar(client):
    page = client.get('/').content.decode()

    assert 'href="/calendar/"' in page and '>Calendar<' in page


# --- collecting the dates when a title is added to To Watch -----------------------------------

TMDB = 'https://api.themoviedb.org/3'


@pytest.fixture
def tmdb_key(settings):
    settings.TMDB_API_KEY = 'made-up-secret-key'


def mock_movie_on_tmdb(respx_mock, tmdb_id, *entries):
    """TMDB's answers for a movie that is not saved yet: its details, and its release dates (the given entries)."""
    respx_mock.get(f'{TMDB}/movie/{tmdb_id}').respond(
        json={'id': tmdb_id, 'title': f'Made-up Movie {tmdb_id}', 'release_date': '2027-03-11'}
    )
    respx_mock.get(f'{TMDB}/movie/{tmdb_id}/release_dates').respond(
        json={'results': [{'iso_3166_1': 'US', 'release_dates': list(entries)}]}
    )


def mock_series_on_tmdb(respx_mock, tmdb_id, air_date):
    """TMDB's answers for a series that is not saved yet: the series, and its one season with one episode."""
    respx_mock.get(f'{TMDB}/tv/{tmdb_id}').respond(
        json={
            'id': tmdb_id, 'name': f'Made-up Series {tmdb_id}', 'first_air_date': '2026-01-01',
            'status': 'Returning Series', 'seasons': [{'season_number': 1}],
        }
    )
    respx_mock.get(f'{TMDB}/tv/{tmdb_id}/season/1').respond(
        json={
            'season_number': 1,
            'episodes': [{'id': 9001, 'season_number': 1, 'episode_number': 1, 'name': 'Premiere', 'air_date': air_date}],
        }
    )


def add_to_watch(client, kind, tmdb_id):
    return client.post('/to-watch/add/', {'kind': kind, 'tmdb_id': tmdb_id})


def test_adding_a_movie_puts_it_on_the_calendar_at_once_without_running_the_job(client, respx_mock, tmdb_key):
    mock_movie_on_tmdb(
        respx_mock, 700, {'type': 3, 'release_date': '2027-03-11T00:00:00.000Z', 'certification': '', 'note': ''}
    )

    add_to_watch(client, 'movie', 700)

    page = client.get('/calendar/').content.decode()
    assert 'Made-up Movie 700' in page and 'In cinemas' in page and 'March 2027' in page and 'Thursday 11' in page


def test_adding_a_series_puts_its_upcoming_episode_on_the_calendar_at_once(client, respx_mock, tmdb_key):
    mock_series_on_tmdb(respx_mock, 800, FRIDAY.isoformat())

    add_to_watch(client, 'series', 800)

    assert coming(client.user) == [(FRIDAY, [('Made-up Series 800', 'S1E1 · Premiere')])]


def test_a_movie_with_no_dates_yet_is_still_added_and_just_not_on_the_calendar(client, respx_mock, tmdb_key):
    mock_movie_on_tmdb(respx_mock, 700)

    response = add_to_watch(client, 'movie', 700)

    assert response.status_code == 302
    assert ToWatchItem.objects.filter(user=client.user, title__tmdb_id=700, removed_at=None).exists()
    assert coming(client.user) == []


def test_adding_still_works_when_tmdb_cannot_give_the_dates(client, respx_mock, tmdb_key):
    mock_movie_on_tmdb(respx_mock, 700)
    respx_mock.get(f'{TMDB}/movie/700/release_dates').mock(side_effect=httpx.ConnectError('no network'))
    mock_series_on_tmdb(respx_mock, 800, FRIDAY.isoformat())
    respx_mock.get(f'{TMDB}/tv/800/season/1').mock(side_effect=httpx.ConnectError('no network'))

    movie_response = add_to_watch(client, 'movie', 700)
    series_response = add_to_watch(client, 'series', 800)

    assert movie_response.status_code == 302 and series_response.status_code == 302
    assert ToWatchItem.objects.filter(user=client.user, removed_at=None).count() == 2
    assert coming(client.user) == []  # the next `refresh_calendar` run collects them
    assert Title.objects.get(tmdb_id=800).episodes_refreshed_at is None  # nothing half saved


def test_adding_a_title_that_is_already_on_the_list_asks_tmdb_nothing_more(client, respx_mock, tmdb_key):
    mock_movie_on_tmdb(respx_mock, 700)
    add_to_watch(client, 'movie', 700)
    asked = respx_mock.calls.call_count

    add_to_watch(client, 'movie', 700)

    assert respx_mock.calls.call_count == asked


def test_a_series_another_account_added_a_moment_ago_is_not_asked_for_again(client, respx_mock, tmdb_key):
    mock_series_on_tmdb(respx_mock, 800, FRIDAY.isoformat())
    add_to_watch(client, 'series', 800)
    asked = respx_mock.calls.call_count
    other = make_client('someone-else')

    add_to_watch(other, 'series', 800)

    assert respx_mock.calls.call_count == asked
    assert coming(other.user) == [(FRIDAY, [('Made-up Series 800', 'S1E1 · Premiere')])]


def test_adding_a_movie_again_after_removing_it_collects_its_dates_again(client, respx_mock, tmdb_key):
    mock_movie_on_tmdb(respx_mock, 700)
    add_to_watch(client, 'movie', 700)
    client.post('/to-watch/remove/', {'kind': 'movie', 'tmdb_id': 700})
    respx_mock.get(f'{TMDB}/movie/700/release_dates').respond(
        json={'results': [{'iso_3166_1': 'US', 'release_dates': [{'type': 4, 'release_date': '2027-05-01T00:00:00.000Z'}]}]}
    )

    add_to_watch(client, 'movie', 700)

    assert coming(client.user) == [(datetime.date(2027, 5, 1), [('Made-up Movie 700', 'Streaming release')])]
