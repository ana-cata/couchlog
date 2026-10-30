"""TVmaze, the second source for upcoming episode dates: finding a series there, saving its upcoming episodes, and
the Calendar showing the ones TMDB does not list (each once, and no watch ever lost).

Every answer from TMDB and TVmaze is made up; the tests never call the real ones. "Today" is fixed.
"""

import datetime
import io
from zoneinfo import ZoneInfo

import httpx
import pytest
import time_machine
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client

from core import tvmaze
from core.episodes import progress_by_series, refresh_episodes, up_next
from core.models import Episode, Profile, Title, ToWatchItem, UpcomingEpisode, Watch
from core.releases import refresh_upcoming, upcoming

# The fixed "today": 8 pm UTC on Wed 28 Oct 2026.
NOW = datetime.datetime(2026, 10, 28, 20, 0, tzinfo=datetime.UTC)
TODAY = datetime.date(2026, 10, 28)
YESTERDAY = datetime.date(2026, 10, 27)
LISBON = ZoneInfo('Europe/Lisbon')
TMDB = 'https://api.themoviedb.org/3'
TVMAZE = 'https://api.tvmaze.com'


def week(number):
    """The Friday `number` weeks after Fri 6 Nov 2026 (week 0)."""
    return datetime.date(2026, 11, 6) + datetime.timedelta(weeks=number)


@pytest.fixture(autouse=True)
def clock():
    with time_machine.travel(NOW, tick=False) as traveller:
        yield traveller


@pytest.fixture(autouse=True)
def tmdb_key(settings):
    settings.TMDB_API_KEY = 'made-up-secret-key'


def make_client(name='made-up-user'):
    account = User.objects.create_user(username=name, password='made-up-password')
    Profile.objects.create(user=account, timezone='Europe/Lisbon')
    client = Client()
    client.force_login(account)
    client.user = account
    return client


@pytest.fixture
def client(db):
    return make_client()


def make_series(tmdb_id=1, imdb_id='', **fields):
    return Title.objects.create(
        kind='series', tmdb_id=tmdb_id, title=f'Made-up Series {tmdb_id}', imdb_id=imdb_id, **fields
    )


def make_episode(series, season, number, air_date, name=''):
    return Episode.objects.create(
        title=series,
        tmdb_id=series.tmdb_id * 1000 + season * 100 + number,
        season_number=season,
        episode_number=number,
        air_date=air_date,
        name=name,
    )


def make_upcoming(series, season, number, air_date, name='TBA'):
    return UpcomingEpisode.objects.create(
        title=series, season_number=season, episode_number=number, air_date=air_date, name=name
    )


def coming(user):
    """What the calendar lists, as [(day, [(title, text), ...]), ...]."""
    return [
        (day['day'], [(item['title'].title, item['text']) for item in day['items']])
        for day in upcoming(user, TODAY, LISBON)
    ]


def tv_episode(season, number, airdate, name='TBA'):
    """One episode as TVmaze lists it."""
    return {
        'id': season * 1000 + number,
        'season': season,
        'number': number,
        'name': name,
        'type': 'regular',
        'airdate': airdate,
    }


def mock_tvmaze(respx_mock, imdb_id, show_id, episodes):
    """TVmaze knowing a show: the lookup by IMDb id, and the show's episodes."""
    respx_mock.get(f'{TVMAZE}/lookup/shows', params={'imdb': imdb_id}).respond(json={'id': show_id, 'name': 'Made-up'})
    return respx_mock.get(f'{TVMAZE}/shows/{show_id}/episodes').respond(json=list(episodes))


def mock_tmdb_series(respx_mock, tmdb_id, imdb_id, episodes=()):
    """TMDB's answers for a series: its details (with the IMDb id) and its season 1, from (id, number, name, date)."""
    external_ids = {'imdb_id': imdb_id} if imdb_id else {'imdb_id': None}
    respx_mock.get(f'{TMDB}/tv/{tmdb_id}').respond(
        json={
            'id': tmdb_id, 'name': f'Made-up Series {tmdb_id}', 'first_air_date': '2026-01-01',
            'status': 'Returning Series', 'seasons': [{'season_number': 1}], 'external_ids': external_ids,
        }
    )
    respx_mock.get(f'{TMDB}/tv/{tmdb_id}/season/1').respond(
        json={
            'season_number': 1,
            'episodes': [
                {'id': episode_id, 'season_number': 1, 'episode_number': number, 'name': name, 'air_date': date}
                for episode_id, number, name, date in episodes
            ],
        }
    )


def saved(series):
    """The upcoming episodes saved for a series, as [(season, number, day, name), ...]."""
    return [
        (row.season_number, row.episode_number, row.air_date, row.name)
        for row in series.upcoming_episodes.order_by('season_number', 'episode_number')
    ]


# --- refreshing a series' upcoming episodes -----------------------------------------------------


def test_it_finds_the_series_by_its_imdb_id_and_saves_the_upcoming_episodes(db, respx_mock):
    series = make_series(1, imdb_id='tt100')
    mock_tvmaze(respx_mock, 'tt100', 48830, [
        tv_episode(1, 1, '2026-10-20', 'Aired already'),
        tv_episode(1, 2, '2026-10-27', 'Yesterday'),
        tv_episode(1, 3, week(0).isoformat(), 'Friday'),
        tv_episode(1, 4, None, 'No date yet'),
        {**tv_episode(1, 5, week(1).isoformat()), 'number': None},
    ])

    refresh_upcoming(series)

    series.refresh_from_db()
    assert series.tvmaze_id == 48830
    # Yesterday is kept (a time zone far from UTC can still be on it), what is older is not; no date or no number is out.
    assert saved(series) == [(1, 2, YESTERDAY, 'Yesterday'), (1, 3, week(0), 'Friday')]


def test_the_lookup_redirect_is_followed(db, respx_mock):
    series = make_series(1, imdb_id='tt100')
    # The real TVmaze answers the lookup with a redirect to the show.
    respx_mock.get(f'{TVMAZE}/lookup/shows', params={'imdb': 'tt100'}).respond(
        301, headers={'Location': f'{TVMAZE}/shows/48830'}
    )
    respx_mock.get(f'{TVMAZE}/shows/48830').respond(json={'id': 48830, 'name': 'Made-up'})
    respx_mock.get(f'{TVMAZE}/shows/48830/episodes').respond(json=[tv_episode(1, 1, week(0).isoformat())])

    refresh_upcoming(series)

    assert saved(series) == [(1, 1, week(0), 'TBA')]


def test_a_series_tvmaze_does_not_know_gets_no_episodes_and_is_no_error(db, respx_mock):
    series = make_series(1, imdb_id='tt100')
    make_upcoming(series, 1, 1, week(0))  # left over from before
    respx_mock.get(f'{TVMAZE}/lookup/shows', params={'imdb': 'tt100'}).respond(404)

    refresh_upcoming(series)

    series.refresh_from_db()
    assert series.tvmaze_id is None and saved(series) == []


def test_a_series_with_no_imdb_id_is_not_looked_up_at_all(db, respx_mock):
    series = make_series(1, imdb_id='')

    refresh_upcoming(series)  # an unmocked call would fail the test

    assert respx_mock.calls.call_count == 0 and saved(series) == []


def test_the_tvmaze_id_is_remembered_so_later_refreshes_ask_one_question(db, respx_mock):
    series = make_series(1, imdb_id='tt100')
    episodes = mock_tvmaze(respx_mock, 'tt100', 48830, [tv_episode(1, 1, week(0).isoformat())])

    refresh_upcoming(series)
    refresh_upcoming(series)

    lookups = [call for call in respx_mock.calls if call.request.url.path == '/lookup/shows']
    assert len(lookups) == 1 and episodes.call_count == 2


def test_an_id_that_tvmaze_no_longer_has_is_forgotten_with_its_episodes(db, respx_mock):
    series = make_series(1, imdb_id='tt100', tvmaze_id=48830)
    make_upcoming(series, 1, 1, week(0))
    respx_mock.get(f'{TVMAZE}/shows/48830/episodes').respond(404)

    refresh_upcoming(series)

    series.refresh_from_db()
    assert series.tvmaze_id is None and saved(series) == []


def test_refreshing_again_replaces_the_episodes_and_never_doubles_them(db, respx_mock):
    series = make_series(1, imdb_id='tt100')
    route = mock_tvmaze(respx_mock, 'tt100', 48830, [tv_episode(1, 1, week(0).isoformat()), tv_episode(1, 2, week(1).isoformat())])
    refresh_upcoming(series)
    refresh_upcoming(series)
    assert saved(series) == [(1, 1, week(0), 'TBA'), (1, 2, week(1), 'TBA')]

    # TVmaze moves the second episode and adds a third.
    route.respond(json=[tv_episode(1, 1, week(0).isoformat()), tv_episode(1, 2, week(2).isoformat()), tv_episode(1, 3, week(3).isoformat())])
    refresh_upcoming(series)

    assert saved(series) == [(1, 1, week(0), 'TBA'), (1, 2, week(2), 'TBA'), (1, 3, week(3), 'TBA')]


@pytest.mark.parametrize(
    'trouble',
    [httpx.ConnectError('no network'), httpx.Response(500), httpx.Response(429)],
    ids=['no network', 'server error', 'too many questions'],
)
def test_when_tvmaze_does_not_answer_nothing_changes_and_the_problem_is_raised(db, respx_mock, trouble):
    series = make_series(1, imdb_id='tt100', tvmaze_id=48830)
    make_upcoming(series, 1, 1, week(0))
    route = respx_mock.get(f'{TVMAZE}/shows/48830/episodes')
    if isinstance(trouble, Exception):
        route.mock(side_effect=trouble)
    else:
        route.mock(return_value=trouble)

    with pytest.raises(tvmaze.TvmazeError):
        refresh_upcoming(series)

    series.refresh_from_db()
    assert series.tvmaze_id == 48830 and saved(series) == [(1, 1, week(0), 'TBA')]


def test_refreshing_the_episodes_from_tmdb_saves_the_imdb_id(db, respx_mock):
    series = make_series(1)
    mock_tmdb_series(respx_mock, 1, 'tt100')

    refresh_episodes(series)

    series.refresh_from_db()
    assert series.imdb_id == 'tt100'


def test_a_series_tmdb_has_no_imdb_id_for_is_saved_with_an_empty_one(db, respx_mock):
    series = make_series(1, imdb_id='tt100')
    mock_tmdb_series(respx_mock, 1, None)

    refresh_episodes(series)

    series.refresh_from_db()
    assert series.imdb_id == ''


# --- the Calendar --------------------------------------------------------------------------------


def test_an_episode_only_tvmaze_knows_is_on_tvmazes_date(client):
    series = make_series(1)
    make_upcoming(series, 6, 3, week(2), name='The Third')
    ToWatchItem.objects.create(user=client.user, title=series)

    assert coming(client.user) == [(week(2), [('Made-up Series 1', 'S6E3 · The Third')])]


def test_a_series_being_watched_gets_the_tvmaze_episodes_too(client):
    series = make_series(1)
    watched = make_episode(series, 1, 1, datetime.date(2011, 4, 17))
    Watch.objects.create(user=client.user, title=series, episode=watched, watched_on=TODAY)
    make_upcoming(series, 1, 2, week(0))

    assert coming(client.user) == [(week(0), [('Made-up Series 1', 'S1E2 · TBA')])]


def test_an_episode_on_both_sources_is_there_once_and_tmdb_wins(client):
    series = make_series(1)
    make_episode(series, 1, 1, week(0), name='From TMDB')
    make_upcoming(series, 1, 1, week(0), name='From TVmaze')
    ToWatchItem.objects.create(user=client.user, title=series)

    assert coming(client.user) == [(week(0), [('Made-up Series 1', 'S1E1 · From TMDB')])]


def test_when_the_two_disagree_on_the_date_tmdbs_date_is_the_only_one(client):
    series = make_series(1)
    make_episode(series, 1, 1, week(1), name='From TMDB')
    make_upcoming(series, 1, 1, week(0), name='From TVmaze')
    ToWatchItem.objects.create(user=client.user, title=series)

    assert coming(client.user) == [(week(1), [('Made-up Series 1', 'S1E1 · From TMDB')])]


def test_an_episode_tmdb_lists_without_a_date_gets_tvmazes_date(client):
    series = make_series(1)
    make_episode(series, 1, 1, None, name='No date on TMDB')
    make_upcoming(series, 1, 1, week(0), name='From TVmaze')
    ToWatchItem.objects.create(user=client.user, title=series)

    assert coming(client.user) == [(week(0), [('Made-up Series 1', 'S1E1 · From TVmaze')])]


def test_an_episode_tmdb_says_has_aired_is_not_brought_back_by_tvmaze(client):
    series = make_series(1)
    make_episode(series, 1, 1, datetime.date(2026, 10, 1), name='Aired')
    make_upcoming(series, 1, 1, week(0))
    ToWatchItem.objects.create(user=client.user, title=series)

    assert coming(client.user) == []


def test_an_episode_tmdb_numbers_differently_is_still_there_once(client):
    series = make_series(1)
    # TVmaze has S6E2 on the 2nd Friday; TMDB later numbers that same day's episode S6E3.
    make_upcoming(series, 6, 1, week(0))
    make_upcoming(series, 6, 2, week(1), name='TVmaze calls it 2')
    make_episode(series, 6, 3, week(1), name='TMDB calls it 3')
    ToWatchItem.objects.create(user=client.user, title=series)

    assert coming(client.user) == [
        (week(0), [('Made-up Series 1', 'S6E1 · TBA')]),
        (week(1), [('Made-up Series 1', 'S6E3 · TMDB calls it 3')]),
    ]


def test_a_season_tmdb_lists_in_full_adds_nothing_from_tvmaze(client):
    series = make_series(1)
    for number in (1, 2, 3):
        make_episode(series, 1, number, week(number), name=f'Episode {number}')
        make_upcoming(series, 1, number, week(number))
    ToWatchItem.objects.create(user=client.user, title=series)

    assert coming(client.user) == [
        (week(number), [('Made-up Series 1', f'S1E{number} · Episode {number}')]) for number in (1, 2, 3)
    ]


def test_several_tvmaze_episodes_on_one_day_share_a_line_and_do_not_hide_each_other(client):
    series = make_series(1)
    make_upcoming(series, 1, 1, week(0))
    make_upcoming(series, 1, 2, week(0))
    make_upcoming(series, 1, 3, week(0))
    ToWatchItem.objects.create(user=client.user, title=series)

    assert coming(client.user) == [(week(0), [('Made-up Series 1', 'S1E1–E3 · 3 episodes')])]


def test_tvmaze_episodes_that_have_passed_are_left_out_and_one_airing_today_stays(client):
    series = make_series(1)
    make_upcoming(series, 1, 1, YESTERDAY)
    make_upcoming(series, 1, 2, TODAY, name='Tonight')
    ToWatchItem.objects.create(user=client.user, title=series)

    assert coming(client.user) == [(TODAY, [('Made-up Series 1', 'S1E2 · Tonight')])]


def test_a_series_that_is_neither_watched_nor_on_the_list_gets_nothing_from_tvmaze(client):
    make_upcoming(make_series(1), 1, 1, week(0))
    on_someone_elses_list = make_series(2)
    make_upcoming(on_someone_elses_list, 1, 1, week(0))
    ToWatchItem.objects.create(user=make_client('someone-else').user, title=on_someone_elses_list)

    assert coming(client.user) == []


def test_tvmaze_episodes_do_not_count_in_progress_or_up_next(client):
    series = make_series(1)
    aired = make_episode(series, 1, 1, datetime.date(2026, 10, 1))
    Watch.objects.create(user=client.user, title=series, episode=aired, watched_on=TODAY)
    make_upcoming(series, 1, 2, TODAY)  # even one TVmaze says airs today

    assert progress_by_series(client.user, [series.id], TODAY) == {series.id: (1, 1)}
    assert up_next(client.user, TODAY) == []


def test_a_watch_is_neither_lost_nor_doubled_when_tmdb_takes_over_an_episode(client, respx_mock):
    series = make_series(1, imdb_id='tt100')
    ToWatchItem.objects.create(user=client.user, title=series)
    mock_tmdb_series(respx_mock, 1, 'tt100', [(5001, 1, 'Pilot', '2026-10-01')])
    refresh_episodes(series)
    pilot = Episode.objects.get(tmdb_id=5001)
    Watch.objects.create(user=client.user, title=series, episode=pilot, watched_on=TODAY)
    mock_tvmaze(respx_mock, 'tt100', 48830, [tv_episode(1, 2, week(0).isoformat()), tv_episode(1, 3, week(1).isoformat())])
    refresh_upcoming(series)
    assert coming(client.user) == [
        (week(0), [('Made-up Series 1', 'S1E2 · TBA')]),
        (week(1), [('Made-up Series 1', 'S1E3 · TBA')]),
    ]

    # TMDB now lists the second episode too.
    mock_tmdb_series(respx_mock, 1, 'tt100', [(5001, 1, 'Pilot', '2026-10-01'), (5002, 2, 'Second', week(0).isoformat())])
    refresh_episodes(series)
    refresh_upcoming(series)

    assert coming(client.user) == [
        (week(0), [('Made-up Series 1', 'S1E2 · Second')]),
        (week(1), [('Made-up Series 1', 'S1E3 · TBA')]),
    ]
    assert list(Watch.objects.values_list('episode__tmdb_id', 'watched_on')) == [(5001, TODAY)]
    assert Episode.objects.count() == 2


# --- collecting them when a title is added to To Watch --------------------------------------------


def add_to_watch(client, tmdb_id=800):
    return client.post('/to-watch/add/', {'kind': 'series', 'tmdb_id': tmdb_id})


def test_adding_a_series_puts_the_whole_season_on_the_calendar_at_once(client, respx_mock):
    # Like Only Murders in the Building: TMDB lists the first episode, TVmaze lists ten weekly ones.
    mock_tmdb_series(respx_mock, 800, 'tt800', [(9001, 1, 'Premiere', week(0).isoformat())])
    mock_tvmaze(respx_mock, 'tt800', 48830, [tv_episode(1, number, week(number - 1).isoformat()) for number in range(1, 11)])

    add_to_watch(client)

    days = coming(client.user)
    assert [day for day, _ in days] == [week(number) for number in range(10)]
    assert days[0] == (week(0), [('Made-up Series 800', 'S1E1 · Premiere')])  # TMDB's own episode, once
    assert days[9] == (week(9), [('Made-up Series 800', 'S1E10 · TBA')])


def test_a_series_saved_before_tvmaze_existed_gets_its_tvmaze_episodes_when_the_command_runs(client, respx_mock):
    # Its episodes were refreshed a moment ago, but with no IMDb id saved (as every series saved before this feature).
    series = make_series(800, imdb_id='', episodes_refreshed_at=NOW)
    ToWatchItem.objects.create(user=client.user, title=series)
    mock_tmdb_series(respx_mock, 800, 'tt800', [(9001, 1, 'Premiere', week(0).isoformat())])
    mock_tvmaze(respx_mock, 'tt800', 48830, [tv_episode(1, number, week(number - 1).isoformat()) for number in range(1, 4)])
    assert coming(client.user) == []

    call_command('refresh_calendar', stdout=io.StringIO(), stderr=io.StringIO())

    series.refresh_from_db()
    assert series.imdb_id == 'tt800' and series.tvmaze_id == 48830
    assert [day for day, _ in coming(client.user)] == [week(0), week(1), week(2)]


def test_adding_still_works_when_tvmaze_does_not_answer(client, respx_mock):
    mock_tmdb_series(respx_mock, 800, 'tt800', [(9001, 1, 'Premiere', week(0).isoformat())])
    respx_mock.get(f'{TVMAZE}/lookup/shows', params={'imdb': 'tt800'}).mock(side_effect=httpx.ConnectError('no network'))

    response = add_to_watch(client)

    assert response.status_code == 302
    assert ToWatchItem.objects.filter(user=client.user, removed_at=None).count() == 1
    assert coming(client.user) == [(week(0), [('Made-up Series 800', 'S1E1 · Premiere')])]  # TMDB's part is there
    assert UpcomingEpisode.objects.count() == 0  # the next `refresh_calendar` run collects them


def test_adding_a_series_tvmaze_does_not_know_works_as_before(client, respx_mock):
    mock_tmdb_series(respx_mock, 800, 'tt800', [(9001, 1, 'Premiere', week(0).isoformat())])
    respx_mock.get(f'{TVMAZE}/lookup/shows', params={'imdb': 'tt800'}).respond(404)

    add_to_watch(client)

    assert coming(client.user) == [(week(0), [('Made-up Series 800', 'S1E1 · Premiere')])]


def test_adding_a_series_with_no_imdb_id_never_asks_tvmaze(client, respx_mock):
    mock_tmdb_series(respx_mock, 800, None, [(9001, 1, 'Premiere', week(0).isoformat())])

    add_to_watch(client)  # a call to TVmaze would fail the test

    assert coming(client.user) == [(week(0), [('Made-up Series 800', 'S1E1 · Premiere')])]


def test_removing_the_series_takes_the_tvmaze_episodes_off_and_undo_brings_them_back(client, respx_mock):
    mock_tmdb_series(respx_mock, 800, 'tt800', [(9001, 1, 'Premiere', week(0).isoformat())])
    mock_tvmaze(respx_mock, 'tt800', 48830, [tv_episode(1, number + 1, week(number).isoformat()) for number in range(1, 4)])
    add_to_watch(client)
    before = coming(client.user)
    assert len(before) == 4

    client.post('/to-watch/remove/', {'kind': 'series', 'tmdb_id': 800})
    removed = coming(client.user)
    client.post('/to-watch/undo/', {'kind': 'series', 'tmdb_id': 800})

    assert removed == []
    assert coming(client.user) == before
    assert UpcomingEpisode.objects.count() == 3  # not doubled


def test_opening_the_series_page_does_not_ask_tvmaze(client, respx_mock):
    mock_tmdb_series(respx_mock, 800, 'tt800', [(9001, 1, 'Premiere', week(0).isoformat())])

    response = client.get('/series/800/')  # a call to TVmaze would fail the test

    assert response.status_code == 200
    assert Title.objects.get(tmdb_id=800).imdb_id == 'tt800'


# --- the refresh_calendar command -----------------------------------------------------------------


def run():
    """Run the command. Returns what it printed, what it said about problems, and the error it ended with."""
    out, err = io.StringIO(), io.StringIO()
    try:
        call_command('refresh_calendar', stdout=out, stderr=err)
    except CommandError as error:
        return out.getvalue(), err.getvalue(), str(error)
    return out.getvalue(), err.getvalue(), None


def test_the_command_collects_the_tvmaze_episodes_too(client, respx_mock):
    series = make_series(11)
    ToWatchItem.objects.create(user=client.user, title=series)
    mock_tmdb_series(respx_mock, 11, 'tt11', [(1101, 1, 'Premiere', week(0).isoformat())])
    mock_tvmaze(respx_mock, 'tt11', 48830, [tv_episode(1, number, week(number - 1).isoformat()) for number in range(1, 4)])

    out, err, problem = run()

    assert '3 upcoming on TVmaze' in out and (err, problem) == ('', None)
    assert len(coming(client.user)) == 3
    run()
    assert UpcomingEpisode.objects.count() == 3  # running it again changes nothing


def test_a_series_tvmaze_cannot_answer_for_is_reported_and_the_others_go_on(client, respx_mock):
    broken, fine = make_series(11), make_series(12)
    ToWatchItem.objects.create(user=client.user, title=broken)
    ToWatchItem.objects.create(user=client.user, title=fine)
    mock_tmdb_series(respx_mock, 11, 'tt11', [(1101, 1, 'Premiere', week(0).isoformat())])
    mock_tmdb_series(respx_mock, 12, 'tt12', [(1201, 1, 'Premiere', week(0).isoformat())])
    respx_mock.get(f'{TVMAZE}/lookup/shows', params={'imdb': 'tt11'}).mock(side_effect=httpx.ConnectError('no network'))
    mock_tvmaze(respx_mock, 'tt12', 48831, [tv_episode(1, 2, week(1).isoformat())])

    out, err, problem = run()

    assert 'Could not refresh the upcoming episodes of “Made-up Series 11” from TVmaze' in err
    assert problem is not None  # so whatever runs it on a schedule can tell
    assert Episode.objects.filter(title=broken).count() == 1  # what TMDB gave is saved
    assert saved(fine) == [(1, 2, week(1), 'TBA')]
    assert 'Refreshed 2 series.' in out


# --- the credit ------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_about_page_credits_tvmaze_and_keeps_the_tmdb_credit(client):
    page = client.get('/about/').content.decode()

    assert 'href="https://www.tvmaze.com/"' in page and 'CC BY-SA' in page
    assert 'This product uses the TMDB API but is not endorsed or certified by TMDB.' in page
