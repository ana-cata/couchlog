import datetime
import re

import pytest
import time_machine
from django.contrib.auth.models import User
from django.test import Client

from core.episodes import dropped_tab
from core.models import DroppedSeries, Episode, Profile, Title, ToWatchItem, Watch

# The fixed "today": 8 pm UTC on 28 Oct 2026 (still the 28th in Lisbon).
NOW = datetime.datetime(2026, 10, 28, 20, 0, tzinfo=datetime.UTC)
LONG_AGO = datetime.date(2011, 4, 17)
TOMORROW = datetime.date(2026, 10, 29)

SEARCH_URL = 'https://api.themoviedb.org/3/search/multi'
ADDRESS = '/series/1/'


@pytest.fixture(autouse=True)
def clock():
    with time_machine.travel(NOW, tick=False):
        yield


@pytest.fixture(autouse=True)
def tmdb_key(settings):
    settings.TMDB_API_KEY = 'made-up-secret-key'


def make_client(name, zone='Europe/Lisbon'):
    account = User.objects.create_user(username=name, password='made-up-password')
    Profile.objects.create(user=account, timezone=zone)
    client = Client()
    client.force_login(account)
    client.user = account
    return client


def make_series(tmdb_id=1, status='Returning Series'):
    # Episodes are fresh, so opening the page never asks TMDB.
    return Title.objects.create(
        kind='series',
        tmdb_id=tmdb_id,
        title=f'Made-up Series {tmdb_id}',
        status=status,
        episodes_refreshed_at=NOW,
    )


def make_episode(series, season, number, air_date=LONG_AGO):
    tmdb_id = series.tmdb_id * 1000 + season * 100 + number
    return Episode.objects.create(
        title=series, tmdb_id=tmdb_id, season_number=season, episode_number=number, air_date=air_date
    )


@pytest.fixture
def me(db):
    """A logged-in account with a series on its To Watch list: two episodes aired, one coming up tomorrow."""
    client = make_client('made-up-user')
    series = make_series()
    client.series = series
    client.first, client.second = make_episode(series, 1, 1), make_episode(series, 1, 2)
    make_episode(series, 1, 3, air_date=TOMORROW)
    ToWatchItem.objects.create(user=client.user, title=series)
    return client


LINK = f'href="{ADDRESS}"'  # a link to the series. Its name is not used: the "dropped" message has it too.


def page(client, url):
    return client.get(url).content.decode()


def same_page(client, url):
    """The page as text, without the security token every form carries, which is new on each visit."""
    return re.sub(r'(name="csrfmiddlewaretoken" value=")[^"]+', r'\1', page(client, url))


def tiles(html):
    return re.findall(r'class="tile" href="([^"]+)"', html)


def screens(client):
    """What the four tabs list, as tile addresses: To Watch, Watching, Finished, Dropped."""
    urls = ('/series/', '/series/watching/', '/series/finished/', '/series/dropped/')
    return tuple(tiles(page(client, url)) for url in urls)


def mark(client, episode):
    return client.post('/watched/episode/add/', {'episode_id': episode.id})


def drop(client, tmdb_id=1, follow=False):
    return client.post('/series/drop/', {'kind': 'series', 'tmdb_id': tmdb_id, 'next': ADDRESS}, follow=follow)


def bring_back(client, tmdb_id=1, follow=False):
    return client.post('/series/bring-back/', {'kind': 'series', 'tmdb_id': tmdb_id, 'next': ADDRESS}, follow=follow)


def snapshot():
    """Every row dropping must not touch: the episodes, the watches, the To Watch entries and the titles."""
    return [list(model.objects.order_by('id').values()) for model in (Episode, Watch, ToWatchItem, Title)]


# --- the tabs ---------------------------------------------------------------------------------


def test_dropping_a_series_you_are_watching_moves_it_to_dropped_only(me):
    mark(me, me.first)
    assert screens(me) == ([], [ADDRESS], [], [])

    drop(me)

    assert screens(me) == ([], [], [], [ADDRESS])


def test_dropping_a_series_you_never_started_moves_it_from_to_watch_to_dropped(me):
    assert screens(me) == ([ADDRESS], [], [], [])

    drop(me)
    assert screens(me) == ([], [], [], [ADDRESS])

    bring_back(me)
    assert screens(me) == ([ADDRESS], [], [], [])


def test_a_finished_series_can_be_dropped_and_comes_back_finished(me):
    Title.objects.filter(id=me.series.id).update(status='Ended')
    mark(me, me.first)
    mark(me, me.second)
    assert screens(me) == ([], [], [ADDRESS], [])

    drop(me)
    assert screens(me) == ([], [], [], [ADDRESS])

    bring_back(me)
    assert screens(me) == ([], [], [ADDRESS], [])


def test_bringing_it_back_puts_everything_back_as_it_was(me):
    mark(me, me.first)
    rows, tab_lists = snapshot(), screens(me)
    home, calendar = same_page(me, '/'), same_page(me, '/calendar/')

    drop(me)
    assert snapshot() == rows  # dropping changes no watch and no To Watch entry
    assert screens(me) != tab_lists

    bring_back(me)
    assert snapshot() == rows
    assert screens(me) == tab_lists == ([], [ADDRESS], [], [])
    assert same_page(me, '/') == home
    assert same_page(me, '/calendar/') == calendar
    assert not DroppedSeries.objects.exists()


def test_the_history_of_a_dropped_series_stays(me):
    mark(me, me.first)
    watch = Watch.objects.get()

    drop(me)

    assert list(Watch.objects.all()) == [watch]


def test_marking_an_episode_of_a_dropped_series_keeps_it_dropped(me):
    drop(me)

    mark(me, me.first)

    assert screens(me) == ([], [], [], [ADDRESS])
    assert Watch.objects.count() == 1


def test_the_dropped_tab_lists_the_series_dropped_last_first(db):
    account = User.objects.create_user(username='made-up-user', password='made-up-password')
    earlier, later = make_series(1), make_series(2)
    DroppedSeries.objects.create(user=account, title=earlier, dropped_at=NOW - datetime.timedelta(days=2))
    DroppedSeries.objects.create(user=account, title=later, dropped_at=NOW)

    assert [series.tmdb_id for series in dropped_tab(account)] == [2, 1]


def test_the_dropped_tab_is_marked_and_says_so_when_empty(me):
    html = page(me, '/series/dropped/')

    assert 'href="/series/dropped/" aria-current="page">Dropped</a>' in html
    assert 'No dropped series' in html
    assert 'href="/series/finished/">Finished</a>' in html  # the other tabs link to it too


def test_the_dropped_tab_shows_plain_tiles_without_a_to_watch_button(me):
    drop(me)

    html = page(me, '/series/dropped/')

    assert 'Made-up Series 1' in html and 'class="tile"' in html
    assert 'To Watch</span>' not in html and 'action="/to-watch/' not in html


# --- Up Next and the Calendar -----------------------------------------------------------------


def test_a_dropped_series_is_not_in_up_next(me):
    mark(me, me.first)  # the next episode is the second one
    assert LINK in page(me, '/')

    drop(me)
    html = page(me, '/')
    assert LINK not in html
    assert 'Nothing to watch next.' in html

    bring_back(me)
    assert LINK in page(me, '/')


@pytest.mark.parametrize('started', [True, False])
def test_a_dropped_series_is_not_on_the_calendar(me, started):
    if started:
        mark(me, me.first)  # in Watching; it is on the To Watch list too
    else:
        assert not Watch.objects.exists()  # only on the To Watch list
    assert LINK in page(me, '/calendar/')

    drop(me)
    assert LINK not in page(me, '/calendar/')

    bring_back(me)
    assert LINK in page(me, '/calendar/')


def test_a_film_on_the_calendar_is_not_affected(me):
    film = Title.objects.create(
        kind='movie', tmdb_id=603, title='Made-up Movie', cinema_at=datetime.datetime(2026, 12, 16, tzinfo=datetime.UTC)
    )
    ToWatchItem.objects.create(user=me.user, title=film)

    drop(me)

    assert 'Made-up Movie' in page(me, '/calendar/')


# --- each account on its own ------------------------------------------------------------------


def test_dropping_only_changes_the_account_that_did_it(me):
    other = make_client('second-user')
    ToWatchItem.objects.create(user=other.user, title=me.series)
    mark(other, me.first)

    drop(me)

    assert screens(me) == ([], [], [], [ADDRESS])
    assert screens(other) == ([], [ADDRESS], [], [])


def test_nobody_can_bring_back_a_series_somebody_else_dropped(me):
    other = make_client('second-user')
    drop(me)

    response = bring_back(other, follow=True)

    assert 'is not in your Dropped list' in response.content.decode()
    assert screens(me) == ([], [], [], [ADDRESS])


# --- the buttons ------------------------------------------------------------------------------


def test_dropping_says_so_and_goes_back_to_the_page(me):
    response = drop(me, follow=True)

    assert response.redirect_chain == [(ADDRESS, 302)]
    assert 'is under Series → Dropped now' in response.content.decode()


def test_bringing_back_says_so_and_goes_back_to_the_page(me):
    drop(me)

    response = bring_back(me, follow=True)

    assert response.redirect_chain == [(ADDRESS, 302)]
    assert 'Brought “Made-up Series 1” back' in response.content.decode()


def test_dropping_twice_still_leaves_one_entry(me):
    drop(me)
    response = drop(me, follow=True)

    assert 'is already in your Dropped list' in response.content.decode()
    assert DroppedSeries.objects.count() == 1


def test_bringing_back_a_series_that_is_not_dropped_changes_nothing(me):
    rows = snapshot()

    response = bring_back(me, follow=True)

    assert 'is not in your Dropped list' in response.content.decode()
    assert snapshot() == rows


def test_a_film_cannot_be_dropped(me):
    Title.objects.create(kind='movie', tmdb_id=603, title='Made-up Movie')

    assert me.post('/series/drop/', {'kind': 'movie', 'tmdb_id': 603}).status_code == 400
    assert not DroppedSeries.objects.exists()


def test_a_series_that_was_never_saved_is_not_found(me):
    assert drop(me, tmdb_id=999).status_code == 404
    assert bring_back(me, tmdb_id=999).status_code == 404


@pytest.mark.django_db
@pytest.mark.parametrize('url', ['/series/dropped/', '/series/drop/', '/series/bring-back/'])
def test_the_dropped_pages_are_closed_when_logged_out(client, url):
    response = client.post(url) if url != '/series/dropped/' else client.get(url)

    assert response.status_code == 302
    assert response['Location'].startswith('/login/')


@pytest.mark.parametrize('url', ['/series/drop/', '/series/bring-back/'])
def test_the_buttons_only_accept_a_button_press(me, url):
    assert me.get(url).status_code == 405


# --- the series page --------------------------------------------------------------------------


def test_the_series_page_does_not_offer_stop_watching_for_a_series_only_on_the_list(me):
    html = page(me, ADDRESS)

    # Nothing is marked, so there is nothing to stop. It leaves the list with its Remove button.
    assert 'Stop watching' not in html
    assert 'action="/series/drop/"' not in html
    assert 'Bring back' not in html
    assert 'Remove from To Watch' in html


def test_the_series_page_offers_stop_watching_for_a_started_series_that_is_on_the_list_too(me):
    mark(me, me.first)

    html = page(me, ADDRESS)

    assert 'Stop watching' in html
    assert 'action="/series/drop/"' in html
    assert 'Bring back' not in html


def test_the_series_page_offers_stop_watching_for_a_started_series_not_on_the_list(me):
    ToWatchItem.objects.all().delete()
    mark(me, me.first)

    assert 'Stop watching' in page(me, ADDRESS)


def test_the_series_page_does_not_offer_stop_watching_for_a_series_you_never_touched(me):
    ToWatchItem.objects.all().delete()

    html = page(me, ADDRESS)

    assert 'Stop watching' not in html
    assert 'Bring back' not in html


def test_the_page_of_a_dropped_series_says_so_and_offers_bring_back(me):
    drop(me)

    html = page(me, ADDRESS)

    assert 'You stopped watching this series.' in html
    assert 'action="/series/bring-back/"' in html and 'Bring back' in html
    assert 'Stop watching' not in html
    # No To Watch button either: the Dropped note takes its place.
    assert 'To Watch</span>' not in html and 'action="/to-watch/' not in html
    assert 'In your Dropped list' in html


def test_the_episodes_of_a_dropped_series_are_still_on_its_page(me):
    drop(me)

    html = page(me, ADDRESS)

    assert f'name="episode_id" value="{me.first.id}"' in html


# --- search -----------------------------------------------------------------------------------


def made_up_result(media_type, tmdb_id, name):
    key = 'title' if media_type == 'movie' else 'name'
    return {'media_type': media_type, 'id': tmdb_id, key: name, 'poster_path': None, 'overview': ''}


def test_search_shows_a_dropped_series_as_dropped_without_an_add_button(me, respx_mock):
    respx_mock.get(SEARCH_URL).respond(
        json={
            'page': 1,
            'results': [
                made_up_result('tv', 1, 'Made-up Series 1'),
                made_up_result('tv', 2, 'Made-up Series 2'),
                # A film that shares the series' number is a different title.
                made_up_result('movie', 1, 'Made-up Movie'),
            ],
        }
    )
    drop(me)

    html = page(me, '/search/?q=made-up')

    assert html.count('In your Dropped list') == 1
    assert html.count('>Add to To Watch<') == 2  # the other series and the film (one button each)
    assert re.search(r'class="tile" href="/series/1/"', html)  # the dropped one still opens its page


def test_search_for_another_account_shows_the_normal_button(me, respx_mock):
    respx_mock.get(SEARCH_URL).respond(json={'page': 1, 'results': [made_up_result('tv', 1, 'Made-up Series 1')]})
    other = make_client('second-user')
    drop(me)

    html = page(other, '/search/?q=made-up')

    assert 'In your Dropped list' not in html
    assert html.count('>Add to To Watch<') == 1  # one button


def test_search_brings_the_button_back_after_bringing_the_series_back(me, respx_mock):
    respx_mock.get(SEARCH_URL).respond(json={'page': 1, 'results': [made_up_result('tv', 1, 'Made-up Series 1')]})
    drop(me)
    bring_back(me)

    html = page(me, '/search/?q=made-up')

    assert 'In your Dropped list' not in html
    assert 'Remove from To Watch' in html  # it is still on my list, as it was
