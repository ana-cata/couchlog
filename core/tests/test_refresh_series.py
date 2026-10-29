import datetime
import io

import httpx
import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError

from core.models import Episode, Title, ToWatchItem, Watch

TV_URL = 'https://api.themoviedb.org/3/tv/{}'

# Made-up TMDB answers. The tests never call the real TMDB.


def series_answer(tmdb_id, status='Returning Series'):
    return {'id': tmdb_id, 'name': f'Made-up Series {tmdb_id}', 'status': status, 'seasons': [{'season_number': 1}]}


def season_answer(*episodes):
    """A season 1 with the given episodes, as (TMDB's episode id, number, name, air date)."""
    return {
        'season_number': 1,
        'episodes': [
            {'id': episode_id, 'season_number': 1, 'episode_number': number, 'name': name, 'air_date': air_date}
            for episode_id, number, name, air_date in episodes
        ],
    }


@pytest.fixture(autouse=True)
def tmdb_key(settings):
    settings.TMDB_API_KEY = 'made-up-secret-key'


@pytest.fixture
def user(db):
    return User.objects.create_user(username='made-up-user', password='made-up-password')


def make_series(tmdb_id, **fields):
    return Title.objects.create(kind='series', tmdb_id=tmdb_id, title=f'Made-up Series {tmdb_id}', **fields)


def mock_series(respx_mock, tmdb_id, status='Returning Series', episodes=((1101, 1, 'Pilot', '2011-04-17'),)):
    respx_mock.get(TV_URL.format(tmdb_id)).respond(json=series_answer(tmdb_id, status))
    respx_mock.get(TV_URL.format(tmdb_id) + '/season/1').respond(json=season_answer(*episodes))


def run():
    """Run the command. Returns what it printed, and what it said about problems."""
    out, err = io.StringIO(), io.StringIO()
    try:
        call_command('refresh_series', stdout=out, stderr=err)
    except CommandError as error:
        return out.getvalue(), err.getvalue(), str(error)
    return out.getvalue(), err.getvalue(), None


def test_it_refreshes_a_series_on_a_to_watch_list_and_saves_episodes_and_status(user, respx_mock):
    series = make_series(11)
    ToWatchItem.objects.create(user=user, title=series)
    mock_series(respx_mock, 11, status='Ended', episodes=[(1101, 1, 'Pilot', '2011-04-17'), (1102, 2, 'Second', '2011-04-24')])

    out, err, problem = run()

    series.refresh_from_db()
    assert (series.status, series.episodes.count()) == ('Ended', 2)
    assert series.episodes_refreshed_at is not None
    assert 'Made-up Series 11' in out and '2 new episodes' in out and 'Ended' in out
    assert 'Refreshed 1 series.' in out
    assert (err, problem) == ('', None)


def test_it_refreshes_a_series_with_a_watched_episode_that_is_on_no_list(user, respx_mock):
    series = make_series(12)
    pilot = Episode.objects.create(title=series, tmdb_id=1201, season_number=1, episode_number=1)
    Watch.objects.create(user=user, title=series, episode=pilot)
    mock_series(respx_mock, 12, status='Ended')

    out, _err, _problem = run()

    series.refresh_from_db()
    assert series.status == 'Ended'
    assert 'Refreshed 1 series.' in out


def test_it_leaves_alone_series_nobody_follows_and_movies(user, respx_mock):
    nobody_follows = make_series(13)
    removed = make_series(14)
    ToWatchItem.objects.create(user=user, title=removed, removed_at=datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC))
    film = Title.objects.create(kind='movie', tmdb_id=15, title='Made-up Movie')
    ToWatchItem.objects.create(user=user, title=film)
    # Nothing is mocked, so the test would fail if TMDB were asked about any of them.

    out, _err, _problem = run()

    assert 'Refreshed 0 series.' in out
    assert respx_mock.calls.call_count == 0
    for title in (nobody_follows, removed, film):
        title.refresh_from_db()
        assert title.episodes_refreshed_at is None


def test_a_series_followed_by_two_accounts_is_refreshed_once(user, respx_mock):
    other = User.objects.create_user(username='second-user', password='made-up-password')
    series = make_series(11)
    ToWatchItem.objects.create(user=user, title=series)
    ToWatchItem.objects.create(user=other, title=series)
    mock_series(respx_mock, 11)

    out, _err, _problem = run()

    assert 'Refreshed 1 series.' in out
    assert respx_mock.calls.call_count == 2  # the series and its one season, once


def test_new_episodes_come_in_and_a_renumbered_one_keeps_its_watch(user, respx_mock):
    series = make_series(11, status='Returning Series')
    ToWatchItem.objects.create(user=user, title=series)
    mock_series(respx_mock, 11, episodes=[(1101, 1, 'Pilot', '2011-04-17'), (1102, 2, 'Second', '2011-04-24')])
    run()
    second = Episode.objects.get(tmdb_id=1102)
    watch = Watch.objects.create(user=user, title=series, episode=second)
    # TMDB now numbers the old second episode 3, and has a new episode 2.
    mock_series(
        respx_mock, 11, status='Ended',
        episodes=[
            (1101, 1, 'Pilot', '2011-04-17'),
            (1102, 3, 'Second', '2011-04-24'),  # the same episode, now number 3
            (1109, 2, 'A new one', '2011-05-01'),
        ],
    )

    out, _err, _problem = run()

    assert series.episodes.count() == 3 and 'Ended, 1 new episode' in out and '1 new episodes' not in out
    watch.refresh_from_db()
    assert (watch.episode_id, watch.episode.episode_number) == (second.id, 3)
    series.refresh_from_db()
    assert series.status == 'Ended'


def test_running_it_twice_changes_nothing_but_the_refresh_time(user, respx_mock):
    series = make_series(11)
    ToWatchItem.objects.create(user=user, title=series)
    mock_series(respx_mock, 11)
    run()
    before = list(Episode.objects.order_by('id').values())

    out, _err, _problem = run()

    assert list(Episode.objects.order_by('id').values()) == before
    assert '0 new episodes' in out


def test_one_series_failing_does_not_stop_the_others(user, respx_mock):
    broken, fine = make_series(11), make_series(12)
    ToWatchItem.objects.create(user=user, title=broken)
    ToWatchItem.objects.create(user=user, title=fine)
    respx_mock.get(TV_URL.format(11)).mock(side_effect=httpx.ConnectError('no network'))
    mock_series(respx_mock, 12)

    out, err, problem = run()

    assert 'Could not refresh “Made-up Series 11”' in err and 'Could not reach TMDB' in err
    assert 'Refreshed 1 series.' in out
    assert fine.episodes.count() == 1
    assert broken.episodes.count() == 0 and Title.objects.get(tmdb_id=11).episodes_refreshed_at is None  # nothing half saved
    assert problem == '1 series could not be refreshed. Run the command again later.'  # so a scheduler can tell


def test_without_a_tmdb_key_every_series_is_reported_and_nothing_crashes(user, respx_mock, settings):
    settings.TMDB_API_KEY = ''
    ToWatchItem.objects.create(user=user, title=make_series(11))

    _out, err, problem = run()

    assert 'TMDB_API_KEY is not set' in err
    assert problem is not None
    assert respx_mock.calls.call_count == 0
