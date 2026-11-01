"""The News section on Home: what comes out in the next days, with a banner and the days left.

News is worked out from what is saved (the Calendar's own list), so none of these tests mock TMDB for it; the one
that checks the page never asks TMDB would fail if it did. The clock is fixed, so the tests give the same result
every day.
"""

import datetime
import re

import pytest
import time_machine
from django.contrib.auth.models import User
from django.test import Client

from core.models import (
    DroppedSeries,
    Episode,
    Profile,
    Title,
    ToWatchItem,
    UpcomingEpisode,
    Watch,
)
from core.releases import countdown_label

# The fixed "today": 8 pm UTC on Wed 28 Oct 2026 (still the 28th in Lisbon, already the 29th in Auckland).
NOW = datetime.datetime(2026, 10, 28, 20, 0, tzinfo=datetime.UTC)
TODAY = datetime.date(2026, 10, 28)
BANNER = 'https://image.tmdb.org/t/p/w780/made-up-banner.jpg'
TMDB = 'https://api.themoviedb.org/3'


def in_days(days):
    return TODAY + datetime.timedelta(days=days)


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


def make_series(tmdb_id=1, backdrop_url=BANNER):
    return Title.objects.create(
        kind='series', tmdb_id=tmdb_id, title=f'Made-up Series {tmdb_id}', backdrop_url=backdrop_url
    )


def make_movie(tmdb_id=500, backdrop_url=BANNER, cinema_at=None, streaming_at=None):
    return Title.objects.create(
        kind='movie',
        tmdb_id=tmdb_id,
        title=f'Made-up Movie {tmdb_id}',
        backdrop_url=backdrop_url,
        cinema_at=cinema_at,
        streaming_at=streaming_at,
    )


def make_episode(series, season, number, air_date):
    tmdb_id = series.tmdb_id * 1000 + season * 100 + number
    return Episode.objects.create(
        title=series, tmdb_id=tmdb_id, season_number=season, episode_number=number, air_date=air_date
    )


def put_on_list(user, title):
    return ToWatchItem.objects.create(user=user, title=title)


def midnight_utc(day):
    """How TMDB gives a film's date: the day, at midnight UTC."""
    return datetime.datetime(day.year, day.month, day.day, tzinfo=datetime.UTC)


def coming_series(client, days, tmdb_id=1):
    """A series on the client's To Watch list with an episode that airs in `days` days."""
    series = make_series(tmdb_id)
    make_episode(series, 1, 1, in_days(days))
    put_on_list(client.user, series)
    return series


BANNER_HTML = re.compile(
    r'<a href="[^"]*">\s*(?:<img [^>]*alt="([^"]*)"[^>]*>|<span class="banner no-banner">([^<]*)</span>)\s*'
    r'<span class="news-days">([^<]*)</span>'
)


def home_page(client):
    response = client.get('/')
    assert response.status_code == 200
    return response.content.decode()


def banners(client):
    """What the News section shows, as [(title, label), ...] in the order shown."""
    return [(alt or name, label) for alt, name, label in BANNER_HTML.findall(home_page(client))]


# --- the label ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ('days', 'label'), [(0, 'today'), (1, 'tomorrow'), (2, 'in 2 days'), (3, 'in 3 days'), (6, 'in 6 days')]
)
def test_the_label_counts_the_days_from_today(days, label):
    assert countdown_label(in_days(days), TODAY) == label


def test_the_label_changes_at_midnight_in_the_accounts_own_day(client, clock):
    coming_series(client, 1)  # airs on Thu 29 Oct

    clock.move_to(datetime.datetime(2026, 10, 28, 23, 59, tzinfo=datetime.UTC))  # Lisbon is on UTC in winter time
    assert banners(client) == [('Made-up Series 1', 'tomorrow')]

    clock.move_to(datetime.datetime(2026, 10, 29, 0, 1, tzinfo=datetime.UTC))
    assert banners(client) == [('Made-up Series 1', 'today')]

    clock.move_to(datetime.datetime(2026, 10, 30, 0, 1, tzinfo=datetime.UTC))
    assert banners(client) == []  # it aired yesterday


def test_the_same_episode_has_a_different_label_in_another_time_zone(db):
    series = make_series(1)
    make_episode(series, 1, 1, in_days(1))  # Thu 29 Oct
    lisbon = make_client('lisbon-user', 'Europe/Lisbon')  # it is Wed 28 Oct there
    auckland = make_client('auckland-user', 'Pacific/Auckland')  # and Thu 29 Oct there
    put_on_list(lisbon.user, series)
    put_on_list(auckland.user, series)

    assert banners(lisbon) == [('Made-up Series 1', 'tomorrow')]
    assert banners(auckland) == [('Made-up Series 1', 'today')]


def test_a_films_day_is_the_day_in_the_accounts_time_zone(db):
    film = make_movie(streaming_at=midnight_utc(in_days(2)))  # midnight UTC, Fri 30 Oct
    lisbon = make_client('lisbon-user', 'Europe/Lisbon')
    new_york = make_client('new-york-user', 'America/New_York')  # still Thu 29 Oct evening there
    put_on_list(lisbon.user, film)
    put_on_list(new_york.user, film)

    assert banners(lisbon) == [('Made-up Movie 500', 'in 2 days')]
    assert banners(new_york) == [('Made-up Movie 500', 'tomorrow')]


# --- what is in the window ------------------------------------------------------------------------


def test_an_episode_in_3_days_is_in_news_with_its_banner_and_one_in_10_days_is_not(client):
    coming_series(client, 3, tmdb_id=1)
    coming_series(client, 10, tmdb_id=2)

    page = home_page(client)

    assert banners(client) == [('Made-up Series 1', 'in 3 days')]
    assert f'src="{BANNER}"' in page
    assert 'Made-up Series 2' not in page


@pytest.mark.parametrize(('days', 'shown'), [(0, True), (6, True), (7, False), (8, False)])
def test_less_than_7_days_away_is_in_news(client, days, shown):
    coming_series(client, days)

    assert (len(banners(client)) == 1) is shown


def test_the_window_setting_changes_what_news_shows(client, monkeypatch):
    coming_series(client, 3, tmdb_id=1)
    coming_series(client, 10, tmdb_id=2)

    assert [name for name, _ in banners(client)] == ['Made-up Series 1']

    monkeypatch.setattr('core.releases.NEWS_DAYS', 14)
    assert [name for name, _ in banners(client)] == ['Made-up Series 1', 'Made-up Series 2']

    monkeypatch.setattr('core.releases.NEWS_DAYS', 3)  # days 0 to 2
    assert banners(client) == []


def test_the_banners_come_nearest_day_first(client):
    coming_series(client, 5, tmdb_id=1)
    coming_series(client, 0, tmdb_id=2)
    coming_series(client, 2, tmdb_id=3)

    assert banners(client) == [
        ('Made-up Series 2', 'today'),
        ('Made-up Series 3', 'in 2 days'),
        ('Made-up Series 1', 'in 5 days'),
    ]


def test_nothing_coming_up_says_so(client, monkeypatch):
    coming_series(client, 10)

    assert 'Nothing coming out in the next 7 days.' in home_page(client)

    monkeypatch.setattr('core.releases.NEWS_DAYS', 1)
    assert 'Nothing coming out in the next 1 day.' in home_page(client)


# --- the same titles as the Calendar -------------------------------------------------------------------


def test_a_series_being_watched_is_in_news_even_when_it_is_on_no_list(client):
    series = make_series(1)
    watched = make_episode(series, 1, 1, datetime.date(2026, 10, 1))
    Watch.objects.create(user=client.user, title=series, episode=watched, watched_on=TODAY)
    make_episode(series, 1, 2, in_days(2))

    assert banners(client) == [('Made-up Series 1', 'in 2 days')]


def test_a_film_on_the_list_is_in_news_on_its_cinema_day_and_on_its_streaming_day(db):
    cinema_film = make_movie(500, cinema_at=midnight_utc(in_days(1)))
    streaming_film = make_movie(501, streaming_at=midnight_utc(in_days(4)))
    client = make_client()
    put_on_list(client.user, cinema_film)
    put_on_list(client.user, streaming_film)

    assert banners(client) == [('Made-up Movie 500', 'tomorrow'), ('Made-up Movie 501', 'in 4 days')]


def test_an_upcoming_episode_only_tvmaze_knows_is_in_news(client):
    series = make_series(1)
    put_on_list(client.user, series)
    UpcomingEpisode.objects.create(title=series, season_number=6, episode_number=3, name='TBA', air_date=in_days(5))

    assert banners(client) == [('Made-up Series 1', 'in 5 days')]


def test_what_the_calendar_leaves_out_is_not_in_news(client):
    dropped = coming_series(client, 2, tmdb_id=1)
    DroppedSeries.objects.create(user=client.user, title=dropped)
    make_episode(make_series(2), 1, 1, in_days(2))  # on no list, never started
    removed = coming_series(client, 2, tmdb_id=3)
    ToWatchItem.objects.filter(user=client.user, title=removed).update(removed_at=NOW)
    watched_film = make_movie(500, streaming_at=midnight_utc(in_days(2)))
    watch = Watch.objects.create(user=client.user, title=watched_film, watched_on=TODAY)
    ToWatchItem.objects.create(user=client.user, title=watched_film, removed_at=NOW, removed_by_watch=watch)
    only_a_special = make_series(4)
    make_episode(only_a_special, 0, 1, in_days(2))
    put_on_list(client.user, only_a_special)
    put_on_list(client.user, make_movie(501))  # a film with no date yet

    assert banners(client) == []


def test_each_account_sees_only_its_own_titles(client):
    coming_series(client, 2, tmdb_id=1)
    other = make_client('someone-else')
    coming_series(other, 3, tmdb_id=2)

    assert banners(client) == [('Made-up Series 1', 'in 2 days')]
    assert banners(other) == [('Made-up Series 2', 'in 3 days')]


# --- one banner for each title -------------------------------------------------------------------------


def test_several_episodes_of_one_series_on_the_same_day_are_one_banner(client):
    series = make_series(1)
    for number in (1, 2, 3):
        make_episode(series, 1, number, in_days(3))
    put_on_list(client.user, series)

    assert banners(client) == [('Made-up Series 1', 'in 3 days')]


def test_a_series_with_episodes_on_two_days_is_one_banner_on_the_nearest_day(client):
    series = make_series(1)
    make_episode(series, 1, 1, in_days(2))
    make_episode(series, 1, 2, in_days(5))
    put_on_list(client.user, series)

    assert banners(client) == [('Made-up Series 1', 'in 2 days')]


def test_a_film_with_a_cinema_and_a_streaming_day_in_the_window_is_one_banner_on_the_nearest(client):
    film = make_movie(cinema_at=midnight_utc(in_days(4)), streaming_at=midnight_utc(in_days(2)))
    put_on_list(client.user, film)

    assert banners(client) == [('Made-up Movie 500', 'in 2 days')]


# --- what a banner looks like ----------------------------------------------------------------------------


def test_a_banner_is_the_picture_with_the_days_left_and_opens_the_titles_page(client):
    coming_series(client, 3)

    page = home_page(client)

    assert '<a href="/series/1/">' in page
    assert f'src="{BANNER}" alt="Made-up Series 1"' in page
    assert 'no-banner' not in page
    # The title is only the picture's hidden description: it is written nowhere else on the page.
    assert page.count('Made-up Series 1') == 1


def test_a_title_with_no_banner_saved_shows_its_name_instead(client):
    series = make_series(1, backdrop_url='')
    make_episode(series, 1, 1, in_days(3))
    put_on_list(client.user, series)

    page = home_page(client)

    assert '<span class="banner no-banner">Made-up Series 1</span>' in page
    assert banners(client) == [('Made-up Series 1', 'in 3 days')]


def test_news_is_above_up_next(client):
    page = home_page(client)

    assert page.index('<h1>News</h1>') < page.index('<h1>Up Next</h1>')


# --- reading only -----------------------------------------------------------------------------------------


def snapshot():
    return (
        list(Title.objects.order_by('id').values()),
        list(Episode.objects.order_by('id').values()),
        list(ToWatchItem.objects.order_by('id').values()),
        list(Watch.objects.order_by('id').values()),
        list(DroppedSeries.objects.order_by('id').values()),
    )


def test_opening_home_changes_nothing_and_asks_tmdb_nothing(client, respx_mock):
    coming_series(client, 3, tmdb_id=1)
    coming_series(client, 0, tmdb_id=2)
    before = snapshot()

    home_page(client)
    home_page(client)

    # It only reads, so there is nothing to undo; an unmocked call to TMDB would have been an error.
    assert snapshot() == before
    assert respx_mock.calls.call_count == 0


def test_the_calendar_page_is_the_same_whatever_news_shows(client, monkeypatch):
    coming_series(client, 3, tmdb_id=1)
    coming_series(client, 10, tmdb_id=2)
    film = make_movie(streaming_at=midnight_utc(in_days(1)))
    put_on_list(client.user, film)

    page = client.get('/calendar/').content.decode()
    monkeypatch.setattr('core.releases.NEWS_DAYS', 30)
    with_a_wider_window = client.get('/calendar/').content.decode()

    assert page == with_a_wider_window
    assert 'Made-up Series 1' in page and 'Made-up Series 2' in page and 'Made-up Movie 500' in page
    assert 'in 3 days' not in page and 'tomorrow' not in page and 'news' not in page


# --- the banner is saved ------------------------------------------------------------------------------------


@pytest.fixture
def tmdb_key(settings):
    settings.TMDB_API_KEY = 'made-up-secret-key'


def test_adding_a_movie_saves_its_banner(client, respx_mock, tmdb_key):
    respx_mock.get(f'{TMDB}/movie/700').respond(
        json={'id': 700, 'title': 'Made-up Movie 700', 'backdrop_path': '/made-up-banner.jpg'}
    )

    client.post('/to-watch/add/', {'kind': 'movie', 'tmdb_id': 700})

    assert Title.objects.get(tmdb_id=700).backdrop_url == BANNER


def test_adding_a_series_saves_its_banner(client, respx_mock, tmdb_key):
    respx_mock.get(f'{TMDB}/tv/800').respond(
        json={'id': 800, 'name': 'Made-up Series 800', 'backdrop_path': '/made-up-banner.jpg', 'seasons': []}
    )

    client.post('/to-watch/add/', {'kind': 'series', 'tmdb_id': 800})

    assert Title.objects.get(tmdb_id=800).backdrop_url == BANNER


def test_a_title_tmdb_has_no_banner_for_is_added_with_none(client, respx_mock, tmdb_key):
    respx_mock.get(f'{TMDB}/movie/700').respond(json={'id': 700, 'title': 'Made-up Movie 700', 'backdrop_path': None})

    response = client.post('/to-watch/add/', {'kind': 'movie', 'tmdb_id': 700})

    assert response.status_code == 302
    assert Title.objects.get(tmdb_id=700).backdrop_url == ''
