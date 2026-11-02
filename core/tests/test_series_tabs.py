import datetime
import re

import pytest
import time_machine
from django.contrib.auth.models import User
from django.test import Client

from core.episodes import series_tabs
from core.models import DroppedSeries, Episode, Profile, Title, ToWatchItem, Watch

# The fixed "today" for the screen tests: 8 pm UTC on 28 Oct 2026 (still the 28th in Lisbon).
NOW = datetime.datetime(2026, 10, 28, 20, 0, tzinfo=datetime.UTC)
TODAY = datetime.date(2026, 10, 28)
LONG_AGO = datetime.date(2011, 4, 17)
TOMORROW = datetime.date(2026, 10, 29)


@pytest.fixture
def user(db):
    return User.objects.create_user(username='made-up-user', password='made-up-password')


def make_series(tmdb_id=1, status='Returning Series'):
    return Title.objects.create(kind='series', tmdb_id=tmdb_id, title=f'Made-up Series {tmdb_id}', status=status)


def make_episode(series, season, number, air_date=LONG_AGO):
    tmdb_id = series.tmdb_id * 1000 + season * 100 + number
    return Episode.objects.create(
        title=series, tmdb_id=tmdb_id, season_number=season, episode_number=number, air_date=air_date
    )


def make_watch(user, episode, created_at=None):
    watch = Watch.objects.create(user=user, title=episode.title, episode=episode, watched_on=TODAY)
    if created_at:
        Watch.objects.filter(id=watch.id).update(created_at=created_at)
    return watch


def tabs(user, today=TODAY):
    """Which series (by TMDB id) are under Watching and under Finished."""
    watching, finished = series_tabs(user, today)
    return [series.tmdb_id for series in watching], [series.tmdb_id for series in finished]


# --- the rules --------------------------------------------------------------------------------


def test_a_series_with_nothing_watched_is_in_neither_tab(user):
    series = make_series()
    make_episode(series, 1, 1)

    assert tabs(user) == ([], [])


def test_a_series_with_an_episode_watched_is_watching_even_if_it_is_on_no_list(user):
    series = make_series()
    first, _second = make_episode(series, 1, 1), make_episode(series, 1, 2)
    make_watch(user, first)

    assert tabs(user) == ([1], [])
    assert not ToWatchItem.objects.exists()


def test_a_series_that_is_caught_up_but_still_running_stays_in_watching(user):
    series = make_series(status='Returning Series')
    make_watch(user, make_episode(series, 1, 1))  # the only episode that has aired

    assert tabs(user) == ([1], [])


def test_a_series_that_ended_but_is_not_fully_watched_stays_in_watching(user):
    series = make_series(status='Ended')
    make_watch(user, make_episode(series, 1, 1))
    make_episode(series, 1, 2)  # aired, not watched

    assert tabs(user) == ([1], [])


@pytest.mark.parametrize('status', ['Ended', 'Canceled', 'Cancelled'])
def test_a_series_that_ended_and_is_fully_watched_is_finished(user, status):
    series = make_series(status=status)
    make_watch(user, make_episode(series, 1, 1))
    make_watch(user, make_episode(series, 1, 2))

    assert tabs(user) == ([], [1])


@pytest.mark.parametrize('status', ['', 'Returning Series', 'In Production', 'Planned', 'Pilot'])
def test_a_fully_watched_series_that_has_not_ended_is_not_finished(user, status):
    series = make_series(status=status)
    make_watch(user, make_episode(series, 1, 1))

    assert tabs(user) == ([1], [])


def test_specials_do_not_have_to_be_watched_to_finish_a_series(user):
    series = make_series(status='Ended')
    make_watch(user, make_episode(series, 1, 1))
    make_episode(series, 0, 1)  # a special, never watched

    assert tabs(user) == ([], [1])


def test_watching_only_a_special_counts_as_started_but_not_as_finished(user):
    series = make_series(status='Ended')
    make_watch(user, make_episode(series, 0, 1))
    make_episode(series, 1, 1)

    assert tabs(user) == ([1], [])


def test_an_ended_series_with_no_regular_episodes_aired_is_never_finished(user):
    series = make_series(status='Ended')
    make_watch(user, make_episode(series, 0, 1))  # only a special exists

    assert tabs(user) == ([1], [])


def test_episodes_that_have_not_aired_or_have_no_date_do_not_block_finishing(user):
    series = make_series(status='Ended')
    make_watch(user, make_episode(series, 1, 1))
    make_episode(series, 1, 2, air_date=TOMORROW)
    make_episode(series, 1, 3, air_date=None)

    assert tabs(user) == ([], [1])


def test_an_episode_that_airs_today_counts_as_aired(user):
    series = make_series(status='Ended')
    make_watch(user, make_episode(series, 1, 1))
    make_episode(series, 1, 2, air_date=TODAY)  # aired today, not watched

    assert tabs(user) == ([1], [])


def test_whether_an_episode_has_aired_follows_the_accounts_own_day(user):
    series = make_series(status='Ended')
    make_watch(user, make_episode(series, 1, 1))
    make_episode(series, 1, 2, air_date=TOMORROW)  # the 29th

    assert tabs(user, today=TODAY) == ([], [1])  # still the 28th in Lisbon: not aired yet
    assert tabs(user, today=TOMORROW) == ([1], [])  # already the 29th in Auckland: aired, not watched


def test_a_rewatch_counts_once(user):
    series = make_series(status='Ended')
    first = make_episode(series, 1, 1)
    make_episode(series, 1, 2)
    make_watch(user, first)
    make_watch(user, first)  # the same episode again: still only one of the two episodes

    assert tabs(user) == ([1], [])


def test_other_accounts_watches_do_not_count(user):
    other = User.objects.create_user(username='second-user', password='made-up-password')
    series = make_series(status='Ended')
    make_watch(other, make_episode(series, 1, 1))

    assert tabs(user) == ([], [])
    assert tabs(other) == ([], [1])


def test_the_series_marked_most_recently_come_first(user):
    old, middle, new = make_series(1), make_series(2), make_series(3)
    long_ago = datetime.datetime(2020, 1, 1, tzinfo=datetime.UTC)
    make_watch(user, make_episode(middle, 1, 1), created_at=long_ago + datetime.timedelta(days=5))
    make_watch(user, make_episode(new, 1, 1), created_at=long_ago + datetime.timedelta(days=9))
    make_watch(user, make_episode(old, 1, 1), created_at=long_ago)
    # An older mark on the middle series does not change where it is: the latest one counts.
    make_watch(user, make_episode(middle, 1, 2), created_at=long_ago + datetime.timedelta(days=1))

    assert tabs(user) == ([3, 2, 1], [])


# --- the screens ------------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clock():
    with time_machine.travel(NOW, tick=False) as traveller:
        yield traveller


def make_client(name, zone='Europe/Lisbon'):
    account = User.objects.create_user(username=name, password='made-up-password')
    Profile.objects.create(user=account, timezone=zone)
    client = Client()
    client.force_login(account)
    client.user = account
    return client


@pytest.fixture
def client_with_series(db):
    """A logged-in account, and a series with two aired episodes on its To Watch list."""
    client = make_client('made-up-user')
    series = make_series(status='Ended')
    first, second = make_episode(series, 1, 1), make_episode(series, 1, 2)
    ToWatchItem.objects.create(user=client.user, title=series)
    client.series, client.first, client.second = series, first, second
    return client


def page(client, url):
    return client.get(url).content.decode()


def tiles(html):
    return re.findall(r'class="tile" href="([^"]+)"', html)


def screens(client):
    """What the three tabs list, as tile addresses."""
    return tuple(tiles(page(client, url)) for url in ('/series/', '/series/watching/', '/series/finished/'))


def mark(client, episode):
    return client.post('/watched/episode/add/', {'episode_id': episode.id})


def unmark(client, watch):
    return client.post('/watched/remove/', {'watch_id': watch.id})


def snapshot():
    return [list(model.objects.order_by('id').values()) for model in (Episode, Watch, ToWatchItem, Title)]


def test_marking_an_episode_moves_a_series_from_to_watch_to_watching_then_finished(client_with_series):
    client = client_with_series
    address = '/series/1/'
    assert screens(client) == ([address], [], [])

    mark(client, client.first)
    assert screens(client) == ([], [address], [])  # started, but not finished

    mark(client, client.second)
    assert screens(client) == ([], [], [address])  # every aired episode watched, and the series ended


def test_unmarking_puts_the_series_back_exactly_where_it_was(client_with_series):
    client = client_with_series
    rows_before, screens_before = snapshot(), screens(client)

    mark(client, client.first)
    mark(client, client.second)
    assert snapshot() != rows_before and screens(client) != screens_before
    unmark(client, Watch.objects.get(episode=client.second))
    assert screens(client) == ([], ['/series/1/'], [])  # one step back: Watching again
    unmark(client, Watch.objects.get(episode=client.first))

    assert snapshot() == rows_before  # nothing else was changed by marking, so nothing is left behind
    assert screens(client) == screens_before == (['/series/1/'], [], [])


def test_a_series_opened_from_search_and_marked_shows_up_under_watching_at_once(client_with_series):
    client = client_with_series
    ToWatchItem.objects.all().delete()  # never added to the To Watch list
    assert screens(client) == ([], [], [])

    mark(client, client.first)

    assert screens(client) == ([], ['/series/1/'], [])
    assert not ToWatchItem.objects.exists()  # marking did not add it to the list


def test_marking_from_the_series_page_with_htmx_also_moves_it(client_with_series):
    client = client_with_series
    client.post('/watched/episode/add/', {'episode_id': client.first.id}, headers={'HX-Request': 'true'})

    assert screens(client) == ([], ['/series/1/'], [])


def test_each_account_has_its_own_tabs(client_with_series):
    client = client_with_series
    other = make_client('second-user')
    ToWatchItem.objects.create(user=other.user, title=client.series)

    mark(client, client.first)

    assert screens(client) == ([], ['/series/1/'], [])
    assert screens(other) == (['/series/1/'], [], [])


def test_the_tabs_show_plain_tiles_without_a_to_watch_button(client_with_series):
    client = client_with_series
    mark(client, client.first)

    html = page(client, '/series/watching/')

    assert 'Made-up Series 1' in html and 'class="tile"' in html
    assert 'To Watch</span>' not in html and 'action="/to-watch/' not in html


def test_the_watching_and_finished_tabs_say_so_when_empty(client_with_series):
    client = client_with_series

    assert 'No series in Watching yet' in page(client, '/series/watching/')
    assert 'No finished series yet' in page(client, '/series/finished/')


def test_the_current_tab_is_marked(client_with_series):
    client = client_with_series

    assert 'href="/series/watching/" aria-current="page">Watching</a>' in page(client, '/series/watching/')
    assert 'href="/series/finished/" aria-current="page">Finished</a>' in page(client, '/series/finished/')
    assert 'href="/series/" aria-current="page">To Watch</a>' in page(client, '/series/')


def test_a_series_in_watching_can_still_be_removed_from_the_list_and_stays_in_watching(client_with_series):
    client = client_with_series
    mark(client, client.first)

    client.post('/to-watch/remove/', {'kind': 'series', 'tmdb_id': 1})

    assert screens(client) == ([], ['/series/1/'], [])


def test_movies_are_not_affected(client_with_series):
    client = client_with_series
    film = Title.objects.create(kind='movie', tmdb_id=603, title='Made-up Movie')
    ToWatchItem.objects.create(user=client.user, title=film)
    mark(client, client.first)

    assert tiles(page(client, '/movies/')) == ['/movie/603/']


SERIES_TABS = ['/series/watching/', '/series/', '/series/finished/', '/series/dropped/']


@pytest.mark.parametrize('url', SERIES_TABS)
def test_the_tabs_are_in_the_order_watching_to_watch_finished_dropped(client_with_series, url):
    html = page(client_with_series, url)
    nav = html[html.index('<nav class="tabs"'):html.index('</nav>', html.index('<nav class="tabs"'))]

    assert re.findall(r'<a href="([^"]+)"[^>]*>([^<]+)</a>', nav) == [
        ('/series/watching/', 'Watching'),
        ('/series/', 'To Watch'),
        ('/series/finished/', 'Finished'),
        ('/series/dropped/', 'Dropped'),
    ]


def test_the_series_link_in_the_header_opens_watching(client_with_series):
    client = client_with_series
    header = page(client, '/')
    header = header[header.index('<header'):header.index('</header>')]
    address = re.search(r'<a href="([^"]+)">Series</a>', header).group(1)

    assert address == '/series/watching/'
    assert 'href="/series/watching/" aria-current="page">Watching</a>' in page(client, address)


def test_each_tab_still_lists_its_own_series_and_no_other(client_with_series):
    client = client_with_series  # series 1 is on the To Watch list, nothing marked
    watching, finished, dropped = make_series(2), make_series(3, status='Ended'), make_series(4)
    make_watch(client.user, make_episode(watching, 1, 1))
    make_watch(client.user, make_episode(finished, 1, 1))
    DroppedSeries.objects.create(user=client.user, title=dropped)

    lists = {url: tiles(page(client, url)) for url in SERIES_TABS}

    assert lists == {
        '/series/watching/': ['/series/2/'],
        '/series/': ['/series/1/'],
        '/series/finished/': ['/series/3/'],
        '/series/dropped/': ['/series/4/'],
    }


@pytest.mark.django_db
@pytest.mark.parametrize('url', ['/series/watching/', '/series/finished/'])
def test_the_new_tabs_are_closed_when_logged_out(client, url):
    response = client.get(url)

    assert response.status_code == 302
    assert response['Location'].startswith('/login/')


def test_the_day_follows_the_accounts_time_zone_on_the_finished_tab(client_with_series):
    client = client_with_series
    auckland = make_client('auckland-user', 'Pacific/Auckland')
    make_episode(client.series, 1, 3, air_date=TOMORROW)  # airs on the 29th
    make_watch(client.user, client.first)
    make_watch(client.user, client.second)
    make_watch(auckland.user, client.first)
    make_watch(auckland.user, client.second)

    # It is the 28th in Lisbon: the third episode has not aired, so the series is finished there.
    assert screens(client) == ([], [], ['/series/1/'])
    # It is already the 29th in Auckland: the third episode has aired and is not watched.
    assert screens(auckland) == ([], ['/series/1/'], [])
