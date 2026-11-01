"""Marking a whole season (and un-marking it by pressing its button again), and the question asked when marking
an episode skips episodes that are not marked ("did you watch everything before it?")."""

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


def mark_one(client, tmdb_id, **options):
    """Press one episode's circle and say "No, only this one" if asked, so it is just a single mark."""
    return client.post('/watched/episode/add/', {'episode_id': eid(tmdb_id), 'only_this': 1}, **options)


def unmark_one(client, tmdb_id, **options):
    watch = Watch.objects.get(user=client.user, episode__tmdb_id=tmdb_id)
    return client.post('/watched/remove/', {'watch_id': watch.id, 'episode_id': watch.episode_id}, **options)


def press_circle(client, tmdb_id, next=SERIES_PAGE, **options):
    """Press an episode's gray circle, as the page does (no "only this one": that is the question's answer)."""
    return client.post('/watched/episode/add/', {'episode_id': eid(tmdb_id), 'next': next}, **options)


def mark_season(client, number, next=SERIES_PAGE, **options):
    """Press "Mark Season N as watched". The buttons on the page always send the page to come back to as `next`."""
    return client.post('/watched/season/add/', {'tmdb_id': 1399, 'season': number, 'next': next}, **options)


def unmark_season(client, number, next=SERIES_PAGE, **options):
    """Press the same button once the season is marked, when it says "as not watched"."""
    return client.post('/watched/season/remove/', {'tmdb_id': 1399, 'season': number, 'next': next}, **options)


def up_to_here(client, tmdb_id, next=SERIES_PAGE, **options):
    """The question's "Yes": mark the episode and the ones it skips (back to the nearest marked one before it)."""
    return client.post('/watched/up-to/add/', {'episode_id': eid(tmdb_id), 'next': next}, **options)


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


def season_button(html, number):
    """The season's form (on the page, or in the answer htmx puts in place of it)."""
    return re.search(rf'<form id="season-action-{number}".*?</form>', html, re.DOTALL).group(0)


def question(html):
    """The pop-up question on the page, or an empty string when there is none."""
    return re.search(r'<div id="ask">(.*?)</div>', html, re.DOTALL).group(1).strip()


def changed_rows(body):
    """The ids of the episode rows an answer puts in place of the ones on the page."""
    return re.findall(r'<li id="episode-(\d+)" hx-swap-oob="true">', body)


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


def test_a_season_skips_episodes_that_have_not_aired_or_have_no_date(opened):
    mark_season(opened, 2)

    assert watched(opened.user) == {6101, 6103}  # not 6102 (no date) and not 6104 (airs tomorrow)


def test_a_season_leaves_episodes_already_marked_alone(opened, clock):
    mark_one(opened, 6002)
    earlier = Watch.objects.get()
    clock.shift(datetime.timedelta(days=1))  # the season is pressed on another day

    mark_season(opened, 1)

    earlier.refresh_from_db()
    assert earlier.watched_on == TODAY  # the same watch, the same date
    assert watched(opened.user) == {6001, 6002, 6003}
    assert Watch.objects.count() == 3  # no second watch for 6002


def test_a_season_with_nothing_new_changes_nothing_and_says_nothing(opened):
    mark_season(opened, 1)
    before = snapshot()

    response = mark_season(opened, 1)

    assert snapshot() == before
    html = after(opened, response)
    assert 'Nothing new' not in html and 'role="status"' not in html


def test_a_season_none_of_whose_episodes_has_aired_marks_nothing(opened):
    before = snapshot()

    mark_season(opened, 3)

    assert snapshot() == before


def test_the_specials_are_marked_as_a_season_of_their_own(opened):
    mark_season(opened, 1)
    assert 6000 not in watched(opened.user)  # a regular season leaves the specials alone

    mark_season(opened, 0)

    assert watched(opened.user) == {6000, 6001, 6002, 6003}


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


# --- pressing the season button again marks the whole season as not watched --------------------


def test_pressing_the_season_button_again_puts_everything_back_as_it_was(opened):
    ToWatchItem.objects.create(user=opened.user, title=Title.objects.get())
    before = snapshot()
    gray_page = page(opened)

    mark_season(opened, 1)
    assert snapshot() != before and is_watched(page(opened), 3)
    unmark_season(opened, 1)

    assert snapshot() == before
    assert without_tokens(page(opened)) == without_tokens(gray_page)  # the page is what it was


def test_un_marking_a_season_leaves_the_other_seasons_alone(opened):
    mark_season(opened, 1)
    mark_season(opened, 2)

    unmark_season(opened, 1)

    assert watched(opened.user) == {6101, 6103}


def test_un_marking_a_season_takes_back_what_was_marked_one_by_one_too(opened):
    mark_one(opened, 6001)
    mark_one(opened, 6003)
    mark_one(opened, 6101)

    unmark_season(opened, 1)

    assert watched(opened.user) == {6101}


def test_un_marking_a_season_with_nothing_marked_changes_nothing_and_says_nothing(opened):
    mark_one(opened, 6101)
    before = snapshot()

    html = after(opened, unmark_season(opened, 1))

    assert snapshot() == before
    assert 'role="status"' not in html


def test_a_season_can_be_marked_again_after_it_was_un_marked(opened):
    mark_season(opened, 1)
    unmark_season(opened, 1)

    mark_season(opened, 1)

    assert watched(opened.user) == {6001, 6002, 6003}


def test_un_marking_a_season_works_any_time_later(opened, clock):
    mark_season(opened, 1)
    clock.shift(datetime.timedelta(days=10))  # long after marking (a login lasts 2 weeks)

    unmark_season(opened, 1)

    assert Watch.objects.count() == 0


def test_each_account_has_its_own_marks_and_its_own_un_marking(opened):
    other = make_client('second-user')
    mark_season(opened, 1)
    mark_season(other, 1)

    unmark_season(other, 1)

    assert watched(opened.user) == {6001, 6002, 6003} and watched(other.user) == set()
    assert is_watched(page(opened), 1) and not is_watched(page(other), 1)


# --- episodes renumbered or added after a season was marked -----------------------------------


def test_after_tmdb_renumbers_the_season_the_marks_stay_and_the_button_follows(opened, tmdb_series, clock):
    mark_season(opened, 1)
    assert 'as not watched' in season_button(page(opened), 1)
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
    # So the season is not complete any more: its button offers to mark it again, which marks only the newcomer.
    assert 'as watched' in season_button(html, 1)
    mark_season(opened, 1)
    assert watched(opened.user) == {6001, 6002, 6003, 6004}
    assert 'as not watched' in season_button(page(opened), 1)


# --- the page ---------------------------------------------------------------------------------


def test_the_page_offers_a_season_button_where_something_has_aired(opened):
    html = page(opened)

    for number in (0, 1, 2):
        assert f'Mark {"Specials" if number == 0 else f"Season {number}"} as watched' in html
    assert 'season-action' not in season_block(html, 3)  # season 3 has not started: nothing to mark


def test_the_button_says_not_watched_once_every_episode_that_has_aired_is_marked(opened):
    mark_one(opened, 6101)
    assert 'Mark Season 2 as watched' in season_button(page(opened), 2)  # 6103 has aired and is not marked

    mark_season(opened, 2)
    button = season_button(page(opened), 2)

    # Not marked: 6102 (no date) and 6104 (airs tomorrow), and that does not matter.
    assert 'Mark Season 2 as not watched' in button and 'action="/watched/season/remove/"' in button
    assert 'Mark Season 1 as watched' in season_button(page(opened), 1)  # the other seasons are as they were


def test_ticking_the_last_episode_by_hand_flips_the_button_and_un_ticking_one_flips_it_back(opened):
    mark_one(opened, 6001)
    mark_one(opened, 6002)
    assert 'as watched' in season_button(page(opened), 1)

    mark_one(opened, 6003)
    assert 'as not watched' in season_button(page(opened), 1)

    unmark_one(opened, 6002)
    assert 'as watched' in season_button(page(opened), 1)


def test_the_specials_button_flips_too(opened):
    mark_season(opened, 0)

    assert 'Mark Specials as not watched' in season_button(page(opened), 0)


def test_there_is_no_up_to_here_button_and_no_notice_or_undo_button(opened):
    mark_season(opened, 1)
    html = page(opened)

    assert 'Up to here' not in html and 'up-to' not in html.replace('/watched/up-to/add/', '')
    assert 'Undo' not in html and 'bulk-notice' not in html and 'name="batch"' not in html
    for tmdb_id in (6001, 6002, 6003):  # aired and marked: the circle and the "−" that takes a watch back
        assert row(html, tmdb_id).count('<button') == 2
    for tmdb_id in (6101, 6103):  # aired and not marked: the circle is the only button of the row
        assert row(html, tmdb_id).count('<button') == 1
    assert row(html, 6102).count('<button') == 0  # no air date: no button


def test_the_buttons_use_htmx_so_the_page_does_not_reload(opened):
    html = page(opened)

    assert 'hx-post="/watched/season/add/" hx-swap="none"' in html
    assert '<div id="ask"></div>' in html


# --- without htmx the page just comes back ----------------------------------------------------


def test_without_htmx_a_season_press_comes_back_to_the_season_with_no_message(opened):
    where = f'{SERIES_PAGE}?season=1#season-1'

    response = mark_season(opened, 1, next=where)

    assert response.status_code == 302 and response['Location'] == where
    html = after(opened, response)
    assert is_watched(html, 3) and 'role="status"' not in html
    assert 'as not watched' in season_button(html, 1)


def test_without_htmx_pressing_it_again_un_marks_the_season_and_comes_back_the_same_way(opened):
    where = f'{SERIES_PAGE}?season=1#season-1'
    mark_season(opened, 1)

    response = unmark_season(opened, 1, next=where)

    assert response.status_code == 302 and response['Location'] == where
    html = after(opened, response)
    assert not is_watched(html, 1) and 'as watched' in season_button(html, 1)
    assert Watch.objects.count() == 0


# --- with htmx only the changed rows and season buttons come back, so the page does not move ----


def test_with_htmx_a_season_answers_with_just_the_rows_that_changed_and_its_button(opened):
    mark_one(opened, 6101)

    response = mark_season(opened, 2, **HTMX)

    body = response.content.decode()
    assert response.status_code == 200 and '<html' not in body
    # Only 6103 changed (6101 was marked already). Its row replaces the one on the page...
    assert body.count('<li') == 1 and changed_rows(body) == [str(eid(6103))]
    assert is_watched(body, 3)
    # ...and so does the season's button, which now says the season is marked.
    assert 'hx-swap-oob="true"' in season_button(body, 2) and 'Mark Season 2 as not watched' in body
    assert '<div id="ask" hx-swap-oob="true"></div>' in body
    assert 'Marked' not in body and 'Undo' not in body and watched(opened.user) == {6101, 6103}


def test_with_htmx_pressing_it_again_answers_with_the_rows_back_to_gray_and_the_button_back(opened):
    before = snapshot()
    mark_season(opened, 1)

    body = unmark_season(opened, 1, **HTMX).content.decode()

    assert len(changed_rows(body)) == 3 and body.count('<li') == 3
    assert 'class="check watched"' not in body
    assert 'Mark Season 1 as watched' in season_button(body, 1)
    assert snapshot() == before


def test_with_htmx_nothing_new_answers_with_no_rows(opened):
    mark_season(opened, 1)

    body = mark_season(opened, 1, **HTMX).content.decode()

    assert '<li' not in body and 'Nothing new' not in body


def test_with_htmx_the_circle_that_completes_a_season_also_flips_its_button(opened):
    mark_one(opened, 6001)
    mark_one(opened, 6002)

    body = press_circle(opened, 6003, **HTMX).content.decode()

    # The row is the main answer (htmx swaps it in place of the row the circle is in)...
    assert body.lstrip().startswith('<li id="episode-') and changed_rows(body) == []
    assert is_watched(body, 3)
    # ...and the season's button comes with it, to be put in place of the one on the page.
    assert 'hx-swap-oob="true"' in season_button(body, 1) and 'as not watched' in season_button(body, 1)


def test_with_htmx_un_marking_one_episode_of_a_marked_season_flips_the_button_back(opened):
    mark_season(opened, 1)

    body = unmark_one(opened, 6002, **HTMX).content.decode()

    assert 'class="check"' in body and 'class="check watched"' not in body
    assert 'Mark Season 1 as watched' in season_button(body, 1)


def test_with_htmx_a_circle_in_a_season_without_a_button_comes_back_as_just_the_row(opened):
    body = press_circle(opened, 6201, **HTMX).content.decode()  # airs in 2999: no circle, no season button

    assert 'season-action' not in body and Watch.objects.count() == 0


# --- "Yes", the question's way of marking an episode and the ones it skips ----------------------


def test_yes_marks_every_aired_episode_before_it_across_seasons(opened):
    up_to_here(opened, 6103)

    # All of season 1, then season 2 up to the chosen one. Not the episode without a date (6102), not the one
    # after (6104) and not the special.
    assert watched(opened.user) == {6001, 6002, 6003, 6101, 6103}
    assert {watch.watched_on for watch in Watch.objects.all()} == {TODAY}


def test_yes_in_the_first_season_marks_only_what_is_before_it(opened):
    up_to_here(opened, 6002)

    assert watched(opened.user) == {6001, 6002}


def test_yes_leaves_episodes_already_marked_alone(opened):
    mark_one(opened, 6001)
    earlier = Watch.objects.get()

    up_to_here(opened, 6003)

    earlier.refresh_from_db()
    assert earlier.watched_on == TODAY
    assert watched(opened.user) == {6001, 6002, 6003}
    assert Watch.objects.count() == 3


def test_yes_marks_only_what_is_between_the_nearest_marked_episode_and_this_one(opened):
    mark_one(opened, 6003)  # episodes 1 and 2 before it were skipped, and stay that way

    up_to_here(opened, 6103)

    assert watched(opened.user) == {6003, 6101, 6103}  # not 6001 and 6002, not 6102 (no date)


def test_yes_when_everything_before_it_is_marked_changes_nothing_and_says_nothing(opened):
    up_to_here(opened, 6003)
    before = snapshot()

    html = after(opened, up_to_here(opened, 6003))

    assert snapshot() == before and 'role="status"' not in html


def test_yes_on_an_episode_that_is_marked_still_marks_the_ones_before_it(opened):
    mark_one(opened, 6003)

    up_to_here(opened, 6003)

    assert watched(opened.user) == {6001, 6002, 6003}


@pytest.mark.parametrize(
    ('tmdb_id', 'reason'), [(6104, 'S2E4 has not aired yet'), (6102, 'S2E2 has no air date yet')]
)
def test_yes_on_an_episode_that_has_not_aired_is_refused(opened, tmdb_id, reason):
    html = after(opened, up_to_here(opened, tmdb_id))

    assert reason in html
    assert Watch.objects.count() == 0


def test_yes_is_not_for_a_special(opened):
    assert up_to_here(opened, 6000).status_code == 400
    assert Watch.objects.count() == 0


def test_yes_follows_the_numbers_as_they_are_now(opened, tmdb_series, clock):
    renumbered = [made_up_episode(1, 4, 6001, '2011-04-17'), *SEASONS[1][1:]]  # the pilot is now the last one
    tmdb_series[1].respond(json={'season_number': 1, 'episodes': renumbered})
    clock.shift(datetime.timedelta(days=2))
    page(opened)

    up_to_here(opened, 6003)  # now episode 3: the pilot, numbered 4, is after it

    assert watched(opened.user) == {6002, 6003}


def test_with_htmx_yes_answers_with_every_row_that_changed_and_the_seasons_buttons(opened):
    body = up_to_here(opened, 6103, **HTMX).content.decode()

    assert body.count('<li') == 5 and len(changed_rows(body)) == 5
    assert body.count('class="check watched"') == 5
    # Season 1 and season 2 are marked in full now (what has aired), so both buttons say so.
    assert 'as not watched' in season_button(body, 1) and 'as not watched' in season_button(body, 2)
    assert 'Marked' not in body and 'Undo' not in body


def test_with_htmx_a_refusal_answers_with_no_rows(opened):
    body = up_to_here(opened, 6104, **HTMX).content.decode()

    assert '<li' not in body and Watch.objects.count() == 0


# --- the question when marking an episode skips episodes that are not marked ------------------


def test_the_first_episode_marked_in_a_series_asks_about_the_earlier_ones_and_saves_nothing_yet(opened):
    where = f'{SERIES_PAGE}?season=1#episode-{eid(6003)}'

    response = press_circle(opened, 6003, next=where)

    assert response.status_code == 302 and response['Location'] == where
    ask = question(after(opened, response))
    assert '<dialog open' in ask and 'Did you watch the earlier episodes too?' in ask
    assert 'Nothing before S1E3 is marked in Made-up Series.' in ask
    assert 'from the beginning (S1E1)' in ask
    assert 'Yes, mark all 3' in ask and 'No, only S1E3' in ask
    assert '<form method="dialog">' in ask and 'Cancel' in ask  # closes the pop-up and nothing else
    assert Watch.objects.count() == 0
    assert question(page(opened)) == ''  # it is asked once, not again on the next visit


def test_the_question_counts_the_episodes_across_seasons_that_have_aired(opened):
    ask = question(after(opened, press_circle(opened, 6103)))

    # Season 1 (3), the first of season 2, and this one. Not the episode without a date.
    assert 'Nothing before S2E3 is marked' in ask and 'Yes, mark all 5' in ask


def test_the_question_follows_the_accounts_own_day(opened):
    auckland = make_client('auckland-user', 'Pacific/Auckland')
    page(auckland)

    ask = question(after(auckland, press_circle(auckland, 6104)))  # it aired on the 29th: today in Auckland

    assert 'Yes, mark all 6' in ask


def test_yes_marks_everything_from_the_beginning_and_the_season_button_takes_it_back(opened):
    before = snapshot()
    ask = question(after(opened, press_circle(opened, 6003)))
    assert 'action="/watched/up-to/add/"' in ask and f'name="episode_id" value="{eid(6003)}"' in ask

    html = after(opened, up_to_here(opened, 6003))

    assert watched(opened.user) == {6001, 6002, 6003}
    assert 'role="status"' not in html and 'Undo' not in html  # no notice: the season button is the way back
    assert 'as not watched' in season_button(html, 1)
    unmark_season(opened, 1)
    assert snapshot() == before


def test_no_marks_only_that_episode_and_it_can_be_undone(opened):
    before = snapshot()
    ask = question(after(opened, press_circle(opened, 6003)))
    assert 'action="/watched/episode/add/"' in ask and 'name="only_this" value="1"' in ask

    opened.post('/watched/episode/add/', {'episode_id': eid(6003), 'only_this': 1, 'next': SERIES_PAGE})

    watch = Watch.objects.get()
    assert (watch.episode.tmdb_id, watch.watched_on) == (6003, TODAY)
    unmark_one(opened, 6003)
    assert snapshot() == before


def test_the_very_first_episode_has_nothing_before_it_so_it_is_marked_without_asking(opened):
    html = after(opened, press_circle(opened, 6001))

    assert question(html) == '' and watched(opened.user) == {6001}


def test_the_episode_right_after_a_marked_one_is_marked_without_asking(opened):
    mark_one(opened, 6001)

    html = after(opened, press_circle(opened, 6002))

    assert question(html) == '' and watched(opened.user) == {6001, 6002}


def test_the_first_episode_of_the_next_season_after_a_marked_one_is_marked_without_asking(opened):
    mark_one(opened, 6003)

    html = after(opened, press_circle(opened, 6101))

    assert question(html) == '' and watched(opened.user) == {6003, 6101}


def test_an_episode_that_skips_one_asks_about_it_and_saves_nothing_yet(opened):
    mark_one(opened, 6001)

    ask = question(after(opened, press_circle(opened, 6003)))  # 6002 is skipped

    assert 'S1E3 comes after S1E1, the last episode you marked before it in Made-up Series.' in ask
    assert 'Did you watch everything from S1E2 up to it?' in ask
    assert 'Yes, mark all 2' in ask and 'No, only S1E3' in ask and 'Cancel' in ask
    assert watched(opened.user) == {6001}


def test_the_question_looks_across_seasons_and_leaves_out_episodes_that_cannot_be_marked(opened):
    mark_season(opened, 1)

    ask = question(after(opened, press_circle(opened, 6103)))  # S2E1 skipped; S2E2 has no date

    assert 'S2E3 comes after S1E3' in ask and 'from S2E1' in ask and 'Yes, mark all 2' in ask


def test_it_asks_about_the_episodes_before_it_when_only_later_ones_are_marked(opened):
    mark_one(opened, 6101)
    mark_one(opened, 6103)  # a series that is well under way, with the first season skipped

    ask = question(after(opened, press_circle(opened, 6003)))

    assert 'Nothing before S1E3 is marked' in ask and 'Yes, mark all 3' in ask
    up_to_here(opened, 6003)
    assert watched(opened.user) == {6001, 6002, 6003, 6101, 6103}


def test_yes_after_a_skip_marks_the_skipped_ones_and_each_can_be_taken_back_one_by_one(opened):
    mark_one(opened, 6001)
    before = snapshot()

    up_to_here(opened, 6003)

    assert watched(opened.user) == {6001, 6002, 6003}
    unmark_one(opened, 6003)
    unmark_one(opened, 6002)
    assert snapshot() == before


def test_no_after_a_skip_marks_only_that_episode_and_it_is_not_asked_about_again(opened):
    mark_one(opened, 6001)

    opened.post('/watched/episode/add/', {'episode_id': eid(6003), 'only_this': 1, 'next': SERIES_PAGE})
    html = after(opened, press_circle(opened, 6101))  # 6002 was skipped on purpose, and is before the last marked one

    assert watched(opened.user) == {6001, 6003, 6101} and question(html) == ''


def test_a_missing_episode_between_two_marked_ones_is_marked_without_asking(opened):
    mark_one(opened, 6001)
    mark_one(opened, 6003)

    html = after(opened, press_circle(opened, 6002))

    assert question(html) == '' and watched(opened.user) == {6001, 6002, 6003}


def test_cancel_after_a_skip_changes_nothing(opened):
    mark_one(opened, 6001)
    before = snapshot()

    press_circle(opened, 6003)  # the pop-up's Cancel is a plain close: nothing is sent to the server

    assert snapshot() == before


def test_a_special_is_marked_without_asking(opened):
    html = after(opened, press_circle(opened, 6000))

    assert question(html) == '' and watched(opened.user) == {6000}


def test_a_marked_special_does_not_count_as_having_started_the_series(opened):
    mark_one(opened, 6000)

    ask = question(after(opened, press_circle(opened, 6002)))

    assert 'Yes, mark all 2' in ask and watched(opened.user) == {6000}


@pytest.mark.parametrize('tmdb_id', [6104, 6102])  # airs tomorrow, has no date
def test_an_episode_that_cannot_be_marked_is_refused_without_asking(opened, tmdb_id):
    html = after(opened, press_circle(opened, tmdb_id))

    assert question(html) == '' and Watch.objects.count() == 0
    assert 'cannot be marked' in html


def test_an_episode_already_marked_is_not_asked_about(opened):
    mark_one(opened, 6003)  # on its own: the episodes before it are not marked

    html = after(opened, press_circle(opened, 6003))

    # Pressing the green circle again is a rewatch: one more watch, and no question.
    assert question(html) == '' and Watch.objects.filter(episode__tmdb_id=6003).count() == 2
    assert watched(opened.user) == {6003}


def test_after_everything_is_un_marked_the_next_first_mark_asks_again(opened):
    up_to_here(opened, 6003)
    unmark_season(opened, 1)

    assert 'Yes, mark all 3' in question(after(opened, press_circle(opened, 6003)))


def test_another_accounts_marks_do_not_count(opened):
    other = make_client('other-user')
    mark_one(other, 6001)

    assert 'Yes, mark all 3' in question(after(opened, press_circle(opened, 6003)))


def test_a_page_that_is_out_of_date_does_not_show_the_question(opened):
    press_circle(opened, 6003)
    mark_one(opened, 6001)
    mark_one(opened, 6002)  # in another tab, say: the episodes it asks about have been marked since

    assert question(page(opened)) == ''


def test_with_htmx_the_question_is_the_whole_answer_and_goes_into_the_page(opened):
    response = press_circle(opened, 6003, **HTMX)

    body = response.content.decode()
    assert response.status_code == 200 and '<html' not in body
    assert response['HX-Retarget'] == '#ask' and response['HX-Reswap'] == 'innerHTML'
    assert '<dialog open' in body and 'Yes, mark all 3' in body
    assert 'hx-post="/watched/up-to/add/" hx-swap="none"' in body
    assert '<li' not in body and Watch.objects.count() == 0


def test_with_htmx_a_skip_answers_with_the_question_and_saves_nothing_yet(opened):
    mark_one(opened, 6001)

    body = press_circle(opened, 6003, **HTMX).content.decode()

    assert '<dialog open' in body and 'S1E3 comes after S1E1' in body and 'Yes, mark all 2' in body
    assert '<li' not in body and watched(opened.user) == {6001}


def test_with_htmx_no_answers_with_the_row_the_seasons_button_and_takes_the_question_off(opened):
    response = opened.post(
        '/watched/episode/add/', {'episode_id': eid(6003), 'only_this': 1, 'next': SERIES_PAGE}, **HTMX
    )

    body = response.content.decode()
    assert changed_rows(body) == [str(eid(6003))]
    assert is_watched(body, 3) and '<div id="ask" hx-swap-oob="true"></div>' in body
    assert 'as watched' in season_button(body, 1)  # one episode of three: the season is not complete
    assert watched(opened.user) == {6003}


def test_with_htmx_yes_takes_the_question_off_the_page(opened):
    body = up_to_here(opened, 6003, **HTMX).content.decode()

    assert '<div id="ask" hx-swap-oob="true"></div>' in body


# --- safety -----------------------------------------------------------------------------------

SEASON_ADDRESSES = ['/watched/season/add/', '/watched/season/remove/']
ADDRESSES = [*SEASON_ADDRESSES, '/watched/up-to/add/']


@pytest.mark.parametrize('address', SEASON_ADDRESSES)
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
def test_a_season_button_with_nonsense_is_refused(opened, address, form):
    mark_season(opened, 1)
    before = snapshot()

    assert opened.post(address, form).status_code == 400
    assert snapshot() == before


@pytest.mark.parametrize('address', SEASON_ADDRESSES)
def test_a_season_or_series_that_does_not_exist_is_not_found(opened, address):
    assert opened.post(address, {'tmdb_id': 1399, 'season': 9}).status_code == 404
    assert opened.post(address, {'tmdb_id': 5, 'season': 1}).status_code == 404
    assert Watch.objects.count() == 0


@pytest.mark.parametrize('form', [{}, {'episode_id': ''}, {'episode_id': 'abc'}])
def test_a_yes_with_nonsense_is_refused(opened, form):
    assert opened.post('/watched/up-to/add/', form).status_code == 400
    assert Watch.objects.count() == 0


def test_a_yes_for_an_episode_that_does_not_exist_is_not_found(opened):
    assert opened.post('/watched/up-to/add/', {'episode_id': 99999}).status_code == 404


def test_the_old_undo_address_is_gone(opened):
    assert opened.post('/watched/batch/remove/', {'batch': 'abc'}).status_code == 404


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
    asked = opened.post('/watched/episode/add/', {'episode_id': eid(6003), 'next': elsewhere})  # the question
    assert asked['Location'] == '/series/'
    pressed = opened.post('/watched/season/add/', {'tmdb_id': 1399, 'season': 1, 'next': elsewhere})
    assert pressed['Location'] == '/series/'
    up_to = opened.post('/watched/up-to/add/', {'episode_id': eid(6103), 'next': elsewhere})
    assert up_to['Location'] == '/series/'
    undone = opened.post('/watched/season/remove/', {'tmdb_id': 1399, 'season': 1, 'next': elsewhere})
    assert undone['Location'] == '/series/'


def test_the_tmdb_key_never_reaches_the_browser(opened):
    body = mark_season(opened, 1, **HTMX).content.decode()

    assert 'made-up-secret-key' not in body
