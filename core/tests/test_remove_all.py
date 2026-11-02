"""Remove from all lists: a dropped series leaves every list, with its history, rating and note."""

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
    Rating,
    RemovedSeries,
    Title,
    ToWatchItem,
    Watch,
)

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


def drop(client, tmdb_id=1):
    return client.post('/series/drop/', {'kind': 'series', 'tmdb_id': tmdb_id})


def remove_all(client, tmdb_id=1, follow=False):
    return client.post('/series/remove-all/', {'kind': 'series', 'tmdb_id': tmdb_id}, follow=follow)


def undo(client, tmdb_id=1, follow=False):
    return client.post('/series/remove-all/undo/', {'kind': 'series', 'tmdb_id': tmdb_id}, follow=follow)


def rate(client, stars=4, note='Made-up note', tmdb_id=1):
    return Rating.objects.create(
        user=client.user, title=Title.objects.get(kind='series', tmdb_id=tmdb_id), stars=stars, note=note
    )


def rows():
    """Every row Remove from all lists deletes and Undo writes back, with ids, dates and all."""
    return [list(model.objects.order_by('id').values()) for model in (Watch, ToWatchItem, DroppedSeries, Rating)]


def other_rows():
    """Every row it must never touch: the titles, the episodes and the copies of other series."""
    return [list(model.objects.order_by('id').values()) for model in (Title, Episode)]


def make_finished(me):
    """The series ended and both aired episodes are watched: it is under Finished."""
    Title.objects.filter(id=me.series.id).update(status='Ended')
    mark(me, me.first)
    mark(me, me.second)


# --- the page: the button in the corner, and the To Watch button that goes -----------------------


@pytest.mark.parametrize('tab', ['watching', 'finished'])
def test_a_series_under_watching_or_finished_has_neither_a_to_watch_button_nor_the_corner_button(me, tab):
    if tab == 'finished':
        make_finished(me)
    else:
        mark(me, me.first)
    assert screens(me)[1 if tab == 'watching' else 2] == [ADDRESS]
    assert ToWatchItem.objects.filter(removed_at=None).exists()  # it is on the list, so the button used to show

    html = page(me, ADDRESS)

    assert 'Remove from To Watch' not in html and 'Add to To Watch' not in html
    assert 'action="/to-watch/' not in html
    assert 'Remove from all lists' not in html and 'action="/series/remove-all/"' not in html


def test_a_started_series_that_is_not_on_the_list_has_no_add_button_and_no_corner_button(me):
    ToWatchItem.objects.all().delete()
    mark(me, me.first)

    html = page(me, ADDRESS)

    assert 'Add to To Watch' not in html
    assert 'Remove from all lists' not in html


def test_a_series_only_on_the_to_watch_list_keeps_its_button_and_has_no_corner_button(me):
    html = page(me, ADDRESS)

    assert 'Remove from To Watch' in html
    assert 'Remove from all lists' not in html


def test_a_series_nobody_touched_keeps_the_add_button_and_has_no_corner_button(me):
    ToWatchItem.objects.all().delete()

    html = page(me, ADDRESS)

    assert 'Add to To Watch' in html
    assert 'Remove from all lists' not in html


def test_a_dropped_series_has_the_corner_button_and_still_says_it_is_dropped(me):
    drop(me)

    html = page(me, ADDRESS)

    assert 'Remove from all lists' in html
    assert 'In your Dropped list' in html
    assert 'Bring back' in html


def test_the_corner_button_follows_the_flow_and_is_gone_again_after_bringing_the_series_back(me):
    """To Watch -> Watching -> Dropped is the only way to it. Bring back puts the series in Watching: no button."""
    assert 'Remove from all lists' not in page(me, ADDRESS)  # To Watch
    mark(me, me.first)
    assert 'Remove from all lists' not in page(me, ADDRESS)  # Watching
    drop(me)
    assert 'Remove from all lists' in page(me, ADDRESS)  # Dropped
    me.post('/series/bring-back/', {'kind': 'series', 'tmdb_id': 1})
    assert 'Remove from all lists' not in page(me, ADDRESS)  # Watching again


def test_a_film_page_has_no_corner_button(me, respx_mock):
    respx_mock.get('https://api.themoviedb.org/3/movie/603').respond(
        json={'id': 603, 'title': 'Made-up Movie', 'release_date': '1999-03-31', 'overview': 'A made-up story.'}
    )
    film = Title.objects.create(kind='movie', tmdb_id=603, title='Made-up Movie', year='1999')
    ToWatchItem.objects.create(user=me.user, title=film)

    html = page(me, '/movie/603/')

    assert 'Remove from all lists' not in html
    assert 'Remove from To Watch' in html


def test_the_question_names_the_series_and_what_goes(me):
    mark(me, me.first)
    mark(me, me.second)
    rate(me)
    drop(me)

    html = page(me, ADDRESS)

    assert 'data-confirm="Remove “Made-up Series 1” from all your lists?' in html
    assert 'Its 2 watches will be deleted, with your rating and note.' in html
    assert 'You can undo for 10 seconds.' in html
    assert 'onsubmit="return confirm(this.dataset.confirm)"' in html


def test_the_question_says_so_when_there_is_one_watch_and_no_rating(me):
    mark(me, me.first)
    drop(me)

    assert 'Its 1 watch will be deleted.' in page(me, ADDRESS)


def test_the_question_does_not_mention_a_rating_that_is_not_there(me):
    mark(me, me.first)
    drop(me)

    html = page(me, ADDRESS)

    assert 'rating' not in re.search(r'data-confirm="([^"]*)"', html).group(1)


def test_search_shows_no_to_watch_button_for_a_started_series(me, respx_mock):
    respx_mock.get(SEARCH_URL).respond(
        json={
            'page': 1,
            'results': [
                {'media_type': 'tv', 'id': 1, 'name': 'Made-up Series 1', 'poster_path': None, 'overview': ''},
                {'media_type': 'tv', 'id': 2, 'name': 'Made-up Series 2', 'poster_path': None, 'overview': ''},
                # A film that shares the series' number is a different title.
                {'media_type': 'movie', 'id': 1, 'title': 'Made-up Movie', 'poster_path': None, 'overview': ''},
            ],
        }
    )
    mark(me, me.first)

    html = page(me, '/search/?q=made-up')

    assert 'Remove from To Watch' not in html
    assert html.count('Add to To Watch') == 2  # the other series and the film
    assert re.search(r'class="tile" href="/series/1/"', html)  # the series still opens its page


# --- removing ---------------------------------------------------------------------------------


def test_removing_a_series_from_watching_takes_it_off_every_list_and_deletes_everything_of_it(me):
    mark(me, me.first)
    mark(me, me.second)
    rate(me)
    assert screens(me) == ([], [ADDRESS], [], [])

    remove_all(me)

    assert screens(me) == ([], [], [], [])
    assert (Watch.objects.count(), ToWatchItem.objects.count(), DroppedSeries.objects.count()) == (0, 0, 0)
    assert Rating.objects.count() == 0
    assert Title.objects.filter(id=me.series.id).exists()  # the series itself is not mine to delete


def test_removing_a_finished_series(me):
    make_finished(me)
    assert screens(me) == ([], [], [ADDRESS], [])

    remove_all(me)

    assert screens(me) == ([], [], [], [])
    assert not Watch.objects.exists()


def test_removing_a_dropped_series(me):
    mark(me, me.first)
    drop(me)
    assert screens(me) == ([], [], [], [ADDRESS])

    remove_all(me)

    assert screens(me) == ([], [], [], [])
    assert not DroppedSeries.objects.exists() and not Watch.objects.exists() and not ToWatchItem.objects.exists()


def test_removing_a_dropped_series_that_was_never_started(me):
    drop(me)

    remove_all(me)

    assert screens(me) == ([], [], [], [])
    assert not DroppedSeries.objects.exists() and not ToWatchItem.objects.exists()


def test_a_removed_series_is_gone_from_up_next_and_the_calendar(me):
    mark(me, me.first)
    assert ADDRESS in page(me, '/') and ADDRESS in page(me, '/calendar/')

    remove_all(me)

    assert f'href="{ADDRESS}"' not in page(me, '/')
    assert f'href="{ADDRESS}"' not in page(me, '/calendar/')


def test_a_removed_series_page_is_like_one_nobody_touched(me):
    mark(me, me.first)

    remove_all(me)
    html = page(me, ADDRESS)

    assert 'Add to To Watch' in html
    assert 'Remove from all lists' not in html
    assert 'aria-label="Mark episode 1 as not watched"' not in html


def test_removing_goes_to_series_to_watch_and_says_so(me):
    mark(me, me.first)

    response = remove_all(me, follow=True)

    assert response.redirect_chain == [('/series/', 302)]
    html = response.content.decode()
    assert 'Removed “Made-up Series 1” from all your lists, with its history.' in html


def test_removing_only_touches_that_series(me):
    other = make_series(2)
    make_episode(other, 1, 1)
    ToWatchItem.objects.create(user=me.user, title=other)
    mark(me, me.first)
    mark(me, Episode.objects.get(title=other))
    rate(me, tmdb_id=2)

    remove_all(me)

    assert Watch.objects.get().title == other
    assert ToWatchItem.objects.get().title == other
    assert Rating.objects.get().title == other
    assert screens(me) == ([], ['/series/2/'], [], [])


def test_removing_only_touches_the_account_that_did_it(me):
    other = make_client('second-user')
    ToWatchItem.objects.create(user=other.user, title=me.series)
    mark(other, me.first)
    rate(other)
    mark(me, me.first)

    remove_all(me)

    assert screens(me) == ([], [], [], [])
    assert screens(other) == ([], [ADDRESS], [], [])
    assert Watch.objects.get().user == other.user
    assert Rating.objects.get().user == other.user


def test_a_series_on_no_list_says_so_and_changes_nothing(me):
    ToWatchItem.objects.all().delete()

    response = remove_all(me, follow=True)

    assert 'is not on any of your lists' in response.content.decode()
    assert not RemovedSeries.objects.exists()


def test_a_film_cannot_be_removed_this_way(me):
    Title.objects.create(kind='movie', tmdb_id=603, title='Made-up Movie')

    assert me.post('/series/remove-all/', {'kind': 'movie', 'tmdb_id': 603}).status_code == 400
    assert not RemovedSeries.objects.exists()


def test_a_series_that_was_never_saved_is_not_found(me):
    assert remove_all(me, tmdb_id=999).status_code == 404
    assert undo(me, tmdb_id=999).status_code == 404


@pytest.mark.django_db
@pytest.mark.parametrize('url', ['/series/remove-all/', '/series/remove-all/undo/'])
def test_the_buttons_are_closed_when_logged_out(client, url):
    response = client.post(url)

    assert response.status_code == 302
    assert response['Location'].startswith('/login/')


@pytest.mark.parametrize('url', ['/series/remove-all/', '/series/remove-all/undo/'])
def test_the_buttons_only_accept_a_button_press(me, url):
    mark(me, me.first)
    before = rows()

    assert me.get(url).status_code == 405
    assert rows() == before


# --- undo -------------------------------------------------------------------------------------


def test_undo_puts_everything_back_as_it_was(me):
    # Dates of my own, a rewatch, a rating and a note: Undo has to bring back each one as it was.
    Watch.objects.create(
        user=me.user, title=me.series, episode=me.first, watched_on=datetime.date(2026, 9, 1),
        created_at=NOW - datetime.timedelta(days=57),
    )
    Watch.objects.create(
        user=me.user, title=me.series, episode=me.first, watched_on=datetime.date(2026, 10, 2),
        created_at=NOW - datetime.timedelta(days=26),
    )
    Watch.objects.create(
        user=me.user, title=me.series, episode=me.second, watched_on=None,
        created_at=NOW - datetime.timedelta(days=3),
    )
    rate(me, stars=5, note='Made-up note, with “quotes” and\nsecond line')
    before, tab_lists = rows(), screens(me)
    home, calendar, series_page = same_page(me, '/'), same_page(me, '/calendar/'), same_page(me, ADDRESS)
    assert tab_lists == ([], [ADDRESS], [], [])

    remove_all(me)
    assert rows() == [[], [], [], []]

    undo(me)
    assert rows() == before
    assert screens(me) == tab_lists
    assert same_page(me, '/') == home
    assert same_page(me, '/calendar/') == calendar
    assert same_page(me, ADDRESS) == series_page
    assert other_rows() == [list(model.objects.order_by('id').values()) for model in (Title, Episode)]
    assert not RemovedSeries.objects.exists()


def test_undo_brings_back_a_dropped_series_and_a_hand_removed_to_watch_entry(me):
    mark(me, me.first)
    drop(me)
    item = ToWatchItem.objects.get()
    item.removed_at = NOW - datetime.timedelta(days=1)  # taken off the list by hand, long ago
    item.save()
    before = rows()

    remove_all(me)
    undo(me)

    assert rows() == before
    assert screens(me) == ([], [], [], [ADDRESS])


def test_undo_brings_back_the_link_between_a_to_watch_entry_and_the_watch_that_took_it_off(me):
    # Marking a film as watched takes it off To Watch, and "Mark as not watched" puts it back: that link must survive.
    film = Title.objects.create(kind='movie', tmdb_id=603, title='Made-up Movie')
    film_item = ToWatchItem.objects.create(user=me.user, title=film)
    mark(me, me.first)
    watch = Watch.objects.get()
    ToWatchItem.objects.filter(title=me.series).update(removed_at=NOW, removed_by_watch=watch)

    remove_all(me)
    undo(me)

    assert ToWatchItem.objects.get(title=me.series).removed_by_watch_id == watch.id
    assert ToWatchItem.objects.get(id=film_item.id).removed_at is None


def test_undo_says_so_and_goes_to_series_to_watch(me):
    mark(me, me.first)
    remove_all(me)

    response = undo(me, follow=True)

    assert response.redirect_chain == [('/series/', 302)]
    assert 'Put “Made-up Series 1” back on all your lists, with its history.' in response.content.decode()


def test_undo_is_refused_after_10_seconds_and_nothing_comes_back(me):
    mark(me, me.first)
    remove_all(me)
    RemovedSeries.objects.update(removed_at=NOW - datetime.timedelta(seconds=11))

    response = undo(me, follow=True)

    assert 'It is too late to undo removing “Made-up Series 1”' in response.content.decode()
    assert rows() == [[], [], [], []]
    assert not RemovedSeries.objects.exists()  # the copy of the history is gone for good


def test_undo_still_works_just_inside_10_seconds(me):
    mark(me, me.first)
    remove_all(me)
    RemovedSeries.objects.update(removed_at=NOW - datetime.timedelta(seconds=9))

    undo(me)

    assert screens(me) == ([], [ADDRESS], [], [])


def test_undo_is_refused_when_the_series_was_changed_since_and_that_change_stays(me):
    mark(me, me.first)
    remove_all(me)
    # Back on the To Watch list from Search, before pressing Undo.
    me.post('/to-watch/add/', {'kind': 'series', 'tmdb_id': 1, 'next': '/search/'})
    after_adding = rows()

    response = undo(me, follow=True)

    assert 'was changed since it was removed, so it was not put back' in response.content.decode()
    assert rows() == after_adding
    assert not Watch.objects.exists()


def test_undo_with_nothing_to_undo_changes_nothing(me):
    mark(me, me.first)
    before = rows()

    response = undo(me, follow=True)

    assert 'There is nothing to undo for that series.' in response.content.decode()
    assert rows() == before


def test_undo_twice_puts_it_back_once(me):
    mark(me, me.first)
    before = rows()
    remove_all(me)
    undo(me)

    response = undo(me, follow=True)

    assert 'There is nothing to undo' in response.content.decode()
    assert rows() == before


def test_nobody_can_undo_a_removal_somebody_else_made(me):
    other = make_client('second-user')
    mark(me, me.first)
    remove_all(me)

    response = undo(other, follow=True)

    assert 'There is nothing to undo for that series.' in response.content.decode()
    assert rows() == [[], [], [], []]
    assert RemovedSeries.objects.count() == 1


def test_two_series_can_be_removed_and_each_undone_on_its_own(me):
    other = make_series(2)
    make_episode(other, 1, 1)
    mark(me, me.first)
    mark(me, Episode.objects.get(title=other))
    before = rows()

    remove_all(me)
    remove_all(me, tmdb_id=2)
    assert rows() == [[], [], [], []]
    undo(me, tmdb_id=2)
    assert screens(me) == ([], ['/series/2/'], [], [])
    undo(me)

    assert rows() == before


def test_removing_again_after_an_undo_can_be_undone_again(me):
    mark(me, me.first)
    before = rows()

    remove_all(me)
    undo(me)
    remove_all(me)
    undo(me)

    assert rows() == before


# --- "Recently removed" on Series -> To Watch -----------------------------------------------------


def test_the_removed_series_is_offered_with_an_undo_on_series_to_watch(me):
    mark(me, me.first)
    remove_all(me)

    html = page(me, '/series/')

    assert 'Recently removed' in html
    assert 'Made-up Series 1' in html and 'from all lists, with its history' in html
    assert 'action="/series/remove-all/undo/"' in html
    assert 'You can undo a removal for 10 seconds.' in html
    assert tiles(html) == []


def test_it_is_listed_with_the_series_taken_off_the_list_by_hand_newest_first(me):
    other = make_series(2)
    ToWatchItem.objects.create(user=me.user, title=other, removed_at=NOW - datetime.timedelta(seconds=5))
    mark(me, me.first)
    remove_all(me)

    html = page(me, '/series/')

    assert html.index('Made-up Series 1') < html.index('Made-up Series 2')
    assert 'action="/series/remove-all/undo/"' in html and 'action="/to-watch/undo/"' in html


def test_the_block_checks_again_when_the_undo_time_runs_out(me):
    mark(me, me.first)
    remove_all(me)

    html = page(me, '/series/')

    assert 'hx-get="/to-watch/removed/?kind=series"' in html
    assert re.search(r'hx-trigger="load delay:\d+s"', html)


def test_after_10_seconds_the_block_is_empty_and_the_copy_is_deleted(me):
    mark(me, me.first)
    remove_all(me)
    RemovedSeries.objects.update(removed_at=NOW - datetime.timedelta(seconds=11))

    html = page(me, '/to-watch/removed/?kind=series')

    assert 'Made-up Series 1' not in html and 'Undo' not in html
    assert not RemovedSeries.objects.exists()


def test_the_next_removal_deletes_expired_copies_of_my_other_series(me):
    other = make_series(2)
    make_episode(other, 1, 1)
    mark(me, me.first)
    mark(me, Episode.objects.get(title=other))
    remove_all(me)
    RemovedSeries.objects.update(removed_at=NOW - datetime.timedelta(minutes=5))

    remove_all(me, tmdb_id=2)

    assert [copy.title.tmdb_id for copy in RemovedSeries.objects.all()] == [2]


def test_the_block_never_shows_another_accounts_removals(me):
    other = make_client('second-user')
    mark(me, me.first)
    remove_all(me)

    assert 'Made-up Series 1' not in page(other, '/series/')
    assert 'Recently removed' not in page(other, '/series/')


def test_the_movies_page_never_shows_a_removed_series(me):
    mark(me, me.first)
    remove_all(me)

    html = page(me, '/movies/')  # only the message about the removal is shown there, once

    assert 'Recently removed' not in html and 'remove-all/undo' not in html
