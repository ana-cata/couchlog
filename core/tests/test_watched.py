import datetime
import re

import httpx
import pytest
import time_machine
from django.contrib.auth.models import User
from django.test import Client

from core.models import Profile, Title, ToWatchItem, Watch

MOVIE_URL = 'https://api.themoviedb.org/3/movie/603'
SERIES_URL = 'https://api.themoviedb.org/3/tv/1399'

# Made-up TMDB answers. The tests never call the real TMDB.
MADE_UP_MOVIE = {
    'id': 603,
    'title': 'Made-up Movie',
    'release_date': '1999-03-31',
    'poster_path': '/made-up-movie.jpg',
    'overview': 'A made-up story about a movie.',
}
MADE_UP_SERIES = {
    'id': 1399,
    'name': 'Made-up Series',
    'first_air_date': '2011-04-17',
    'poster_path': '/made-up-series.jpg',
    'overview': 'A made-up story about a series.',
}

# The fixed "now" for every test here: 8 pm UTC on 28 Oct 2026. In Lisbon that is still the 28th;
# in Auckland it is already the 29th, so the two show how "today" follows the account's time zone.
NOW = datetime.datetime(2026, 10, 28, 20, 0, tzinfo=datetime.UTC)
LONG_AGO = datetime.datetime(2020, 1, 15, 9, 30, tzinfo=datetime.UTC)


@pytest.fixture(autouse=True)
def tmdb_key(settings):
    settings.TMDB_API_KEY = 'made-up-secret-key'


@pytest.fixture(autouse=True)
def clock():
    with time_machine.travel(NOW, tick=False) as traveller:
        yield traveller


def make_client(name, zone='Europe/Lisbon'):
    """A browser logged in as a new account (with a time zone chosen, so no redirect to Profile)."""
    user = User.objects.create_user(username=name, password='made-up-password')
    Profile.objects.create(user=user, timezone=zone)
    client = Client()
    client.force_login(user)
    client.user = user
    return client


@pytest.fixture
def logged_in_client(db):
    return make_client('made-up-user')


@pytest.fixture
def movie_route(respx_mock):
    return respx_mock.get(MOVIE_URL).respond(json=MADE_UP_MOVIE)


def mark(client, kind='movie', tmdb_id=603, watched_on='2026-10-28', **extra):
    return client.post('/watched/add/', {'kind': kind, 'tmdb_id': tmdb_id, 'watched_on': watched_on, **extra})


def unmark(client, watch_id, **extra):
    return client.post('/watched/remove/', {'watch_id': watch_id, **extra})


def add_to_watch(client, tmdb_id=603):
    return client.post('/to-watch/add/', {'kind': 'movie', 'tmdb_id': tmdb_id})


def page(client, url):
    return client.get(url).content.decode()


def after(client, response):
    """The page a button press sends the browser to (with its message)."""
    return client.get(response['Location']).content.decode()


def tiles(html):
    return re.findall(r'class="tile" href="([^"]+)"', html)


def to_watch_snapshot():
    return list(ToWatchItem.objects.order_by('id').values())


def watch_snapshot():
    return list(Watch.objects.order_by('id').values())


def make_watch(user, number, watched_on):
    title = Title.objects.create(kind='movie', tmdb_id=number, title=f'Movie {number}', year='2000')
    return Watch.objects.create(user=user, title=title, watched_on=watched_on)


# --- the movie page -------------------------------------------------------------------------


def test_the_movie_page_offers_todays_date_in_my_own_time_zone(db, movie_route):
    lisbon, auckland = make_client('lisbon-user'), make_client('auckland-user', 'Pacific/Auckland')

    lisbon_page, auckland_page = page(lisbon, '/movie/603/'), page(auckland, '/movie/603/')

    assert 'Mark as watched' in lisbon_page
    assert 'name="watched_on" value="2026-10-28" max="2026-10-28"' in lisbon_page
    assert 'name="watched_on" value="2026-10-29" max="2026-10-29"' in auckland_page
    assert 'name="date_unknown"' in lisbon_page


def test_a_series_page_has_no_mark_as_watched(logged_in_client, respx_mock):
    respx_mock.get(SERIES_URL).respond(json=MADE_UP_SERIES)

    assert 'Mark as watched' not in page(logged_in_client, '/series/1399/')


def test_a_series_cannot_be_marked_as_watched(logged_in_client, respx_mock):
    respx_mock.get(SERIES_URL).respond(json=MADE_UP_SERIES)

    response = mark(logged_in_client, kind='series', tmdb_id=1399)

    assert response.status_code == 400
    assert Watch.objects.count() == 0


def test_the_movie_page_shows_the_date_it_was_watched_and_the_way_to_undo(logged_in_client, movie_route):
    response = mark(logged_in_client, watched_on='2026-03-05', next='/movie/603/')

    assert response['Location'] == '/movie/603/'
    html = after(logged_in_client, response)
    assert 'Marked “Made-up Movie” as watched.' in html
    assert '<strong>Watched</strong>' in html
    assert 'on 5 Mar 2026' in html
    assert 'Mark as not watched' in html
    assert 'Mark as watched' not in html  # a second watch is "Watch again" (see the rewatch tests below)


# --- marking --------------------------------------------------------------------------------


def test_marking_a_movie_puts_it_in_my_history_with_its_date(logged_in_client, movie_route):
    response = mark(logged_in_client, watched_on='2026-10-28')

    assert response.status_code == 302
    html = page(logged_in_client, '/movies/history/')  # a fresh request, like reloading the page
    assert tiles(html) == ['/movie/603/']
    assert 'Made-up Movie' in html
    assert 'Watched 28 Oct 2026' in html
    watch = Watch.objects.get()
    assert (watch.user, watch.title.tmdb_id, watch.watched_on) == (logged_in_client.user, 603, datetime.date(2026, 10, 28))


def test_marking_saves_the_tmdb_details_in_our_own_table_once(logged_in_client, movie_route):
    mark(logged_in_client)
    other = make_client('second-user')
    mark(other)

    saved = Title.objects.get()
    assert (saved.kind, saved.tmdb_id, saved.title, saved.year) == ('movie', 603, 'Made-up Movie', '1999')
    assert Watch.objects.count() == 2
    assert movie_route.call_count == 1  # the second account used our saved copy


def test_an_earlier_date_can_be_chosen(logged_in_client, movie_route):
    mark(logged_in_client, watched_on='2019-12-31')

    assert Watch.objects.get().watched_on == datetime.date(2019, 12, 31)
    assert 'Watched 31 Dec 2019' in page(logged_in_client, '/movies/history/')


def test_the_date_can_be_unknown(logged_in_client, movie_route):
    # The date box still holds a date; the ticked box wins.
    mark(logged_in_client, watched_on='2026-10-28', date_unknown='on')

    assert Watch.objects.get().watched_on is None
    assert 'Date unknown' in page(logged_in_client, '/movies/history/')
    assert '(date unknown)' in page(logged_in_client, '/movie/603/')


@pytest.mark.parametrize(
    ('watched_on', 'message'),
    [
        ('2026-10-29', 'That day has not happened yet.'),  # tomorrow, for an account in Lisbon
        ('', 'Pick the day you watched it'),
        ('not-a-date', 'Enter a valid date.'),
    ],
)
def test_a_date_that_makes_no_sense_is_refused_and_nothing_is_saved(logged_in_client, movie_route, watched_on, message):
    response = mark(logged_in_client, watched_on=watched_on)

    assert message in after(logged_in_client, response)
    assert Watch.objects.count() == 0
    assert Title.objects.count() == 0


def test_whether_a_day_is_in_the_future_depends_on_my_time_zone(db, movie_route):
    # 29 Oct is tomorrow in Lisbon but already today in Auckland.
    mark(make_client('lisbon-user'), watched_on='2026-10-29')
    assert Watch.objects.count() == 0

    mark(make_client('auckland-user', 'Pacific/Auckland'), watched_on='2026-10-29')
    assert Watch.objects.get().watched_on == datetime.date(2026, 10, 29)


def test_a_next_address_on_another_site_is_not_followed(logged_in_client, movie_route):
    response = mark(logged_in_client, next='https://elsewhere.example/')

    assert response['Location'] == '/movies/history/'


def test_tmdb_not_answering_gives_a_friendly_message_and_saves_nothing(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_URL).mock(side_effect=httpx.ConnectError('down'))

    response = mark(logged_in_client)

    assert 'Could not reach TMDB' in after(logged_in_client, response)
    assert Watch.objects.count() == 0
    assert Title.objects.count() == 0


def test_a_title_tmdb_does_not_have_is_not_found(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_URL).respond(status_code=404)

    assert mark(logged_in_client).status_code == 404
    assert Watch.objects.count() == 0


# --- the To Watch list ----------------------------------------------------------------------


def test_a_watched_movie_leaves_the_to_watch_list(logged_in_client, movie_route):
    add_to_watch(logged_in_client)
    assert tiles(page(logged_in_client, '/movies/')) == ['/movie/603/']

    mark(logged_in_client)

    html = page(logged_in_client, '/movies/')
    assert tiles(html) == []
    # It left because it was watched, not removed: no "Recently removed" and no 10-second Undo.
    assert 'Recently removed' not in html


def test_the_to_watch_undo_does_not_bring_back_a_watched_movie(logged_in_client, movie_route):
    add_to_watch(logged_in_client)
    mark(logged_in_client)
    before = to_watch_snapshot()

    response = logged_in_client.post('/to-watch/undo/', {'kind': 'movie', 'tmdb_id': 603})

    assert to_watch_snapshot() == before
    assert 'There is nothing to undo' in after(logged_in_client, response)


def test_marking_a_movie_that_was_not_on_the_list_does_not_put_it_there(logged_in_client, movie_route):
    mark(logged_in_client)

    assert ToWatchItem.objects.count() == 0
    assert tiles(page(logged_in_client, '/movies/')) == []


def test_a_watched_movie_can_be_added_to_to_watch_again(logged_in_client, movie_route):
    add_to_watch(logged_in_client)
    mark(logged_in_client)

    add_to_watch(logged_in_client)

    item = ToWatchItem.objects.get()
    assert (item.removed_at, item.removed_by_watch) == (None, None)
    assert tiles(page(logged_in_client, '/movies/')) == ['/movie/603/']
    assert Watch.objects.count() == 1  # still watched


# --- watching a film again --------------------------------------------------------------------


def test_watch_again_adds_a_watch_with_its_own_date_each_time(logged_in_client, movie_route):
    mark(logged_in_client, watched_on='2026-05-01')

    response = mark(logged_in_client, watched_on='2026-06-01')
    mark(logged_in_client, watched_on='2026-07-01')
    mark(logged_in_client, watched_on='2026-07-02', date_unknown='on')  # an older rewatch can have an unknown date

    days = [watch.watched_on for watch in Watch.objects.order_by('id')]
    assert days == [datetime.date(2026, 5, 1), datetime.date(2026, 6, 1), datetime.date(2026, 7, 1), None]
    assert 'Added another watch of “Made-up Movie”.' in after(logged_in_client, response)
    assert movie_route.call_count == 1  # the rewatches used our saved copy


def test_a_day_in_the_future_is_refused_for_a_rewatch_too(logged_in_client, movie_route):
    mark(logged_in_client, watched_on='2026-05-01')
    before = watch_snapshot()

    response = mark(logged_in_client, watched_on='2026-10-29')

    assert watch_snapshot() == before
    assert 'That day has not happened yet.' in after(logged_in_client, response)


def test_the_movie_page_offers_watch_again_and_lists_every_watch(logged_in_client, movie_route):
    assert 'Watch again' not in page(logged_in_client, '/movie/603/')  # nothing to watch again yet
    mark(logged_in_client, watched_on='2026-05-01')

    once = page(logged_in_client, '/movie/603/')
    assert '<strong>Watched</strong>' in once and 'Mark as not watched' in once
    assert 'Watch again' in once and 'Mark as watched' not in once

    mark(logged_in_client, watched_on='2026-06-01')
    twice = page(logged_in_client, '/movie/603/')
    assert '<strong>Watched 2 times</strong>' in twice
    assert twice.index('on 1 Jun 2026') < twice.index('on 1 May 2026')  # the newest first, like History
    assert twice.count('Remove this watch') == 2 and 'Mark as not watched' not in twice


def test_history_shows_every_watch_of_a_film_with_its_own_date(logged_in_client, movie_route):
    mark(logged_in_client, watched_on='2026-05-01')
    mark(logged_in_client, watched_on='2026-06-01')

    html = page(logged_in_client, '/movies/history/')

    assert tiles(html) == ['/movie/603/', '/movie/603/']
    assert html.index('Watched 1 Jun 2026') < html.index('Watched 1 May 2026')
    assert html.count('Remove this watch') == 2


def test_taking_the_watches_back_one_by_one_puts_everything_back_as_it_was(logged_in_client, movie_route):
    add_to_watch(logged_in_client)
    ToWatchItem.objects.update(added_at=LONG_AGO)
    before = to_watch_snapshot()
    for day in ('2026-05-01', '2026-06-01', '2026-07-01'):
        mark(logged_in_client, watched_on=day)
    first, second, third = Watch.objects.order_by('id').values_list('id', flat=True)

    for watch_id in (third, second):
        response = unmark(logged_in_client, watch_id)
        assert 'Removed one watch of “Made-up Movie”.' in after(logged_in_client, response)
        assert tiles(page(logged_in_client, '/movies/')) == []  # still watched, so still off To Watch
    assert list(Watch.objects.values_list('id', flat=True)) == [first]

    response = unmark(logged_in_client, first)

    assert 'It is back on your To Watch list.' in after(logged_in_client, response)
    assert Watch.objects.count() == 0
    assert to_watch_snapshot() == before  # on the list again, with its old date added


def test_taking_back_the_watch_that_took_the_film_off_the_list_keeps_it_off_while_others_remain(
    logged_in_client, movie_route
):
    add_to_watch(logged_in_client)
    ToWatchItem.objects.update(added_at=LONG_AGO)
    before = to_watch_snapshot()
    mark(logged_in_client, watched_on='2026-05-01')
    mark(logged_in_client, watched_on='2026-06-01')
    first, second = Watch.objects.order_by('id').values_list('id', flat=True)

    unmark(logged_in_client, first)  # the older watch, the one that took it off the list

    item = ToWatchItem.objects.get()
    assert item.removed_at is not None and item.removed_by_watch_id == second  # the entry follows the watch left
    html = page(logged_in_client, '/movies/')
    assert tiles(html) == [] and 'Recently removed' not in html

    unmark(logged_in_client, second)

    assert to_watch_snapshot() == before


def test_a_film_put_back_on_the_list_leaves_it_when_watched_again_and_returns_when_that_is_taken_back(
    logged_in_client, movie_route
):
    add_to_watch(logged_in_client)
    mark(logged_in_client, watched_on='2026-05-01')
    add_to_watch(logged_in_client)  # to watch it once more
    ToWatchItem.objects.update(added_at=LONG_AGO)
    before = to_watch_snapshot()
    assert tiles(page(logged_in_client, '/movies/')) == ['/movie/603/']

    mark(logged_in_client, watched_on='2026-06-01')  # a watched film leaves the list
    assert tiles(page(logged_in_client, '/movies/')) == []
    unmark(logged_in_client, Watch.objects.order_by('-id').first().id)

    assert Watch.objects.count() == 1  # the first watch is still there
    assert to_watch_snapshot() == before


def test_each_account_has_its_own_rewatches(logged_in_client, movie_route):
    add_to_watch(logged_in_client)
    mark(logged_in_client, watched_on='2026-05-01')
    mark(logged_in_client, watched_on='2026-06-01')
    other = make_client('second-user')
    mark(other, watched_on='2026-07-01')

    assert '<strong>Watched</strong>' in page(other, '/movie/603/')  # one watch, not three
    assert tiles(page(other, '/movies/history/')) == ['/movie/603/']

    mine = list(Watch.objects.filter(user=logged_in_client.user).order_by('id').values_list('id', flat=True))
    for watch_id in mine:
        unmark(logged_in_client, watch_id)

    assert Watch.objects.filter(user=other.user).count() == 1  # the other account's watch was never touched
    assert tiles(page(logged_in_client, '/movies/')) == ['/movie/603/']  # and mine do not count as theirs


# --- the history screen ---------------------------------------------------------------------


def test_history_lists_the_newest_watch_first_and_unknown_dates_last(logged_in_client):
    make_watch(logged_in_client.user, 1, datetime.date(2026, 1, 5))
    make_watch(logged_in_client.user, 2, datetime.date(2026, 3, 1))
    make_watch(logged_in_client.user, 3, None)
    make_watch(logged_in_client.user, 4, None)

    # Newest date first; among the unknown ones, the one saved last first.
    assert tiles(page(logged_in_client, '/movies/history/')) == ['/movie/2/', '/movie/1/', '/movie/4/', '/movie/3/']


def test_an_empty_history_says_so(logged_in_client):
    html = page(logged_in_client, '/movies/history/')

    assert 'Nothing in your history yet' in html
    assert tiles(html) == []


def test_each_account_has_its_own_history(logged_in_client, movie_route):
    mark(logged_in_client)
    other = make_client('second-user')

    assert tiles(page(logged_in_client, '/movies/history/')) == ['/movie/603/']
    assert tiles(page(other, '/movies/history/')) == []
    assert 'Mark as watched' in page(other, '/movie/603/')  # not marked for them


def test_history_is_a_tab_of_the_movies_section(logged_in_client):
    html = page(logged_in_client, '/movies/history/')

    assert 'href="/movies/history/" aria-current="page"' in html  # the tab you are on
    assert 'href="/movies/"' in html  # and the way back to the To Watch tab
    assert 'href="/history/"' not in page(logged_in_client, '/')  # no longer a link of its own in the header


def test_history_lists_films_only(logged_in_client):
    make_watch(logged_in_client.user, 1, datetime.date(2026, 1, 5))
    show = Title.objects.create(kind='series', tmdb_id=1399, title='Made-up Series', year='2011')
    Watch.objects.create(user=logged_in_client.user, title=show, watched_on=datetime.date(2026, 2, 5))

    assert tiles(page(logged_in_client, '/movies/history/')) == ['/movie/1/']


@pytest.mark.parametrize('method', ['get', 'post'])
@pytest.mark.parametrize('address', ['/movies/history/', '/history/', '/watched/add/', '/watched/remove/'])
def test_watching_pages_need_a_login(db, method, address):
    response = getattr(Client(), method)(address)

    assert response.status_code == 302
    assert response['Location'].startswith('/login/')


# --- undo -----------------------------------------------------------------------------------


def test_undo_puts_everything_back_as_it_was(logged_in_client, movie_route):
    add_to_watch(logged_in_client)
    ToWatchItem.objects.update(added_at=LONG_AGO)
    before = to_watch_snapshot()

    mark(logged_in_client)
    assert Watch.objects.count() == 1
    assert to_watch_snapshot() != before

    response = unmark(logged_in_client, Watch.objects.get().id)

    assert to_watch_snapshot() == before  # on the list again, with its old date added
    assert Watch.objects.count() == 0
    assert 'It is back on your To Watch list.' in after(logged_in_client, response)
    assert tiles(page(logged_in_client, '/movies/')) == ['/movie/603/']
    assert tiles(page(logged_in_client, '/movies/history/')) == []
    assert 'Mark as watched' in page(logged_in_client, '/movie/603/')


def test_undo_of_a_movie_that_was_never_on_the_list_leaves_the_list_alone(logged_in_client, movie_route):
    mark(logged_in_client)

    unmark(logged_in_client, Watch.objects.get().id)

    assert Watch.objects.count() == 0
    assert ToWatchItem.objects.count() == 0


def test_undo_does_not_bring_back_a_title_that_was_removed_by_hand_earlier(logged_in_client, movie_route):
    add_to_watch(logged_in_client)
    logged_in_client.post('/to-watch/remove/', {'kind': 'movie', 'tmdb_id': 603})
    ToWatchItem.objects.update(removed_at=LONG_AGO)
    before = to_watch_snapshot()

    mark(logged_in_client)
    assert to_watch_snapshot() == before  # it was not on the list, so marking changes nothing there
    unmark(logged_in_client, Watch.objects.get().id)

    assert to_watch_snapshot() == before
    assert tiles(page(logged_in_client, '/movies/')) == []


def test_undo_is_still_possible_days_later(logged_in_client, movie_route, clock):
    add_to_watch(logged_in_client)
    before = to_watch_snapshot()
    mark(logged_in_client)

    clock.shift(datetime.timedelta(days=3))  # far beyond the 10 seconds of the To Watch undo
    unmark(logged_in_client, Watch.objects.get().id)

    assert Watch.objects.count() == 0
    assert to_watch_snapshot() == before


def test_undo_from_the_history_screen_works(logged_in_client, movie_route):
    add_to_watch(logged_in_client)
    mark(logged_in_client)
    watch_id = Watch.objects.get().id
    assert f'name="watch_id" value="{watch_id}"' in page(logged_in_client, '/movies/history/')

    response = unmark(logged_in_client, watch_id, next='/movies/history/')

    assert response['Location'] == '/movies/history/'
    assert 'Nothing in your history yet' in after(logged_in_client, response)


def test_a_movie_can_be_marked_again_after_an_undo(logged_in_client, movie_route):
    mark(logged_in_client, watched_on='2026-05-01')
    unmark(logged_in_client, Watch.objects.get().id)

    mark(logged_in_client, watched_on='2026-06-01')

    assert Watch.objects.get().watched_on == datetime.date(2026, 6, 1)


def test_undoing_after_adding_it_to_to_watch_again_leaves_the_list_entry_alone(logged_in_client, movie_route):
    add_to_watch(logged_in_client)
    mark(logged_in_client)
    add_to_watch(logged_in_client)
    before = to_watch_snapshot()

    unmark(logged_in_client, Watch.objects.get().id)

    assert to_watch_snapshot() == before
    assert ToWatchItem.objects.count() == 1


def test_nobody_can_undo_someone_elses_watch(logged_in_client, movie_route):
    mark(logged_in_client)
    other = make_client('second-user')
    before = watch_snapshot()

    response = unmark(other, Watch.objects.get().id)

    assert watch_snapshot() == before
    assert 'not in your history' in after(other, response)


def test_undoing_a_watch_that_does_not_exist_changes_nothing(logged_in_client, movie_route):
    mark(logged_in_client)
    before = watch_snapshot()

    response = unmark(logged_in_client, 99999)

    assert watch_snapshot() == before
    assert 'not in your history' in after(logged_in_client, response)


def test_a_garbled_watch_number_is_refused(logged_in_client):
    assert unmark(logged_in_client, 'abc').status_code == 400
