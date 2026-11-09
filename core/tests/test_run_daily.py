import datetime
import io

import httpx
import pytest
import time_machine
from django.contrib.auth.models import User
from django.core.management import call_command
from django.db.migrations.recorder import MigrationRecorder
from django.db.utils import OperationalError

from core.management.commands import run_daily
from core.models import Title, ToWatchItem

NOW = datetime.datetime(2026, 11, 9, 10, 0, tzinfo=datetime.UTC)
TV_URL = 'https://api.themoviedb.org/3/tv/11'
SEASON_URL = TV_URL + '/season/1'


class Stopped(Exception):
    """Raised by the made-up sleep, because `run_daily` otherwise goes on for ever."""


# Made-up TMDB answers. The tests never call the real TMDB.
SERIES = {'id': 11, 'name': 'Made-up Series 11', 'status': 'Returning Series', 'seasons': [{'season_number': 1}], 'genres': []}


def season(*numbers):
    episodes = [
        {'id': 1100 + n, 'season_number': 1, 'episode_number': n, 'name': f'Episode {n}', 'air_date': '2026-01-01'} for n in numbers
    ]
    return {'season_number': 1, 'episodes': episodes}


@pytest.fixture(autouse=True)
def tmdb_key(settings):
    settings.TMDB_API_KEY = 'made-up-secret-key'


@pytest.fixture
def clock():
    with time_machine.travel(NOW, tick=False) as traveller:
        yield traveller


@pytest.fixture
def series(db):
    user = User.objects.create_user(username='made-up-user', password='made-up-password')
    title = Title.objects.create(kind='series', tmdb_id=11, title='Made-up Series 11')
    ToWatchItem.objects.create(user=user, title=title)
    return title


@pytest.fixture
def sleeps(monkeypatch, clock):
    """A sleep that waits for nothing: it moves the frozen clock on and remembers how long it was asked to wait. It
    stops the command at the third wait of a day, so a test sees three runs."""
    asked = []

    def sleep(seconds):
        asked.append(seconds)
        clock.shift(datetime.timedelta(seconds=seconds))
        if asked.count(run_daily.A_DAY) == 3:
            raise Stopped

    monkeypatch.setattr(run_daily.time, 'sleep', sleep)
    return asked


def run():
    """Run the command until the made-up sleep stops it. Returns what it printed and what it said about problems."""
    out, err = io.StringIO(), io.StringIO()
    with pytest.raises(Stopped):
        call_command('run_daily', stdout=out, stderr=err)
    return out.getvalue(), err.getvalue()


def test_it_refreshes_at_the_start_and_again_a_day_later(series, sleeps, respx_mock):
    respx_mock.get(TV_URL).respond(json=SERIES)
    # A new episode appears on TMDB the next day, and the second run brings it in.
    respx_mock.get(SEASON_URL).side_effect = [
        httpx.Response(200, json=season(1)),
        httpx.Response(200, json=season(1, 2)),
        httpx.Response(200, json=season(1, 2)),
    ]

    out, err = run()

    assert series.episodes.count() == 2
    assert sleeps == [run_daily.A_DAY] * 3
    assert '2026-11-09 10:00 UTC Starting refresh_calendar.' in out
    assert '2026-11-10 10:00 UTC Starting refresh_calendar.' in out
    assert '2026-11-10 10:00 UTC Finished refresh_calendar.' in out
    assert '“Made-up Series 11”' in out  # the refresh's own lines are in the log too
    assert err == ''


def test_a_failed_refresh_is_reported_and_it_tries_again_the_next_day(series, sleeps, respx_mock):
    respx_mock.get(TV_URL).side_effect = [
        httpx.Response(500),
        httpx.Response(200, json=SERIES),
        httpx.Response(200, json=SERIES),
    ]
    respx_mock.get(SEASON_URL).respond(json=season(1))

    out, err = run()

    assert '2026-11-09 10:00 UTC refresh_calendar failed' in err
    assert 'It runs again in 24 hours.' in err
    assert '2026-11-10 10:00 UTC Finished refresh_calendar.' in out
    assert series.episodes.count() == 1


def test_an_unexpected_error_does_not_stop_it_either(db, sleeps, monkeypatch):
    def locked(*args, **kwargs):
        raise OperationalError('database is locked')

    monkeypatch.setattr(run_daily, 'call_command', locked)

    _, err = run()

    assert err.count('database is locked') == 3
    assert sleeps == [run_daily.A_DAY] * 3


def test_a_command_that_fails_does_not_stop_the_next_one(db, sleeps, monkeypatch):
    ran = []

    def fake(name, **kwargs):
        ran.append(name)
        if name == 'first':
            raise RuntimeError('made-up problem')

    monkeypatch.setattr(run_daily, 'DAILY_COMMANDS', ['first', 'second'])
    monkeypatch.setattr(run_daily, 'call_command', fake)

    run()

    assert ran == ['first', 'second'] * 3


def test_it_waits_for_the_migrations_before_the_first_refresh(db, clock, monkeypatch):
    # One migration is missing from the database until the app has "applied" it, during the second wait.
    newest = MigrationRecorder.Migration.objects.filter(app='core').order_by('-id').first()
    app, name = newest.app, newest.name
    newest.delete()
    ran = []
    waits = []

    def sleep(seconds):
        waits.append(seconds)
        if seconds != run_daily.A_DAY:
            assert ran == []  # nothing runs while a migration is missing
        if len(waits) == 2:
            MigrationRecorder.Migration.objects.create(app=app, name=name)
        if seconds == run_daily.A_DAY:
            raise Stopped

    monkeypatch.setattr(run_daily.time, 'sleep', sleep)
    monkeypatch.setattr(run_daily, 'call_command', lambda name, **kwargs: ran.append(name))

    out, _ = run()

    assert waits ==[run_daily.MIGRATIONS_CHECK_EVERY, run_daily.MIGRATIONS_CHECK_EVERY, run_daily.A_DAY]
    assert ran == ['refresh_calendar']
    assert out.count('Waiting for the app to apply the migrations.') == 1


def test_it_does_not_wait_when_the_migrations_are_already_applied(db):
    assert run_daily.migrations_are_applied() is True


def test_a_database_that_answers_with_an_error_counts_as_not_ready(db, monkeypatch):
    def locked(*args, **kwargs):
        raise OperationalError('database is locked')

    monkeypatch.setattr(run_daily, 'MigrationExecutor', locked)

    assert run_daily.migrations_are_applied() is False
