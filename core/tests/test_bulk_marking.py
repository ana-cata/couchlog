"""Marking a whole season and "watched up to here": which episodes they save, and Undo in one step."""

import datetime
import re

import pytest
import time_machine
from django.contrib.auth.models import User
from django.test import Client

from core.models import Episode, Profile, Title, ToWatchItem, Watch

SERIES_URL = 'https://api.themoviedb.org/3/tv/1399'
SERIES_PAGE = '/series/1399/'

MADE_UP_SERIES = {
    'id': 1399,
    'name': 'Made-up Series',
    'first_air_date': '2011-04-17',
    'poster_path': '/made-up-series.jpg',
    'overview': 'A made-up story about a series.',
    'status': 'Returning Series',
    'seasons': [{'season_number': 0}, {'season_number': 1}, {'season_number': 2}, {'season_number': 3}],
}


def made_up_episode(season, number, tmdb_id, air_date, name=None):
    return {
        'id': tmdb_id,
        'season_number': season,
        'episode_number': number,
        'name': name or f'Made-up episode {season}x{number}',
        'air_date': air_date,
        'runtime': 45,
    }


# "Today" below is the 28th in Lisbon and already the 29th in Auckland. Season 1 has aired in full, season 2
# has one episode with no date and one that airs tomorrow (in Lisbon), and season 3 has not started.
SEASONS = {
    0: [made_up_episode(0, 1, 6000, '2010-01-01', name='Made-up special')],
    1: [
        made_up_episode(1, 1, 6001, '2011-04-17'),
        made_up_episode(1, 2, 6002, '2011-04-24'),
        made_up_episode(1, 3, 6003, '2011-05-01'),
    ],
    2: [
        made_up_episode(2, 1, 6101, '2011-05-08'),
        made_up_episode(2, 2, 6102, None),
        made_up_episode(2, 3, 6103, '2011-05-22'),
        made_up_episode(2, 4, 6104, '2026-10-29'),
    ],
    3: [made_up_episode(3, 1, 6201, '2999-01-01')],
}

# The fixed "now" for every test here: 8 pm UTC on 28 Oct 2026.
NOW = datetime.datetime(2026, 10, 28, 20, 0, tzinfo=datetime.UTC)
TODAY = datetime.date(2026, 10, 28)

HTMX = {'headers': {'HX-Request': 'true'}}


@pytest.fixture(autouse=True)
def tmdb_key(settings):
    settings.TMDB_API_KEY = 'made-up-secret-key'


@pytest.fixture(autouse=True)
def clock():
    with time_machine.travel(NOW, tick=False) as traveller:
        yield traveller


def make_client(name, zone='Europe/Lisbon', **options):
    """A browser logged in as a new account (with a time zone chosen, so no redirect to Profile)."""
    user = User.objects.create_user(username=name, password='made-up-password')
    Profile.objects.create(user=user, timezone=zone)
    client = Client(**options)
    client.force_login(user)
    client.user = user
    return client


@pytest.fixture
def logged_in_client(db):
    return make_client('made-up-user')


@pytest.fixture
def tmdb_series(respx_mock):
    """The made-up TMDB answers for the series and each of its seasons, by name so a test can change one."""
    routes = {'series': respx_mock.get(SERIES_URL).respond(json=MADE_UP_SERIES)}
    for number, episodes in SEASONS.items():
        routes[number] = respx_mock.get(f'{SERIES_URL}/season/{number}').respond(
            json={'season_number': number, 'episodes': episodes}
        )
    return routes


def page(client):
    return client.get(SERIES_PAGE).content.decode()


def after(client, response):
    """The page a button press sends the browser to (with its message)."""
    return client.get(response['Location']).content.decode()


def eid(tmdb_id):
    return Episode.objects.get(tmdb_id=tmdb_id).id


def mark_one(client, tmdb_id):
    return client.post('/watched/episode/add/', {'episode_id': eid(tmdb_id)})


def unmark_one(client, tmdb_id):
    watch = Watch.objects.get(user=client.user, episode__tmdb_id=tmdb_id)
    return client.post('/watched/remove/', {'watch_id': watch.id, 'episode_id': watch.episode_id})


def mark_season(client, number, next=SERIES_PAGE, **options):
    """Press "Mark season". The buttons on the page always send the page to come back to as `next`."""
    return client.post('/watched/season/add/', {'tmdb_id': 1399, 'season': number, 'next': next}, **options)


def up_to_here(client, tmdb_id, next=SERIES_PAGE, **options):
    return client.post('/watched/up-to/add/', {'episode_id': eid(tmdb_id), 'next': next}, **options)


def undo(client, batch, next=SERIES_PAGE, **options):
    return client.post('/watched/batch/remove/', {'batch': batch, 'next': next}, **options)


def last_batch():
    """The batch of the latest season or "up to here" press."""
    return Watch.objects.exclude(batch=None).order_by('-id').values_list('batch', flat=True).first()


def watched(user):
    """The TMDB ids of the episodes this account has marked."""
    return set(Watch.objects.filter(user=user, episode__isnull=False).values_list('episode__tmdb_id', flat=True))


def snapshot():
    """Everything saved about episodes, watches and the To Watch lists, to compare before and after."""
    return [list(model.objects.order_by('id').values()) for model in (Episode, Watch, ToWatchItem)]


def is_watched(html, number):
    """Whether the page shows episode `number` with the green button (it offers "not watched")."""
    return f'aria-label="Mark episode {number} as not watched"' in html


def without_tokens(html):
    """The page without the random CSRF tokens, so two loads of the same page can be compared."""
    return re.sub(r'name="csrfmiddlewaretoken" value="[^"]+"', '', html)


def row(html, tmdb_id):
    """The piece of the page that is one episode's row."""
    return re.search(rf'<li id="episode-{eid(tmdb_id)}".*?</li>', html, re.DOTALL).group(0)


def season_block(html, number):
    return re.search(rf'<details id="season-{number}".*?</details>', html, re.DOTALL).group(0)


@pytest.fixture
def opened(logged_in_client, tmdb_series):
    """The account, with the series opened once so its episodes are saved."""
    page(logged_in_client)
    return logged_in_client


# --- marking a whole season -------------------------------------------------------------------


def test_marking_a_season_saves_a_watch_for_each_episode_dated_the_day_it_was_pressed(opened):
    mark_season(opened, 1)

    assert watched(opened.user) == {6001, 6002, 6003}
    watches = Watch.objects.all()
    assert {watch.watched_on for watch in watches} == {TODAY}
    assert {watch.title.tmdb_id for watch in watches} == {1399}
    assert {watch.user for watch in watches} == {opened.user}
    assert len({watch.batch for watch in watches}) == 1 and watches[0].batch is not None  # one press, one batch


def test_a_season_skips_episodes_that_have_not_aired_or_have_no_date(opened):
    mark_season(opened, 2)

    assert watched(opened.user) == {6101, 6103}  # not 6102 (no date) and not 6104 (airs tomorrow)


def test_a_season_leaves_episodes_already_marked_alone(opened, clock):
    mark_one(opened, 6002)
    earlier = Watch.objects.get()
    clock.shift(datetime.timedelta(days=1))  # the season is pressed on another day

    mark_season(opened, 1)

    earlier.refresh_from_db()
    assert (earlier.watched_on, earlier.batch) == (TODAY, None)  # the same watch, the same date, not in the batch
    assert watched(opened.user) == {6001, 6002, 6003}
    assert Watch.objects.count() == 3  # no second watch for 6002
    assert set(Watch.objects.filter(batch=last_batch()).values_list('episode__tmdb_id', flat=True)) == {6001, 6003}


def test_a_season_with_nothing_new_changes_nothing_and_says_so(opened):
    after(opened, mark_season(opened, 1))
    before = snapshot()

    response = mark_season(opened, 1)

    assert snapshot() == before
    html = after(opened, response)
    assert 'Nothing new to mark in Season 1.' in html
    assert 'name="batch"' not in html  # nothing to undo


def test_a_season_none_of_whose_episodes_has_aired_marks_nothing(opened):
    before = snapshot()

    mark_season(opened, 3)

    assert snapshot() == before


def test_the_specials_are_marked_as_a_season_of_their_own(opened):
    after(opened, mark_season(opened, 1))
    assert 6000 not in watched(opened.user)  # a regular season leaves the specials alone

    html = after(opened, mark_season(opened, 0))

    assert watched(opened.user) == {6000, 6001, 6002, 6003}
    assert 'Marked 1 episode in the Specials as watched.' in html


def test_marking_a_season_starts_the_series_and_leaves_the_to_watch_list_alone(opened):
    ToWatchItem.objects.create(user=opened.user, title=Title.objects.get())
    to_watch = list(ToWatchItem.objects.values())
    assert 'Made-up Series' in opened.get('/series/').content.decode()

    mark_season(opened, 1)

    assert 'Made-up Series' in opened.get('/series/watching/').content.decode()
    assert 'Made-up Series' not in opened.get('/series/').content.decode()
    assert list(ToWatchItem.objects.values()) == to_watch


def test_what_has_aired_follows_the_accounts_time_zone(opened):
    auckland = make_client('auckland-user', 'Pacific/Auckland')  # already the 29th there

    mark_season(opened, 2)
    mark_season(auckland, 2)

    assert watched(opened.user) == {6101, 6103}
    assert watched(auckland.user) == {6101, 6103, 6104}
    assert {watch.watched_on for watch in Watch.objects.filter(user=auckland.user)} == {datetime.date(2026, 10, 29)}


# --- watched up to here -----------------------------------------------------------------------


def test_up_to_here_marks_every_aired_episode_before_it_across_seasons(opened):
    up_to_here(opened, 6103)

    # All of season 1, then season 2 up to the chosen one. Not the episode without a date (6102), not the one
    # after (6104) and not the special.
    assert watched(opened.user) == {6001, 6002, 6003, 6101, 6103}
    assert {watch.watched_on for watch in Watch.objects.all()} == {TODAY}
    assert len({watch.batch for watch in Watch.objects.all()}) == 1


def test_up_to_here_in_the_first_season_marks_only_what_is_before_it(opened):
    up_to_here(opened, 6002)

    assert watched(opened.user) == {6001, 6002}


def test_up_to_here_leaves_episodes_already_marked_alone(opened):
    mark_one(opened, 6002)
    earlier = Watch.objects.get()

    up_to_here(opened, 6003)

    earlier.refresh_from_db()
    assert earlier.batch is None
    assert watched(opened.user) == {6001, 6002, 6003}
    assert Watch.objects.count() == 3
    assert set(Watch.objects.filter(batch=last_batch()).values_list('episode__tmdb_id', flat=True)) == {6001, 6003}


def test_up_to_here_when_everything_before_it_is_marked_changes_nothing_and_says_so(opened):
    after(opened, up_to_here(opened, 6003))
    before = snapshot()

    html = after(opened, up_to_here(opened, 6003))

    assert snapshot() == before
    assert 'Nothing new to mark up to S1E3.' in html


def test_up_to_here_on_an_episode_that_is_marked_still_marks_the_ones_before_it(opened):
    mark_one(opened, 6003)

    up_to_here(opened, 6003)

    assert watched(opened.user) == {6001, 6002, 6003}


@pytest.mark.parametrize(
    ('tmdb_id', 'reason'), [(6104, 'S2E4 has not aired yet'), (6102, 'S2E2 has no air date yet')]
)
def test_up_to_here_on_an_episode_that_has_not_aired_is_refused(opened, tmdb_id, reason):
    html = after(opened, up_to_here(opened, tmdb_id))

    assert reason in html
    assert Watch.objects.count() == 0


def test_up_to_here_is_not_offered_for_a_special(opened):
    assert up_to_here(opened, 6000).status_code == 400
    assert Watch.objects.count() == 0


# --- undo -------------------------------------------------------------------------------------


def test_undoing_a_season_puts_everything_back_as_it_was(opened):
    ToWatchItem.objects.create(user=opened.user, title=Title.objects.get())
    mark_one(opened, 6101)  # marked before, and not part of the season press below
    before = snapshot()
    gray_page = page(opened)

    after(opened, mark_season(opened, 1))
    assert snapshot() != before and is_watched(page(opened), 3)
    html = after(opened, undo(opened, last_batch()))

    assert snapshot() == before
    assert 'Undone: 3 episodes marked as not watched.' in html
    assert without_tokens(page(opened)) == without_tokens(gray_page)  # the page is what it was


def test_undoing_up_to_here_puts_everything_back_as_it_was(opened):
    mark_one(opened, 6002)  # marked before: it must still be marked, with the same watch, afterwards
    before = snapshot()
    gray_page = page(opened)

    after(opened, up_to_here(opened, 6103))
    assert snapshot() != before
    after(opened, undo(opened, last_batch()))

    assert snapshot() == before
    assert without_tokens(page(opened)) == without_tokens(gray_page)


def test_undo_works_any_time_later(opened, clock):
    mark_season(opened, 1)
    batch = last_batch()
    clock.shift(datetime.timedelta(days=10))  # long after marking (a login lasts 2 weeks)

    undo(opened, batch)

    assert Watch.objects.count() == 0


def test_undo_removes_exactly_what_that_press_added(opened):
    mark_one(opened, 6101)
    mark_season(opened, 1)
    batch = last_batch()
    # Un-mark one episode by hand, then mark it again by hand: that new watch is not part of the press.
    unmark_one(opened, 6002)
    mark_one(opened, 6002)

    undo(opened, batch)

    assert watched(opened.user) == {6101, 6002}
    assert Watch.objects.get(episode__tmdb_id=6002).batch is None


def test_undo_after_one_episode_was_un_marked_by_hand_removes_the_rest(opened):
    mark_season(opened, 1)
    batch = last_batch()
    unmark_one(opened, 6002)

    undo(opened, batch)

    assert Watch.objects.count() == 0


def test_undoing_twice_says_there_is_nothing_to_undo(opened):
    mark_season(opened, 1)
    batch = last_batch()
    undo(opened, batch)
    before = snapshot()

    html = after(opened, undo(opened, batch))

    assert snapshot() == before
    assert 'Nothing to undo' in html


def test_a_season_can_be_marked_again_after_an_undo(opened):
    mark_season(opened, 1)
    undo(opened, last_batch())

    mark_season(opened, 1)

    assert watched(opened.user) == {6001, 6002, 6003}


def test_each_account_has_its_own_marks_and_its_own_undo(opened):
    other = make_client('second-user')
    mark_season(opened, 1)
    batch = last_batch()

    assert is_watched(page(opened), 1) and not is_watched(page(other), 1)

    # The second account cannot undo the first account's press...
    before = snapshot()
    assert 'Nothing to undo' in after(other, undo(other, batch))
    assert snapshot() == before
    # ...and pressing the season itself marks only its own.
    mark_season(other, 1)
    assert watched(opened.user) == watched(other.user) == {6001, 6002, 6003}
    undo(other, last_batch())
    assert watched(opened.user) == {6001, 6002, 6003} and watched(other.user) == set()


# --- episodes renumbered or added after a season was marked -----------------------------------


def test_after_tmdb_renumbers_the_season_marks_and_undo_still_hit_the_same_episodes(opened, tmdb_series, clock):
    after(opened, mark_season(opened, 1))
    first_batch = last_batch()
    # TMDB now has a new first episode, and what used to be episodes 1 to 3 are now 2 to 4.
    renumbered = [
        made_up_episode(1, 1, 6004, '2011-04-10', name='Made-up newcomer'),
        made_up_episode(1, 2, 6001, '2011-04-17'),
        made_up_episode(1, 3, 6002, '2011-04-24'),
        made_up_episode(1, 4, 6003, '2011-05-01'),
    ]
    tmdb_series[1].respond(json={'season_number': 1, 'episodes': renumbered})
    clock.shift(datetime.timedelta(days=2))

    html = page(opened)

    # The three still have their watches under their new numbers, and the newcomer is not marked.
    assert watched(opened.user) == {6001, 6002, 6003}
    assert is_watched(html, 2) and is_watched(html, 3) and is_watched(html, 4) and not is_watched(html, 1)

    # Marking the season again marks only the newcomer, in a batch of its own.
    after(opened, mark_season(opened, 1))
    assert watched(opened.user) == {6001, 6002, 6003, 6004}
    assert last_batch() != first_batch

    # Undoing the first press removes exactly its three episodes, wherever they are numbered now.
    undo(opened, first_batch)
    assert watched(opened.user) == {6004}


def test_up_to_here_follows_the_numbers_as_they_are_now(opened, tmdb_series, clock):
    renumbered = [made_up_episode(1, 4, 6001, '2011-04-17'), *SEASONS[1][1:]]  # the pilot is now the last one
    tmdb_series[1].respond(json={'season_number': 1, 'episodes': renumbered})
    clock.shift(datetime.timedelta(days=2))
    page(opened)

    up_to_here(opened, 6003)  # now episode 3: the pilot, numbered 4, is after it

    assert watched(opened.user) == {6002, 6003}


# --- the page ---------------------------------------------------------------------------------


def test_the_page_offers_a_season_button_where_something_has_aired(opened):
    html = page(opened)

    assert 'Mark Season 1 as watched' in html and 'Mark Season 2 as watched' in html
    assert 'Mark Specials as watched' in html
    assert 'season/add' not in season_block(html, 3)  # season 3 has not started: nothing to mark


def test_the_page_offers_up_to_here_only_on_regular_episodes_that_have_aired(opened):
    html = page(opened)

    for tmdb_id in (6001, 6002, 6003, 6101, 6103):
        assert 'Up to here' in row(html, tmdb_id)
    for tmdb_id in (6000, 6102, 6104, 6201):  # a special, no date, airs tomorrow, season 3
        assert 'Up to here' not in row(html, tmdb_id)


def test_up_to_here_is_there_on_a_marked_episode_too(opened):
    mark_one(opened, 6003)

    assert 'Up to here' in row(page(opened), 6003)


def test_the_buttons_use_htmx_so_the_page_does_not_reload(opened):
    mark_season(opened, 1)
    html = page(opened)

    assert 'hx-post="/watched/season/add/" hx-target="#bulk-notice" hx-swap="innerHTML"' in html
    assert 'hx-post="/watched/up-to/add/" hx-target="#bulk-notice" hx-swap="innerHTML"' in html
    assert '<div id="bulk-notice"' in html


# --- without htmx the page comes back with its notice and an Undo button ---------------------


def test_without_htmx_the_page_comes_back_with_a_notice_that_has_undo(opened):
    where = f'{SERIES_PAGE}?season=1#season-1'
    response = opened.post('/watched/season/add/', {'tmdb_id': 1399, 'season': 1, 'next': where})

    assert response.status_code == 302 and response['Location'] == where
    html = after(opened, response)
    assert 'Marked 3 episodes in Season 1 as watched.' in html
    assert f'name="batch" value="{last_batch()}"' in html
    assert 'Marked 3 episodes' not in page(opened)  # shown once

    undone = after(opened, undo(opened, last_batch(), next=where))
    assert 'Undone: 3 episodes marked as not watched.' in undone
    assert 'name="batch"' not in undone  # nothing left to undo
    assert Watch.objects.count() == 0


def test_without_htmx_up_to_here_comes_back_with_a_notice_too(opened):
    html = after(opened, up_to_here(opened, 6103, next=f'{SERIES_PAGE}?season=2'))

    assert 'Marked 5 episodes up to S2E3 as watched.' in html
    assert f'name="batch" value="{last_batch()}"' in html


# --- with htmx only the notice and the changed rows come back, so the page does not move ------


def test_with_htmx_a_season_answers_with_the_notice_and_just_the_rows_that_changed(opened):
    mark_one(opened, 6101)

    response = mark_season(opened, 2, **HTMX)

    body = response.content.decode()
    assert response.status_code == 200 and '<html' not in body
    assert 'Marked 1 episode in Season 2 as watched.' in body
    assert f'name="batch" value="{last_batch()}"' in body  # the Undo button
    # Only 6103 changed (6101 was marked already). Its row replaces the one on the page.
    assert body.count('<li') == 1
    assert f'<li id="episode-{eid(6103)}" hx-swap-oob="true">' in body
    assert is_watched(body, 3)
    assert watched(opened.user) == {6101, 6103}


def test_with_htmx_up_to_here_answers_with_every_row_that_changed(opened):
    body = up_to_here(opened, 6103, **HTMX).content.decode()

    assert 'Marked 5 episodes up to S2E3 as watched.' in body
    assert body.count('<li') == 5 and body.count('hx-swap-oob="true"') == 5
    assert body.count('class="check watched"') == 5


def test_with_htmx_nothing_new_answers_with_just_the_notice(opened):
    mark_season(opened, 1)

    body = mark_season(opened, 1, **HTMX).content.decode()

    assert 'Nothing new to mark in Season 1.' in body
    assert '<li' not in body and 'name="batch"' not in body


def test_with_htmx_a_refusal_answers_with_just_the_notice(opened):
    body = up_to_here(opened, 6104, **HTMX).content.decode()

    assert 'S2E4 has not aired yet' in body and '<li' not in body
    assert Watch.objects.count() == 0


def test_with_htmx_undo_answers_with_the_notice_and_the_rows_back_to_gray(opened):
    before = snapshot()
    mark_season(opened, 1)

    body = undo(opened, last_batch(), **HTMX).content.decode()

    assert 'Undone: 3 episodes marked as not watched.' in body
    assert body.count('<li') == 3 and body.count('hx-swap-oob="true"') == 3
    assert 'class="check watched"' not in body
    assert 'name="batch"' not in body  # nothing left to undo
    assert snapshot() == before


def test_with_htmx_undoing_twice_says_so_and_changes_nothing(opened):
    mark_season(opened, 1)
    batch = last_batch()
    undo(opened, batch, **HTMX)
    before = snapshot()

    body = undo(opened, batch, **HTMX).content.decode()

    assert 'Nothing to undo' in body and '<li' not in body
    assert snapshot() == before


# --- safety -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    'form',
    [
        {},
        {'tmdb_id': '1399'},
        {'season': '1'},
        {'tmdb_id': 'abc', 'season': '1'},
        {'tmdb_id': '1399', 'season': 'x'},
        {'tmdb_id': '0', 'season': '1'},
        {'tmdb_id': '1399', 'season': '-1'},
    ],
)
def test_a_season_button_with_nonsense_is_refused(opened, form):
    assert opened.post('/watched/season/add/', form).status_code == 400
    assert Watch.objects.count() == 0


def test_a_season_or_series_that_does_not_exist_is_not_found(opened):
    assert opened.post('/watched/season/add/', {'tmdb_id': 1399, 'season': 9}).status_code == 404
    assert opened.post('/watched/season/add/', {'tmdb_id': 5, 'season': 1}).status_code == 404
    assert Watch.objects.count() == 0


@pytest.mark.parametrize('form', [{}, {'episode_id': ''}, {'episode_id': 'abc'}])
def test_an_up_to_here_button_with_nonsense_is_refused(opened, form):
    assert opened.post('/watched/up-to/add/', form).status_code == 400
    assert Watch.objects.count() == 0


def test_an_up_to_here_for_an_episode_that_does_not_exist_is_not_found(opened):
    assert opened.post('/watched/up-to/add/', {'episode_id': 99999}).status_code == 404


@pytest.mark.parametrize('form', [{}, {'batch': ''}, {'batch': 'abc'}, {'batch': '1234'}])
def test_an_undo_with_nonsense_is_refused(opened, form):
    assert opened.post('/watched/batch/remove/', form).status_code == 400


ADDRESSES = ['/watched/season/add/', '/watched/up-to/add/', '/watched/batch/remove/']


@pytest.mark.parametrize('address', ADDRESSES)
def test_the_buttons_only_accept_posts(logged_in_client, address):
    assert logged_in_client.get(address).status_code == 405


@pytest.mark.parametrize('address', ADDRESSES)
@pytest.mark.django_db
def test_the_buttons_are_closed_when_logged_out(client, respx_mock, address):
    response = client.post(address, {'tmdb_id': 1399, 'season': 1})

    assert response.status_code == 302
    assert response['Location'].startswith('/login/')
    assert respx_mock.calls.call_count == 0


@pytest.mark.parametrize('address', ADDRESSES)
def test_the_buttons_need_the_csrf_token(db, tmdb_series, address):
    strict = make_client('strict-user', enforce_csrf_checks=True)
    page(strict)

    assert strict.post(address, {'tmdb_id': 1399, 'season': 1}).status_code == 403
    assert Watch.objects.count() == 0


@pytest.mark.parametrize('elsewhere', ['https://evil.example/', '//evil.example/', 'javascript:alert(1)'])
def test_a_button_never_sends_you_to_another_site(opened, elsewhere):
    pressed = opened.post('/watched/season/add/', {'tmdb_id': 1399, 'season': 1, 'next': elsewhere})
    assert pressed['Location'] == '/series/'
    up_to = opened.post('/watched/up-to/add/', {'episode_id': eid(6103), 'next': elsewhere})
    assert up_to['Location'] == '/series/'
    undone = opened.post('/watched/batch/remove/', {'batch': last_batch(), 'next': elsewhere})
    assert undone['Location'] == '/series/'


def test_the_tmdb_key_never_reaches_the_browser(opened):
    body = mark_season(opened, 1, **HTMX).content.decode()

    assert 'made-up-secret-key' not in body
