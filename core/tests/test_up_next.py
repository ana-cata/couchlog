"""Up Next on the Home page and the progress bars: the "next episode" and "watched out of aired" calculations,
and the screens that show them."""

import datetime
import re

import pytest
import time_machine
from django.contrib.auth.models import User
from django.test import Client

from core.episodes import progress_by_series, up_next
from core.models import Episode, Profile, Title, ToWatchItem, Watch

# The fixed "today": 8 pm UTC on 28 Oct 2026 (still the 28th in Lisbon).
NOW = datetime.datetime(2026, 10, 28, 20, 0, tzinfo=datetime.UTC)
TODAY = datetime.date(2026, 10, 28)
LONG_AGO = datetime.date(2011, 4, 17)
TOMORROW = datetime.date(2026, 10, 29)

HTMX = {'HX-Request': 'true'}


@pytest.fixture(autouse=True)
def clock():
    with time_machine.travel(NOW, tick=False) as traveller:
        yield traveller


@pytest.fixture
def user(db):
    return User.objects.create_user(username='made-up-user', password='made-up-password')


def make_series(tmdb_id=1, status='Returning Series'):
    return Title.objects.create(
        kind='series', tmdb_id=tmdb_id, title=f'Made-up Series {tmdb_id}', status=status, episodes_refreshed_at=NOW
    )


def make_episode(series, season, number, air_date=LONG_AGO):
    tmdb_id = series.tmdb_id * 1000 + season * 100 + number
    return Episode.objects.create(
        title=series, tmdb_id=tmdb_id, season_number=season, episode_number=number, air_date=air_date, name=f'Name {number}'
    )


def make_watch(user, episode, created_at=None):
    watch = Watch.objects.create(user=user, title=episode.title, episode=episode, watched_on=TODAY)
    if created_at:
        Watch.objects.filter(id=watch.id).update(created_at=created_at)
    return watch


def next_ones(user, today=TODAY):
    """What Up Next lists, as (series TMDB id, 'S1E2', watched, aired)."""
    return [
        (
            entry['series'].tmdb_id,
            f'S{entry["episode"].season_number}E{entry["episode"].episode_number}',
            entry['watched'],
            entry['aired'],
        )
        for entry in up_next(user, today)
    ]


# --- the next episode -------------------------------------------------------------------------


def test_the_next_episode_is_the_first_one_not_watched_that_has_aired(user):
    series = make_series()
    make_watch(user, make_episode(series, 1, 1))
    make_episode(series, 1, 2)
    make_episode(series, 1, 3)

    assert next_ones(user) == [(1, 'S1E2', 1, 3)]


def test_the_next_episode_goes_on_to_the_next_season(user):
    series = make_series()
    make_watch(user, make_episode(series, 1, 1))
    make_watch(user, make_episode(series, 1, 2))
    make_episode(series, 2, 1)

    assert next_ones(user) == [(1, 'S2E1', 2, 3)]


def test_with_a_gap_the_first_episode_not_watched_is_next_even_if_later_ones_are_watched(user):
    series = make_series()
    make_episode(series, 1, 1)
    make_watch(user, make_episode(series, 1, 2))  # watched on its own: "No, only this one"
    make_watch(user, make_episode(series, 1, 3))

    assert next_ones(user) == [(1, 'S1E1', 2, 3)]


def test_the_order_is_by_season_and_episode_number_not_by_when_they_were_saved(user):
    series = make_series()
    make_watch(user, make_episode(series, 1, 1))
    make_episode(series, 2, 1)  # saved before season 1 episode 2
    make_episode(series, 1, 2)

    assert next_ones(user) == [(1, 'S1E2', 1, 3)]


def test_specials_are_never_next_and_do_not_count_in_progress(user):
    series = make_series()
    make_watch(user, make_episode(series, 1, 1))
    make_episode(series, 0, 1)  # a special that has aired, not watched
    make_episode(series, 1, 2)

    assert next_ones(user) == [(1, 'S1E2', 1, 2)]


def test_a_series_with_only_specials_left_has_nothing_next(user):
    series = make_series()
    make_watch(user, make_episode(series, 1, 1))
    make_episode(series, 0, 1)

    assert next_ones(user) == []


def test_watching_a_special_does_not_count_in_progress_but_starts_the_series(user):
    series = make_series()
    make_watch(user, make_episode(series, 0, 1))
    make_episode(series, 1, 1)

    assert next_ones(user) == [(1, 'S1E1', 0, 1)]


def test_episodes_that_have_not_aired_or_have_no_date_are_never_next(user):
    series = make_series()
    make_watch(user, make_episode(series, 1, 1))
    make_episode(series, 1, 2, air_date=TOMORROW)
    make_episode(series, 1, 3, air_date=None)

    assert next_ones(user) == []


def test_a_series_with_no_episodes_aired_has_nothing_next(user):
    series = make_series()
    make_watch(user, make_episode(series, 0, 1))  # started with a special
    make_episode(series, 1, 1, air_date=TOMORROW)

    assert next_ones(user) == []


def test_an_episode_airing_today_can_be_next(user):
    series = make_series()
    make_watch(user, make_episode(series, 1, 1))
    make_episode(series, 1, 2, air_date=TODAY)

    assert next_ones(user) == [(1, 'S1E2', 1, 2)]


def test_a_series_with_everything_watched_leaves_the_list_until_a_new_episode_airs(user):
    series = make_series(status='Returning Series')
    make_watch(user, make_episode(series, 1, 1))
    upcoming = make_episode(series, 1, 2, air_date=TOMORROW)
    assert next_ones(user) == []  # caught up, but still running: it waits

    # The day passes (here the account's day is the 29th): the episode has aired and the series is back.
    assert next_ones(user, today=TOMORROW) == [(1, 'S1E2', 1, 2)]

    # Or TMDB brings a new episode in: it is next at once.
    upcoming.air_date = LONG_AGO
    upcoming.save()
    make_watch(user, upcoming)
    assert next_ones(user) == []
    make_episode(series, 1, 3)
    assert next_ones(user) == [(1, 'S1E3', 2, 3)]


def test_a_finished_series_is_not_listed(user):
    series = make_series(status='Ended')
    make_watch(user, make_episode(series, 1, 1))

    assert next_ones(user) == []


def test_an_ended_series_not_fully_watched_is_listed(user):
    series = make_series(status='Ended')
    make_watch(user, make_episode(series, 1, 1))
    make_episode(series, 1, 2)

    assert next_ones(user) == [(1, 'S1E2', 1, 2)]


def test_a_series_nothing_was_watched_of_is_not_listed_even_on_the_to_watch_list(user):
    series = make_series()
    make_episode(series, 1, 1)
    ToWatchItem.objects.create(user=user, title=series)

    assert next_ones(user) == []


def test_a_rewatch_counts_once_in_progress(user):
    series = make_series()
    first = make_episode(series, 1, 1)
    make_episode(series, 1, 2)
    make_watch(user, first)
    make_watch(user, first)  # the same episode again

    assert next_ones(user) == [(1, 'S1E2', 1, 2)]


def test_other_accounts_watches_do_not_count(user):
    other = User.objects.create_user(username='second-user', password='made-up-password')
    series = make_series()
    first = make_episode(series, 1, 1)
    make_episode(series, 1, 2)
    make_watch(other, first)
    make_watch(user, make_episode(series, 0, 1))  # I started it with a special

    assert next_ones(user) == [(1, 'S1E1', 0, 2)]  # the other account's watch did not move my episode or my bar
    assert next_ones(other) == [(1, 'S1E2', 1, 2)]


def test_the_series_marked_most_recently_come_first(user):
    long_ago = datetime.datetime(2020, 1, 1, tzinfo=datetime.UTC)
    for tmdb_id, days in ((1, 0), (2, 9), (3, 5)):
        series = make_series(tmdb_id)
        make_watch(user, make_episode(series, 1, 1), created_at=long_ago + datetime.timedelta(days=days))
        make_episode(series, 1, 2)

    assert [row[0] for row in next_ones(user)] == [2, 3, 1]


def test_whether_an_episode_has_aired_follows_the_accounts_own_day(user):
    series = make_series()
    make_watch(user, make_episode(series, 1, 1))
    make_episode(series, 1, 2, air_date=TOMORROW)  # the 29th

    assert next_ones(user, today=TODAY) == []  # still the 28th in Lisbon
    assert next_ones(user, today=TOMORROW) == [(1, 'S1E2', 1, 2)]  # already the 29th in Auckland


# --- the progress count -----------------------------------------------------------------------


def test_progress_is_watched_out_of_aired_without_specials_unaired_or_undated_episodes(user):
    series = make_series()
    make_watch(user, make_episode(series, 1, 1))
    make_episode(series, 1, 2)
    make_episode(series, 1, 3, air_date=TOMORROW)
    make_episode(series, 1, 4, air_date=None)
    make_watch(user, make_episode(series, 0, 1))
    make_episode(series, 0, 2)

    assert progress_by_series(user, [series.id], TODAY) == {series.id: (1, 2)}


def test_progress_of_a_series_with_no_episodes_is_nothing_out_of_nothing(user):
    series = make_series()

    assert progress_by_series(user, [series.id], TODAY) == {series.id: (0, 0)}


def test_progress_of_a_watched_episode_whose_date_moved_to_the_future_does_not_count(user):
    series = make_series()
    make_watch(user, make_episode(series, 1, 1))
    moved = make_episode(series, 1, 2)
    make_watch(user, moved)
    Episode.objects.filter(id=moved.id).update(air_date=TOMORROW)  # TMDB moved its date later

    assert progress_by_series(user, [series.id], TODAY) == {series.id: (1, 1)}


# --- the Home screen --------------------------------------------------------------------------


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


def home(client):
    return client.get('/').content.decode()


def cards(html):
    """The Home page's cards, as (series name, 'S1E2', (watched, aired) or None when the card has no bar)."""
    found = []
    for block in re.findall(r'<li id="up-next-\d+">(.*?)</li>', html, re.DOTALL):
        name = re.search(r'<strong><a [^>]*>([^<]+)</a>', block)[1]
        episode = re.search(r'<span>(S\d+E\d+) ·', block)[1]
        numbers = re.search(r'value="(\d+)" max="(\d+)"', block)
        found.append((name, episode, (int(numbers[1]), int(numbers[2])) if numbers else None))
    return found


def check_off(client, episode, htmx=False):
    """Press the check button of a Home card (the browser sends `up_next` with it, and with htmx the header)."""
    data = {'episode_id': episode.id, 'up_next': '1', 'next': '/'}
    return client.post('/watched/episode/add/', data, headers=HTMX if htmx else {})


def snapshot():
    return [list(model.objects.order_by('id').values()) for model in (Episode, Watch, ToWatchItem, Title)]


@pytest.fixture
def two_series(client):
    """Series 1 with S1E1 watched and S1E2, S1E3 to watch; series 2 with S1E1 watched and S1E2 to watch."""
    first, second = make_series(1), make_series(2)
    client.episodes = {(1, number): make_episode(first, 1, number) for number in (1, 2, 3)}
    client.episodes.update({(2, number): make_episode(second, 1, number) for number in (1, 2)})
    long_ago = datetime.datetime(2020, 1, 1, tzinfo=datetime.UTC)
    make_watch(client.user, client.episodes[(1, 1)], created_at=long_ago + datetime.timedelta(days=2))
    make_watch(client.user, client.episodes[(2, 1)], created_at=long_ago + datetime.timedelta(days=1))
    return client


def test_home_shows_the_next_episode_and_progress_of_each_series_in_watching(two_series):
    assert cards(home(two_series)) == [
        ('Made-up Series 1', 'S1E2', (1, 3)),
        ('Made-up Series 2', 'S1E2', (1, 2)),
    ]


def test_home_shows_the_episode_name_air_date_and_a_link_to_the_series(two_series):
    html = home(two_series)

    assert 'Name 2' in html
    assert 'Aired 17 Apr 2011' in html
    assert 'href="/series/1/"' in html
    assert '1 of 3 aired episodes watched' in html


def test_home_has_no_cards_before_anything_is_watched(client):
    series = make_series()
    make_episode(series, 1, 1)
    ToWatchItem.objects.create(user=client.user, title=series)

    html = home(client)

    assert cards(html) == []
    assert 'Nothing to watch next' in html


def test_checking_off_a_card_marks_the_episode_and_the_next_one_appears(two_series):
    client = two_series

    response = check_off(client, client.episodes[(1, 2)], htmx=True)

    # The answer is that series' card again, now with the next episode and the bar moved.
    assert cards(response.content.decode()) == [('Made-up Series 1', 'S1E3', (2, 3))]
    watch = Watch.objects.get(user=client.user, episode=client.episodes[(1, 2)])
    assert watch.watched_on == TODAY  # the day the button was pressed
    assert cards(home(client)) == [('Made-up Series 1', 'S1E3', (2, 3)), ('Made-up Series 2', 'S1E2', (1, 2))]


def test_checking_off_the_last_episode_leaves_the_list_and_the_card_goes_with_it(two_series):
    client = two_series
    response = check_off(client, client.episodes[(2, 2)], htmx=True)

    assert response.content.decode().strip() == ''  # nothing is left to show, so htmx takes the card off
    assert cards(home(client)) == [('Made-up Series 1', 'S1E2', (1, 3))]
    # The series is not gone: it is still in Watching, just waiting for a new episode.
    assert client.get('/series/watching/').content.decode().count('class="tile"') == 2


def test_a_series_that_is_left_with_nothing_to_watch_comes_back_when_a_new_episode_airs(two_series):
    client = two_series
    check_off(client, client.episodes[(2, 2)], htmx=True)
    assert [card[0] for card in cards(home(client))] == ['Made-up Series 1']

    make_episode(Title.objects.get(tmdb_id=2), 1, 3)  # TMDB brings in a new episode that has aired

    # Series 2 was marked last, so it comes first.
    assert cards(home(client)) == [('Made-up Series 2', 'S1E3', (2, 3)), ('Made-up Series 1', 'S1E2', (1, 3))]


def test_checking_off_a_card_without_htmx_goes_back_to_home_with_a_message(two_series):
    client = two_series

    response = check_off(client, client.episodes[(1, 2)])

    assert response.status_code == 302 and response['Location'] == '/'
    html = client.get(response['Location']).content.decode()
    assert 'Marked “Made-up Series 1” S1E2 as watched.' in html
    assert cards(html)[0] == ('Made-up Series 1', 'S1E3', (2, 3))


def test_undoing_a_check_off_brings_the_episode_and_the_bar_back(two_series):
    client = two_series
    rows_before, home_before = snapshot(), cards(home(two_series))

    check_off(client, client.episodes[(1, 2)], htmx=True)
    check_off(client, client.episodes[(2, 2)], htmx=True)
    assert cards(home(client)) == [('Made-up Series 1', 'S1E3', (2, 3))]
    # The undo is the green circle on the series page.
    for key in ((2, 2), (1, 2)):
        watch = Watch.objects.get(user=client.user, episode=client.episodes[key])
        client.post('/watched/remove/', {'watch_id': watch.id, 'episode_id': watch.episode_id}, headers=HTMX)

    assert cards(home(client)) == home_before == [('Made-up Series 1', 'S1E2', (1, 3)), ('Made-up Series 2', 'S1E2', (1, 2))]
    assert snapshot() == rows_before  # every saved row is back as it was


def test_a_card_that_is_out_of_date_shows_how_things_really_are(two_series):
    client = two_series
    check_off(client, client.episodes[(1, 2)], htmx=True)
    rows_before = snapshot()

    # The same card pressed again from a page that was not reloaded (the episode is marked in another tab).
    response = check_off(client, client.episodes[(1, 2)], htmx=True)

    assert cards(response.content.decode()) == [('Made-up Series 1', 'S1E3', (2, 3))]
    assert snapshot() == rows_before  # nothing was marked twice


def test_an_episode_that_has_not_aired_cannot_be_checked_off_from_home(two_series):
    client = two_series
    later = make_episode(Title.objects.get(tmdb_id=1), 1, 4, air_date=TOMORROW)
    rows_before = snapshot()

    check_off(client, later, htmx=True)

    assert snapshot() == rows_before


def test_a_card_that_would_start_the_series_marks_nothing_and_asks_nothing(client):
    """A page that is out of date: the series has no watch any more, so the first mark would ask a question.
    Home has no place for it, so nothing is marked and the series simply is not in Up Next."""
    series = make_series()
    make_episode(series, 1, 1)
    later = make_episode(series, 1, 2)
    rows_before = snapshot()

    response = check_off(client, later, htmx=True)

    assert response.content.decode().strip() == ''
    assert snapshot() == rows_before
    assert 'ask_earlier' not in client.session  # the question is not kept for the series page either


def test_each_account_has_its_own_up_next(two_series):
    other = make_client('second-user')

    assert cards(home(other)) == []
    assert len(cards(home(two_series))) == 2


# --- the progress bars on the series page -----------------------------------------------------


def bar(html, dom_id):
    """(watched, aired) of the bar with this id, or None when it shows no bar."""
    match = re.search(rf'<span class="progress" id="{dom_id}"[^>]*>(.*?)</span>', html, re.DOTALL)
    assert match, f'no bar with the id {dom_id}'
    numbers = re.search(r'value="(\d+)" max="(\d+)"', match[1])
    return (int(numbers[1]), int(numbers[2])) if numbers else None


@pytest.fixture
def series_page(client):
    """A series with a special, two aired episodes in season 1, and one aired and one future in season 2."""
    series = make_series(1)
    client.episodes = {
        'special': make_episode(series, 0, 1),
        'one': make_episode(series, 1, 1),
        'two': make_episode(series, 1, 2),
        'three': make_episode(series, 2, 1),
        'future': make_episode(series, 2, 2, air_date=TOMORROW),
    }
    return client


def test_the_series_page_shows_a_bar_for_the_series_and_one_for_each_season_but_not_the_specials(series_page):
    html = series_page.get('/series/1/').content.decode()

    assert bar(html, 'progress-series') == (0, 3)  # the special and the episode that has not aired are not counted
    assert bar(html, 'progress-season-1') == (0, 2)
    assert bar(html, 'progress-season-2') == (0, 1)
    assert bar(html, 'progress-season-0') is None
    assert '0 of 3 aired episodes watched' in html


def test_a_season_with_nothing_aired_has_no_bar(client):
    series = make_series(1)
    make_episode(series, 1, 1, air_date=TOMORROW)

    html = client.get('/series/1/').content.decode()

    assert bar(html, 'progress-series') is None
    assert bar(html, 'progress-season-1') is None


def test_the_bars_follow_what_is_watched_and_the_series_bar_is_the_seasons_added_up(series_page):
    client = series_page
    make_watch(client.user, client.episodes['one'])
    make_watch(client.user, client.episodes['three'])
    make_watch(client.user, client.episodes['special'])  # a special: no change to any bar

    html = client.get('/series/1/').content.decode()

    assert bar(html, 'progress-season-1') == (1, 2)
    assert bar(html, 'progress-season-2') == (1, 1)
    assert bar(html, 'progress-series') == (2, 3)


def test_marking_an_episode_with_htmx_sends_the_new_bars_along_with_the_row(series_page):
    client = series_page
    make_watch(client.user, client.episodes['one'])  # so marking the next one asks nothing

    response = client.post('/watched/episode/add/', {'episode_id': client.episodes['two'].id}, headers=HTMX)
    html = response.content.decode()

    assert bar(html, 'progress-season-1') == (2, 2)
    assert bar(html, 'progress-series') == (2, 3)
    assert html.count('hx-swap-oob="true"') >= 3  # the season button and both bars are put in place by their ids


def test_marking_a_whole_season_with_htmx_sends_the_new_bars(series_page):
    client = series_page

    response = client.post('/watched/season/add/', {'tmdb_id': 1, 'season': 1}, headers=HTMX)
    html = response.content.decode()

    assert bar(html, 'progress-season-1') == (2, 2)
    assert bar(html, 'progress-series') == (2, 3)


def test_undoing_an_episode_moves_the_bars_back(series_page):
    client = series_page
    rows_before = snapshot()
    watch = make_watch(client.user, client.episodes['one'])

    response = client.post('/watched/remove/', {'watch_id': watch.id, 'episode_id': watch.episode_id}, headers=HTMX)
    html = response.content.decode()

    assert bar(html, 'progress-season-1') == (0, 2)
    assert bar(html, 'progress-series') == (0, 3)
    assert snapshot() == rows_before


def test_the_up_next_card_and_the_series_page_agree(two_series):
    client = two_series
    card = cards(home(client))[0]

    html = client.get('/series/1/').content.decode()

    assert card[2] == bar(html, 'progress-series') == (1, 3)
