"""Watching episodes and seasons again: an episode's circle pressed again counts another watch, the "−" next to it
takes the latest watch back, and "Watch Season N again" adds one watch to every aired episode of a season (with
its own "−" to take one rewatch back). Films are in test_watched.py.

A rewatch only adds watches: progress bars, Up Next, the Series tabs and the Calendar stay as they are (design
rule 2), and every press has an undo (design rule 5)."""

import datetime
import re
from collections import Counter

import pytest
import time_machine
from django.contrib.auth.models import User
from django.test import Client

from core.models import Episode, Profile, ToWatchItem, Watch

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


def made_up_episode(season, number, tmdb_id, air_date):
    return {
        'id': tmdb_id,
        'season_number': season,
        'episode_number': number,
        'name': f'Made-up episode {season}x{number}',
        'air_date': air_date,
        'runtime': 45,
    }


# "Today" below is the 28th in Lisbon and already the 29th in Auckland. Season 1 has aired in full, season 2
# has one episode with no date and one that airs tomorrow (in Lisbon), and season 3 has not started.
SEASONS = {
    0: [made_up_episode(0, 1, 6000, '2010-01-01')],
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
def tmdb_series(respx_mock):
    routes = {'series': respx_mock.get(SERIES_URL).respond(json=MADE_UP_SERIES)}
    for number, episodes in SEASONS.items():
        routes[number] = respx_mock.get(f'{SERIES_URL}/season/{number}').respond(
            json={'season_number': number, 'episodes': episodes}
        )
    return routes


def page(client, url=SERIES_PAGE):
    return client.get(url).content.decode()


@pytest.fixture
def opened(logged_in_client, tmdb_series):
    """The account, with the series opened once so its episodes are saved."""
    page(logged_in_client)
    return logged_in_client


def eid(tmdb_id):
    return Episode.objects.get(tmdb_id=tmdb_id).id


def mark_one(client, tmdb_id, **options):
    """The first mark of an episode, as "No, only this one" makes it (so there is never a question)."""
    return client.post('/watched/episode/add/', {'episode_id': eid(tmdb_id), 'only_this': 1}, **options)


def press_circle(client, tmdb_id, **options):
    """Press an episode's round check button, as the page does."""
    return client.post('/watched/episode/add/', {'episode_id': eid(tmdb_id), 'next': SERIES_PAGE}, **options)


def minus(client, tmdb_id, **options):
    """Press the "−" of an episode's row. The page sends the id of the latest watch of the episode."""
    watch = Watch.objects.filter(user=client.user, episode__tmdb_id=tmdb_id).order_by('created_at', 'id').last()
    return client.post('/watched/remove/', {'watch_id': watch.id, 'episode_id': watch.episode_id}, **options)


def mark_season(client, number, **options):
    return client.post('/watched/season/add/', {'tmdb_id': 1399, 'season': number, 'next': SERIES_PAGE}, **options)


def unmark_season(client, number, **options):
    return client.post('/watched/season/remove/', {'tmdb_id': 1399, 'season': number, 'next': SERIES_PAGE}, **options)


def watch_season_again(client, number, **options):
    return client.post('/watched/season/again/', {'tmdb_id': 1399, 'season': number, 'next': SERIES_PAGE}, **options)


def take_back_season(client, number, **options):
    return client.post(
        '/watched/season/again/remove/', {'tmdb_id': 1399, 'season': number, 'next': SERIES_PAGE}, **options
    )


def counts(user):
    """How many watches this account has of each episode, by the episode's TMDB id."""
    return Counter(Watch.objects.filter(user=user, episode__isnull=False).values_list('episode__tmdb_id', flat=True))


def snapshot():
    """Everything saved about episodes, watches and the To Watch lists, to compare before and after."""
    return [list(model.objects.order_by('id').values()) for model in (Episode, Watch, ToWatchItem)]


def row(html, tmdb_id):
    """The piece of the page that is one episode's row."""
    return re.search(rf'<li id="episode-{eid(tmdb_id)}".*?</li>', html, re.DOTALL).group(0)


def season_block(html, number):
    return re.search(rf'<details id="season-{number}".*?</details>', html, re.DOTALL).group(0)


def minus_watch_id(html, tmdb_id):
    """The watch the "−" of an episode's row would take back, from the form on the page."""
    return int(re.search(r'name="watch_id" value="(\d+)"', row(html, tmdb_id)).group(1))


def is_a_row(body, tmdb_id):
    """Whether an htmx answer is just that episode's row (a piece of a page that htmx puts in place of the row)."""
    return body.lstrip().startswith(f'<li id="episode-{eid(tmdb_id)}">') and '<html' not in body


def changed_rows(body):
    """The ids of the episode rows an answer puts in place of the ones on the page."""
    return re.findall(r'<li id="episode-(\d+)" hx-swap-oob="true">', body)


def without_tokens(html):
    return re.sub(r'name="csrfmiddlewaretoken" value="[^"]+"', '', html)


# --- an episode: the circle pressed again, and the "−" ----------------------------------------


def test_pressing_a_watched_circle_again_counts_it_again_and_the_row_says_how_many(opened):
    mark_one(opened, 6001)
    assert '×' not in row(page(opened), 6001)  # watched once: no count

    press_circle(opened, 6001)
    assert '2×' in row(page(opened), 6001)
    press_circle(opened, 6001)
    assert '3×' in row(page(opened), 6001)

    assert counts(opened.user) == {6001: 3}
    assert {watch.watched_on for watch in Watch.objects.all()} == {TODAY}


def test_a_rewatch_asks_no_question_and_touches_no_other_episode(opened):
    mark_one(opened, 6003)  # on its own: 6001 and 6002 before it are not marked

    response = press_circle(opened, 6003)

    assert '<dialog' not in page(opened, response['Location'])
    assert counts(opened.user) == {6003: 2}


def test_the_minus_takes_the_latest_watch_back_until_the_circle_is_gray_again(opened):
    before = snapshot()
    mark_one(opened, 6001)
    press_circle(opened, 6001)
    press_circle(opened, 6001)
    first, second, third = Watch.objects.order_by('id').values_list('id', flat=True)

    for left, gone in ((2, third), (1, second)):
        html = page(opened)
        assert minus_watch_id(html, 6001) == gone  # the page offers to take back the latest one
        assert 'Take back the latest watch of episode 1' in row(html, 6001)
        minus(opened, 6001)
        assert counts(opened.user) == {6001: left}

    html = page(opened)
    assert minus_watch_id(html, 6001) == first
    assert 'Mark episode 1 as not watched' in row(html, 6001)  # the last one: it says what it does
    minus(opened, 6001)

    html = page(opened)
    assert counts(opened.user) == {}
    assert 'class="check watched"' not in row(html, 6001) and 'Mark episode 1 as watched' in row(html, 6001)
    assert snapshot() == before  # every saved row is back as it was


def test_the_green_circle_no_longer_undoes(opened):
    mark_one(opened, 6001)

    press_circle(opened, 6001)

    assert counts(opened.user) == {6001: 2}  # it added one, it did not remove


def test_a_double_click_adds_two_watches_and_the_minus_is_the_way_back(opened):
    mark_one(opened, 6001)
    before = snapshot()

    press_circle(opened, 6001)
    press_circle(opened, 6001)
    minus(opened, 6001)
    minus(opened, 6001)

    assert snapshot() == before


def test_with_htmx_the_row_comes_back_with_its_new_count(opened):
    mark_one(opened, 6001)

    body = press_circle(opened, 6001, **HTMX).content.decode()

    assert is_a_row(body, 6001)
    assert '2×' in body and 'class="check watched"' in body

    body = minus(opened, 6001, **HTMX).content.decode()

    assert is_a_row(body, 6001)
    assert '×' not in body and 'Mark episode 1 as not watched' in body


def test_an_out_of_date_card_on_home_or_question_never_adds_a_rewatch(opened):
    mark_one(opened, 6001)  # marked in another tab
    before = snapshot()

    # Home's check, and the question's "No, only this one", are about marking for the first time.
    opened.post('/watched/episode/add/', {'episode_id': eid(6001), 'up_next': 1, 'next': '/'})
    opened.post('/watched/episode/add/', {'episode_id': eid(6001), 'only_this': 1})
    opened.post('/watched/episode/add/', {'episode_id': eid(6001), 'up_next': 1}, **HTMX)

    assert snapshot() == before


def test_an_episode_that_has_not_aired_cannot_be_watched(opened):
    before = snapshot()

    press_circle(opened, 6104)  # airs tomorrow in Lisbon
    press_circle(opened, 6102)  # no air date

    assert snapshot() == before


def test_each_account_counts_its_own_watches(opened):
    other = make_client('second-user')
    mark_one(opened, 6001)
    press_circle(opened, 6001)
    mark_one(other, 6001)

    assert '2×' in row(page(opened), 6001) and '×' not in row(page(other), 6001)

    minus(other, 6001)  # the second account takes back its own only watch
    assert counts(opened.user) == {6001: 2} and counts(other.user) == {}


# --- a season: "Watch Season N again" and its "−" -----------------------------------------------


def test_watch_season_again_is_offered_once_everything_that_has_aired_is_marked(opened):
    mark_one(opened, 6001)
    mark_one(opened, 6002)
    assert 'Watch Season 1 again' not in page(opened)

    mark_one(opened, 6003)
    assert 'Watch Season 1 again' in page(opened)

    mark_season(opened, 2)  # 6102 has no date and 6104 airs tomorrow: that does not matter
    mark_season(opened, 0)
    html = page(opened)
    assert 'Watch Season 2 again' in html and 'Watch Specials again' in html
    assert 'season-rewatch' not in season_block(html, 3)  # nothing has aired there


def test_watch_season_again_adds_one_watch_to_every_aired_episode_of_the_season(opened):
    mark_season(opened, 2)  # 6101 and 6103
    mark_season(opened, 1)

    watch_season_again(opened, 2)

    assert counts(opened.user) == {6001: 1, 6002: 1, 6003: 1, 6101: 2, 6103: 2}  # not 6102, not 6104
    html = page(opened)
    assert '2×' in row(html, 6101) and '2×' in row(html, 6103) and '×' not in row(html, 6001)
    assert {watch.watched_on for watch in Watch.objects.all()} == {TODAY}

    watch_season_again(opened, 2)
    assert counts(opened.user)[6101] == 3  # each press adds one more


def test_watch_season_again_follows_the_accounts_time_zone(opened):
    auckland = make_client('auckland-user', 'Pacific/Auckland')  # already the 29th there, so 6104 has aired
    mark_season(auckland, 2)

    watch_season_again(auckland, 2)

    assert counts(auckland.user) == {6101: 2, 6103: 2, 6104: 2}
    assert {watch.watched_on for watch in Watch.objects.filter(user=auckland.user)} == {datetime.date(2026, 10, 29)}


def test_a_season_that_is_not_watched_through_cannot_be_watched_again(opened):
    mark_one(opened, 6001)
    before = snapshot()

    watch_season_again(opened, 1)  # a page that is out of date: 6002 and 6003 are not marked
    watch_season_again(opened, 3)  # nothing has aired
    watch_season_again(opened, 0)  # the special is not marked

    assert snapshot() == before


def test_taking_back_a_season_rewatch_removes_exactly_the_watches_it_added(opened):
    ToWatchItem.objects.create(user=opened.user, title=Episode.objects.get(tmdb_id=6001).title)
    mark_season(opened, 1)
    before = snapshot()

    watch_season_again(opened, 1)
    assert snapshot() != before
    take_back_season(opened, 1)

    assert snapshot() == before  # every saved row is back as it was
    assert counts(opened.user) == {6001: 1, 6002: 1, 6003: 1}


def test_taking_back_a_rewatch_takes_one_off_each_episode_that_has_more_than_one(opened):
    mark_season(opened, 1)
    press_circle(opened, 6001)  # 6001 was also pressed on its own: it has two
    watch_season_again(opened, 1)  # now 6001 has three, the others two

    take_back_season(opened, 1)

    assert counts(opened.user) == {6001: 2, 6002: 1, 6003: 1}  # the known limit: 6001 keeps its extra one
    take_back_season(opened, 1)
    assert counts(opened.user) == {6001: 1, 6002: 1, 6003: 1}
    take_back_season(opened, 1)  # nothing has more than one any more: nothing happens
    assert counts(opened.user) == {6001: 1, 6002: 1, 6003: 1}


def test_the_minus_next_to_the_season_button_shows_only_while_there_is_a_rewatch_to_take_back(opened):
    mark_season(opened, 1)
    assert 'Take back one rewatch of Season 1' not in page(opened)

    watch_season_again(opened, 1)
    assert 'Take back one rewatch of Season 1' in page(opened)
    assert 'Take back one rewatch of Season 2' not in page(opened)  # the other seasons are as they were

    take_back_season(opened, 1)
    assert 'Take back one rewatch of Season 1' not in page(opened)


def test_marking_the_season_as_not_watched_erases_every_watch_of_it_including_the_extra_ones(opened):
    before = snapshot()
    mark_season(opened, 1)
    watch_season_again(opened, 1)
    press_circle(opened, 6002)

    unmark_season(opened, 1)

    assert snapshot() == before


def test_marking_a_season_as_watched_never_adds_a_rewatch(opened):
    mark_season(opened, 1)
    before = snapshot()

    mark_season(opened, 1)  # nothing is new: the "Watch again" button is the one that adds

    assert snapshot() == before


def test_watching_a_season_again_leaves_the_other_seasons_alone(opened):
    mark_season(opened, 1)
    mark_season(opened, 2)

    def season_2():
        return {tmdb_id: n for tmdb_id, n in counts(opened.user).items() if tmdb_id > 6100}

    before = season_2()
    watch_season_again(opened, 1)

    assert season_2() == before == {6101: 1, 6103: 1}


def test_each_account_has_its_own_season_rewatches(opened):
    other = make_client('second-user')
    mark_season(opened, 1)
    mark_season(other, 1)

    watch_season_again(opened, 1)
    take_back_season(other, 1)  # the second account has nothing to take back

    assert counts(opened.user) == {6001: 2, 6002: 2, 6003: 2}
    assert counts(other.user) == {6001: 1, 6002: 1, 6003: 1}


def test_with_htmx_a_season_rewatch_answers_with_the_rows_and_the_new_buttons(opened):
    mark_season(opened, 1)

    body = watch_season_again(opened, 1, **HTMX).content.decode()

    assert '<html' not in body and len(changed_rows(body)) == 3 and body.count('class="watch-count"') == 3
    assert '<div id="season-rewatch-1" class="season-rewatch" hx-swap-oob="true">' in body
    assert 'Watch Season 1 again' in body and 'Take back one rewatch of Season 1' in body
    assert '<div id="ask" hx-swap-oob="true"></div>' in body

    body = take_back_season(opened, 1, **HTMX).content.decode()

    assert len(changed_rows(body)) == 3 and 'class="watch-count"' not in body
    assert 'Watch Season 1 again' in body and 'Take back one rewatch of Season 1' not in body


def test_with_htmx_the_circle_that_completes_a_season_also_brings_its_rewatch_button(opened):
    mark_one(opened, 6001)
    mark_one(opened, 6002)

    body = press_circle(opened, 6003, **HTMX).content.decode()
    assert '<div id="season-rewatch-1"' in body and 'Watch Season 1 again' in body

    body = press_circle(opened, 6003, **HTMX).content.decode()  # watched again: there is one to take back now
    assert 'Take back one rewatch of Season 1' in body


def test_with_htmx_the_minus_that_breaks_a_season_takes_its_rewatch_button_away(opened):
    mark_season(opened, 1)

    body = minus(opened, 6002, **HTMX).content.decode()  # 6002 is no longer watched at all

    assert 'Watch Season 1 again' not in body and 'Mark Season 1 as watched' in body


# --- nothing else changes -----------------------------------------------------------------------


def screens(client):
    """Home, the Series tabs and the Calendar, without the random tokens, and the progress sentences of the series page."""
    pages = [without_tokens(page(client, url)) for url in ('/', '/series/', '/series/watching/', '/series/finished/', '/calendar/')]
    sentences = re.findall(r'\d+ of \d+ episodes?', page(client))
    return pages, sentences


def test_a_rewatch_changes_no_progress_bar_no_up_next_no_tab_and_no_calendar(opened):
    mark_season(opened, 1)
    mark_one(opened, 6101)  # S2E3 is what Up Next offers
    before = screens(opened)
    assert 'S2E3' in before[0][0] and before[1]  # the card and the bars are really there

    press_circle(opened, 6001)
    press_circle(opened, 6001)
    watch_season_again(opened, 1)
    press_circle(opened, 6101)

    assert screens(opened) == before


# --- the pages need a login -----------------------------------------------------------------------


@pytest.mark.parametrize('method', ['get', 'post'])
@pytest.mark.parametrize('address', ['/watched/season/again/', '/watched/season/again/remove/'])
def test_the_season_rewatch_buttons_need_a_login(db, method, address):
    response = getattr(Client(), method)(address)

    assert response.status_code == 302 and response['Location'].startswith('/login/')


@pytest.mark.parametrize('address', ['/watched/season/again/', '/watched/season/again/remove/'])
def test_the_season_rewatch_buttons_only_accept_posts(logged_in_client, address):
    assert logged_in_client.get(address).status_code == 405


@pytest.mark.parametrize('address', ['/watched/season/again/', '/watched/season/again/remove/'])
@pytest.mark.parametrize('form', [{}, {'tmdb_id': 'abc', 'season': 1}, {'tmdb_id': 1399, 'season': 'x'}])
def test_the_season_rewatch_buttons_refuse_nonsense(opened, address, form):
    assert opened.post(address, form).status_code == 400
