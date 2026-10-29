import datetime
import re

import httpx
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
    'seasons': [{'season_number': 0}, {'season_number': 1}, {'season_number': 2}],
}


def made_up_episode(season, number, tmdb_id, air_date, name=None, runtime=45):
    return {
        'id': tmdb_id,
        'season_number': season,
        'episode_number': number,
        'name': name or f'Made-up episode {season}x{number}',
        'air_date': air_date,
        'runtime': runtime,
    }


# The made-up episodes. "Today" below is the 28th in Lisbon and already the 29th in Auckland, so
# one episode has aired for everyone, one only for Auckland, and one has no date.
SEASONS = {
    0: [made_up_episode(0, 1, 6000, '2010-01-01', name='Made-up special')],
    1: [
        made_up_episode(1, 1, 6001, '2011-04-17', name='Made-up pilot', runtime=60),
        made_up_episode(1, 2, 6002, '2011-04-24'),
        made_up_episode(1, 3, 6003, '2026-10-28'),
    ],
    2: [
        made_up_episode(2, 1, 6101, '2026-10-29'),
        made_up_episode(2, 2, 6102, None),
    ],
}

# The fixed "now" for every test here: 8 pm UTC on 28 Oct 2026.
NOW = datetime.datetime(2026, 10, 28, 20, 0, tzinfo=datetime.UTC)


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


def page(client, url=SERIES_PAGE):
    return client.get(url).content.decode()


def after(client, response):
    """The page a button press sends the browser to (with its message)."""
    return client.get(response['Location']).content.decode()


def episode_of(tmdb_id):
    return Episode.objects.get(tmdb_id=tmdb_id)


def mark(client, tmdb_id, **extra):
    return client.post('/watched/episode/add/', {'episode_id': episode_of(tmdb_id).id, **extra})


def unmark(client, watch_id, **extra):
    return client.post('/watched/remove/', {'watch_id': watch_id, **extra})


def snapshot():
    """Everything saved about episodes, watches and the To Watch lists, to compare before and after."""
    return [list(model.objects.order_by('id').values()) for model in (Episode, Watch, ToWatchItem)]


def is_watched(html, number):
    """Whether the page shows episode `number` with the green button (it offers "not watched")."""
    return f'aria-label="Mark episode {number} as not watched"' in html


def can_mark(html, tmdb_id):
    """Whether the page has the gray button for this episode (found by the id its form sends)."""
    return f'name="episode_id" value="{episode_of(tmdb_id).id}"' in html


def without_tokens(html):
    """The page without the random CSRF tokens, so two loads of the same page can be compared."""
    return re.sub(r'name="csrfmiddlewaretoken" value="[^"]+"', '', html)


# --- saving the series and its episodes -------------------------------------------------------


def test_opening_a_series_saves_it_and_its_episodes(logged_in_client, tmdb_series):
    page(logged_in_client)

    series = Title.objects.get(kind='series', tmdb_id=1399)
    assert series.title == 'Made-up Series'
    assert series.episodes_refreshed_at == NOW
    assert Episode.objects.count() == 6
    pilot = episode_of(6001)
    assert (pilot.title, pilot.season_number, pilot.episode_number) == (series, 1, 1)
    assert pilot.name == 'Made-up pilot'
    assert pilot.air_date == datetime.date(2011, 4, 17)
    assert pilot.runtime == 60
    assert episode_of(6102).air_date is None
    assert all(tmdb_series[number].call_count == 1 for number in SEASONS)


def test_the_page_lists_the_seasons_in_order_with_the_specials_last(logged_in_client, tmdb_series):
    html = page(logged_in_client)

    assert html.index('Season 1') < html.index('Season 2') < html.index('Specials')
    assert 'Made-up pilot' in html and 'Made-up special' in html
    assert '3 episodes' in html and '1 episode<' in html  # the specials have one
    assert '17 Apr 2011' in html  # aired
    assert 'Airs 29 Oct 2026' in html  # tomorrow, in Lisbon
    assert 'No air date yet' in html


def test_the_first_season_is_open_and_a_season_in_the_address_is_opened_instead(logged_in_client, tmdb_series):
    first = page(logged_in_client)
    second = page(logged_in_client, SERIES_PAGE + '?season=2')
    nonsense = page(logged_in_client, SERIES_PAGE + '?season=abc')

    assert '<details id="season-1" open>' in first and '<details id="season-2">' in first
    assert '<details id="season-2" open>' in second and '<details id="season-1">' in second
    assert '<details id="season-1" open>' in nonsense


def test_the_page_still_has_the_to_watch_button_and_no_movie_form(logged_in_client, tmdb_series):
    html = page(logged_in_client)

    assert 'Add to To Watch' in html
    assert 'name="watched_on"' not in html


def test_a_series_with_no_episodes_says_so(logged_in_client, respx_mock):
    respx_mock.get(SERIES_URL).respond(json={**MADE_UP_SERIES, 'seasons': []})

    html = page(logged_in_client)

    assert 'TMDB has no episodes for this series yet.' in html
    assert Episode.objects.count() == 0


def test_a_season_tmdb_cannot_find_is_skipped_and_the_rest_are_kept(logged_in_client, tmdb_series):
    tmdb_series[2].respond(404, json={'status_message': 'The resource could not be found.'})

    html = page(logged_in_client)

    assert 'Season 1' in html and 'Season 2' not in html
    assert Episode.objects.count() == 4


def test_tmdb_values_that_make_no_sense_are_saved_as_empty(logged_in_client, tmdb_series):
    odd = made_up_episode(1, 4, 6004, 'not-a-date', runtime=0)
    tmdb_series[1].respond(json={'season_number': 1, 'episodes': [*SEASONS[1], odd, {**odd, 'id': 6005, 'air_date': ''}]})

    page(logged_in_client)

    assert (episode_of(6004).air_date, episode_of(6004).runtime) == (None, None)
    assert episode_of(6005).air_date is None


# --- refreshing -------------------------------------------------------------------------------


def test_opening_it_again_within_a_day_does_not_ask_tmdb_again(logged_in_client, tmdb_series, clock):
    page(logged_in_client)
    clock.shift(datetime.timedelta(hours=23))

    page(logged_in_client)
    assert tmdb_series[1].call_count == 1

    clock.shift(datetime.timedelta(hours=2))  # now over a day old
    page(logged_in_client)
    assert tmdb_series[1].call_count == 2


def test_the_status_is_saved_and_shown_next_to_the_year(logged_in_client, tmdb_series):
    html = page(logged_in_client)

    assert Title.objects.get().status == 'Returning Series'
    assert '2011 · Series · Returning Series' in html


def test_a_refresh_picks_up_that_the_series_has_ended(logged_in_client, tmdb_series, clock):
    page(logged_in_client)
    tmdb_series['series'].respond(json={**MADE_UP_SERIES, 'status': 'Ended'})
    clock.shift(datetime.timedelta(days=2))

    html = page(logged_in_client)

    assert Title.objects.get().status == 'Ended'
    assert '2011 · Series · Ended' in html


def test_a_series_whose_status_tmdb_does_not_give_has_none_saved_and_none_shown(logged_in_client, tmdb_series):
    tmdb_series['series'].respond(json={key: value for key, value in MADE_UP_SERIES.items() if key != 'status'})

    html = page(logged_in_client)

    assert Title.objects.get().status == ''
    assert '2011 · Series<' in html


def test_a_refresh_brings_in_a_new_episode(logged_in_client, tmdb_series, clock):
    page(logged_in_client)
    new = made_up_episode(1, 4, 6004, '2026-11-04', name='Made-up newcomer')
    tmdb_series[1].respond(json={'season_number': 1, 'episodes': [*SEASONS[1], new]})
    clock.shift(datetime.timedelta(days=2))

    html = page(logged_in_client)

    assert Episode.objects.count() == 7
    assert 'Made-up newcomer' in html and 'Airs 4 Nov 2026' in html


def test_a_renumbered_episode_keeps_its_watch_and_nothing_is_deleted(logged_in_client, tmdb_series, clock):
    page(logged_in_client)
    mark(logged_in_client, 6002, only_this=1)  # the first mark in a series asks about the earlier ones; not here
    watch = Watch.objects.get()
    # TMDB now calls that episode number 5 with another name, and has dropped episode 6003.
    renumbered = made_up_episode(1, 5, 6002, '2011-04-24', name='Made-up renamed episode')
    tmdb_series[1].respond(json={'season_number': 1, 'episodes': [SEASONS[1][0], renumbered]})
    clock.shift(datetime.timedelta(days=2))

    html = page(logged_in_client)

    assert Episode.objects.count() == 6  # no duplicate, and 6003 was not deleted
    watch.refresh_from_db()
    assert (watch.episode.tmdb_id, watch.episode.episode_number) == (6002, 5)
    assert 'Made-up renamed episode' in html
    assert is_watched(html, 5)


def test_tmdb_down_on_a_later_visit_shows_the_saved_episodes_with_a_note(logged_in_client, tmdb_series, clock):
    page(logged_in_client)
    saved_at = Title.objects.get().episodes_refreshed_at
    tmdb_series['series'].mock(side_effect=httpx.ConnectError('no network'))
    clock.shift(datetime.timedelta(days=2))

    html = page(logged_in_client)

    assert 'Could not reach TMDB' in html and 'Showing the episodes saved earlier.' in html
    assert 'Made-up pilot' in html
    assert Title.objects.get().episodes_refreshed_at == saved_at  # so the next visit tries again


def test_tmdb_failing_for_the_episodes_shows_the_series_and_a_message_then_recovers(
    logged_in_client, tmdb_series
):
    tmdb_series[1].mock(side_effect=httpx.ConnectError('no network'))

    html = page(logged_in_client)

    assert 'Made-up Series' in html and 'Could not reach TMDB' in html
    assert 'TMDB has no episodes' not in html
    assert Episode.objects.count() == 0  # nothing half saved
    assert Title.objects.get().episodes_refreshed_at is None

    tmdb_series[1].side_effect = None  # TMDB is back
    tmdb_series[1].respond(json={'season_number': 1, 'episodes': SEASONS[1]})
    assert 'Made-up pilot' in page(logged_in_client)
    assert Episode.objects.count() == 6


def test_a_series_never_opened_before_with_tmdb_down_shows_a_friendly_message(logged_in_client, respx_mock):
    respx_mock.get(SERIES_URL).mock(side_effect=httpx.ConnectError('no network'))

    response = logged_in_client.get(SERIES_PAGE)

    assert response.status_code == 200
    assert 'Could not reach TMDB' in response.content.decode()
    assert Title.objects.count() == 0


def test_a_series_tmdb_does_not_have_is_not_found(logged_in_client, respx_mock):
    respx_mock.get(SERIES_URL).respond(404, json={'status_message': 'The resource could not be found.'})

    assert logged_in_client.get(SERIES_PAGE).status_code == 404
    assert Title.objects.count() == 0


# --- marking one episode ----------------------------------------------------------------------


def test_marking_saves_one_watch_for_that_episode_on_the_day_it_was_pressed(logged_in_client, tmdb_series):
    page(logged_in_client)
    target = f'{SERIES_PAGE}?season=1#episode-{episode_of(6001).id}'

    response = mark(logged_in_client, 6001, next=target)

    watch = Watch.objects.get()
    assert (watch.user, watch.title.tmdb_id, watch.episode.tmdb_id) == (logged_in_client.user, 1399, 6001)
    assert watch.watched_on == datetime.date(2026, 10, 28)
    assert response['Location'] == target  # back to the same episode, in the same season
    html = after(logged_in_client, response)
    assert is_watched(html, 1)
    assert 'role="status"' not in html  # no message: the green button says it
    assert 'aria-label="Mark episode 2 as watched"' in html  # the others are still gray


def test_the_button_is_gray_until_the_episode_is_watched_then_green(logged_in_client, tmdb_series):
    before = page(logged_in_client)
    mark(logged_in_client, 6001)
    after_marking = page(logged_in_client)

    # Four episodes have aired for Lisbon (three in season 1, one special), so four buttons.
    assert before.count('class="check"') == 4 and 'class="check watched"' not in before
    assert after_marking.count('class="check"') == 3 and after_marking.count('class="check watched"') == 1


def test_an_episode_that_aired_today_can_be_marked(logged_in_client, tmdb_series):
    page(logged_in_client)

    mark(logged_in_client, 6003, only_this=1)

    assert Watch.objects.get().watched_on == datetime.date(2026, 10, 28)


def test_the_day_follows_the_accounts_time_zone(logged_in_client, tmdb_series):
    page(logged_in_client)
    auckland = make_client('auckland-user', 'Pacific/Auckland')

    refused = mark(logged_in_client, 6101)  # airs on the 29th: tomorrow in Lisbon...
    assert Watch.objects.count() == 0
    assert 'has not aired yet' in after(logged_in_client, refused)

    assert not can_mark(page(logged_in_client), 6101)  # no button for it in Lisbon...
    assert can_mark(page(auckland), 6101)  # ...but there is one in Auckland

    mark(auckland, 6101, only_this=1)
    assert Watch.objects.get().watched_on == datetime.date(2026, 10, 29)


def test_an_episode_that_has_not_aired_has_no_button_and_cannot_be_marked(logged_in_client, tmdb_series):
    html = page(logged_in_client)
    assert not can_mark(html, 6101) and not can_mark(html, 6102)  # neither has a button
    assert can_mark(html, 6003)  # while one that aired today does

    mark(logged_in_client, 6101)
    response = mark(logged_in_client, 6102)

    assert Watch.objects.count() == 0
    assert 'no air date yet' in after(logged_in_client, response)


def test_marking_an_episode_that_is_already_marked_changes_nothing(logged_in_client, tmdb_series):
    page(logged_in_client)
    mark(logged_in_client, 6001)
    before = snapshot()

    response = mark(logged_in_client, 6001)

    assert snapshot() == before
    assert 'already marked as watched' in after(logged_in_client, response)


def test_marking_an_episode_moves_the_series_from_to_watch_to_watching_without_touching_the_list(
    logged_in_client, tmdb_series
):
    page(logged_in_client)
    ToWatchItem.objects.create(user=logged_in_client.user, title=Title.objects.get())
    assert 'href="/series/1399/"' in page(logged_in_client, '/series/')

    mark(logged_in_client, 6001)

    # Its entry on the list is untouched: the tabs are worked out, so un-marking brings it back.
    assert ToWatchItem.objects.get().removed_at is None
    assert 'href="/series/1399/"' not in page(logged_in_client, '/series/')
    assert 'href="/series/1399/"' in page(logged_in_client, '/series/watching/')


def test_marking_an_episode_does_not_show_in_history(logged_in_client, tmdb_series):
    page(logged_in_client)
    mark(logged_in_client, 6001)

    assert 'class="tile"' not in page(logged_in_client, '/movies/history/')


# --- undo -------------------------------------------------------------------------------------


def test_undo_puts_everything_back_as_it_was(logged_in_client, tmdb_series):
    page(logged_in_client)
    ToWatchItem.objects.create(user=logged_in_client.user, title=Title.objects.get())
    before = snapshot()
    gray_page = page(logged_in_client)

    mark(logged_in_client, 6001)
    assert snapshot() != before and is_watched(page(logged_in_client), 1)
    watch = Watch.objects.get()
    response = unmark(logged_in_client, watch.id, next=f'{SERIES_PAGE}?season=1#episode-{watch.episode_id}')

    assert snapshot() == before
    assert response['Location'] == f'{SERIES_PAGE}?season=1#episode-{watch.episode_id}'
    html = after(logged_in_client, response)
    assert 'role="status"' not in html
    assert without_tokens(page(logged_in_client)) == without_tokens(gray_page)  # the page is what it was
    assert 'aria-label="Mark episode 1 as watched"' in html


def test_an_episode_can_be_marked_again_after_an_undo(logged_in_client, tmdb_series):
    page(logged_in_client)
    mark(logged_in_client, 6001)
    unmark(logged_in_client, Watch.objects.get().id)

    mark(logged_in_client, 6001)

    assert Watch.objects.count() == 1


def test_un_marking_works_any_time_later(logged_in_client, tmdb_series, clock):
    page(logged_in_client)
    mark(logged_in_client, 6001)
    clock.shift(datetime.timedelta(days=10))  # long after marking (a login lasts 2 weeks)

    unmark(logged_in_client, Watch.objects.get().id)

    assert Watch.objects.count() == 0


def test_each_account_has_its_own_marks(logged_in_client, tmdb_series):
    page(logged_in_client)
    mark(logged_in_client, 6001)
    other = make_client('second-user')

    assert is_watched(page(logged_in_client), 1)
    assert not is_watched(page(other), 1)

    # And the second account cannot un-mark the first account's watch.
    before = snapshot()
    response = unmark(other, Watch.objects.get().id)
    assert snapshot() == before
    assert 'not in your history' in after(other, response)


# --- safety -----------------------------------------------------------------------------------


@pytest.mark.parametrize('form', [{}, {'episode_id': ''}, {'episode_id': 'abc'}])
def test_a_button_with_nonsense_is_refused(logged_in_client, tmdb_series, form):
    assert logged_in_client.post('/watched/episode/add/', form).status_code == 400
    assert Watch.objects.count() == 0


def test_an_episode_that_does_not_exist_is_not_found(logged_in_client):
    assert logged_in_client.post('/watched/episode/add/', {'episode_id': 99999}).status_code == 404
    assert Watch.objects.count() == 0


def test_the_mark_button_only_accepts_posts(logged_in_client):
    assert logged_in_client.get('/watched/episode/add/').status_code == 405


@pytest.mark.django_db
def test_marking_is_closed_when_logged_out(client, respx_mock):
    response = client.post('/watched/episode/add/', {'episode_id': 1})

    assert response.status_code == 302
    assert response['Location'].startswith('/login/')
    assert respx_mock.calls.call_count == 0


def test_the_mark_button_needs_the_csrf_token(db, tmdb_series):
    strict = make_client('strict-user', enforce_csrf_checks=True)
    page(strict)

    assert strict.post('/watched/episode/add/', {'episode_id': episode_of(6001).id}).status_code == 403
    assert Watch.objects.count() == 0


@pytest.mark.parametrize('elsewhere', ['https://evil.example/', '//evil.example/', 'javascript:alert(1)'])
def test_a_button_never_sends_you_to_another_site(logged_in_client, tmdb_series, elsewhere):
    page(logged_in_client)

    assert mark(logged_in_client, 6001, next=elsewhere)['Location'] == '/series/'


def test_the_tmdb_key_never_reaches_the_browser(logged_in_client, tmdb_series):
    response = logged_in_client.get(SERIES_PAGE)

    assert 'made-up-secret-key' not in response.content.decode()
    assert 'made-up-secret-key' not in str(response.headers)


# --- with htmx only the episode's row changes, so the page does not move ----------------------

HTMX = {'headers': {'HX-Request': 'true'}}


def test_the_buttons_use_htmx_so_the_page_does_not_reload(logged_in_client, tmdb_series):
    gray = page(logged_in_client)
    mark(logged_in_client, 6001)
    green = page(logged_in_client)

    assert 'hx-post="/watched/episode/add/" hx-target="closest li" hx-swap="outerHTML"' in gray
    assert 'hx-post="/watched/remove/" hx-target="closest li" hx-swap="outerHTML"' in green


def test_with_htmx_marking_and_un_marking_answer_with_just_the_row(logged_in_client, tmdb_series):
    page(logged_in_client)
    episode = episode_of(6001)

    marked = logged_in_client.post('/watched/episode/add/', {'episode_id': episode.id}, **HTMX)

    body = marked.content.decode()
    assert marked.status_code == 200 and '<html' not in body  # a piece of a page, not a page
    assert body.lstrip().startswith(f'<li id="episode-{episode.id}">') and body.count('<li') == 1
    assert is_watched(body, 1)
    assert Watch.objects.count() == 1

    watch = Watch.objects.get()
    unmarked = logged_in_client.post(
        '/watched/remove/', {'watch_id': watch.id, 'episode_id': episode.id}, **HTMX
    )

    body = unmarked.content.decode()
    assert unmarked.status_code == 200 and '<html' not in body
    assert 'aria-label="Mark episode 1 as watched"' in body and not is_watched(body, 1)
    assert Watch.objects.count() == 0


def test_with_htmx_undo_puts_everything_back_as_it_was(logged_in_client, tmdb_series):
    page(logged_in_client)
    before = snapshot()
    episode = episode_of(6001)

    logged_in_client.post('/watched/episode/add/', {'episode_id': episode.id}, **HTMX)
    assert snapshot() != before
    logged_in_client.post('/watched/remove/', {'watch_id': Watch.objects.get().id, 'episode_id': episode.id}, **HTMX)

    assert snapshot() == before


def test_with_htmx_an_episode_that_has_not_aired_comes_back_without_a_button(logged_in_client, tmdb_series):
    page(logged_in_client)

    response = logged_in_client.post('/watched/episode/add/', {'episode_id': episode_of(6101).id}, **HTMX)

    body = response.content.decode()
    assert response.status_code == 200 and 'Airs 29 Oct 2026' in body and 'class="check' not in body
    assert Watch.objects.count() == 0


def test_with_htmx_marking_an_episode_twice_shows_it_green_and_saves_one_watch(logged_in_client, tmdb_series):
    page(logged_in_client)
    episode = episode_of(6001)
    logged_in_client.post('/watched/episode/add/', {'episode_id': episode.id}, **HTMX)

    response = logged_in_client.post('/watched/episode/add/', {'episode_id': episode.id}, **HTMX)

    assert is_watched(response.content.decode(), 1)
    assert Watch.objects.count() == 1


def test_with_htmx_a_page_that_is_out_of_date_shows_the_row_as_it_is_now(logged_in_client, tmdb_series):
    page(logged_in_client)
    episode = episode_of(6001)
    mark(logged_in_client, 6001)
    watch_id = Watch.objects.get().id
    unmark(logged_in_client, watch_id)  # undone in another tab; this page still shows green

    response = logged_in_client.post('/watched/remove/', {'watch_id': watch_id, 'episode_id': episode.id}, **HTMX)

    assert response.status_code == 200
    assert 'aria-label="Mark episode 1 as watched"' in response.content.decode()
    assert Watch.objects.count() == 0


def test_with_htmx_each_account_sees_only_its_own_marks(logged_in_client, tmdb_series):
    page(logged_in_client)
    mark(logged_in_client, 6001)
    other = make_client('second-user')
    episode = episode_of(6001)

    # The second account presses "not watched" with the first account's watch id: nothing is removed
    # and the row it gets back is gray, because it has not marked that episode itself.
    response = other.post('/watched/remove/', {'watch_id': Watch.objects.get().id, 'episode_id': episode.id}, **HTMX)

    assert not is_watched(response.content.decode(), 1)
    assert Watch.objects.count() == 1
