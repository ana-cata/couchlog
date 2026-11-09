"""Backups to Cloudflare R2. A fake R2 in memory, never the real one, and a made-up database file in a temporary folder."""

import datetime
import io
import sqlite3
import tempfile
from contextlib import closing

import pytest
import time_machine
from botocore.exceptions import ClientError, EndpointConnectionError
from django.core.management import call_command
from django.core.management.base import CommandError

from core import backups

NOW = datetime.datetime(2026, 11, 9, 10, 0, tzinfo=datetime.UTC)
FIRST_NAME = 'couchlog-2026-11-09-100000.sqlite3'

SESSION_KEY = 'made-up-session-key'
KEY_VALUES = {
    'TMDB_API_KEY': 'made-up-tmdb-key',
    'SECRET_KEY': 'made-up-login-secret',
    'R2_ACCESS_KEY_ID': 'made-up-r2-key-id',
    'R2_SECRET_ACCESS_KEY': 'made-up-r2-secret',
}


class FakeR2:
    """The four things Couchlog asks of R2, on a dictionary."""

    def __init__(self):
        self.objects = {}
        self.upload_problem = None

    def put_object(self, Bucket, Key, Body):
        assert Bucket == 'made-up-bucket'
        if self.upload_problem:
            raise self.upload_problem
        self.objects[Key] = Body

    def list_objects_v2(self, Bucket, Prefix):
        assert Bucket == 'made-up-bucket'
        contents = [{'Key': key} for key in sorted(self.objects) if key.startswith(Prefix)]
        return {'Contents': contents} if contents else {}

    def delete_object(self, Bucket, Key):
        assert Bucket == 'made-up-bucket'
        del self.objects[Key]

    def get_object(self, Bucket, Key):
        assert Bucket == 'made-up-bucket'
        if Key not in self.objects:
            raise ClientError({'Error': {'Code': 'NoSuchKey', 'Message': 'Not there'}}, 'GetObject')
        return {'Body': io.BytesIO(self.objects[Key])}


@pytest.fixture
def r2(monkeypatch, settings):
    settings.R2_ACCOUNT_ID = 'made-up-account'
    settings.R2_BUCKET = 'made-up-bucket'
    settings.R2_ACCESS_KEY_ID = KEY_VALUES['R2_ACCESS_KEY_ID']
    settings.R2_SECRET_ACCESS_KEY = KEY_VALUES['R2_SECRET_ACCESS_KEY']
    settings.TMDB_API_KEY = KEY_VALUES['TMDB_API_KEY']
    settings.SECRET_KEY = KEY_VALUES['SECRET_KEY']
    fake = FakeR2()
    monkeypatch.setattr(backups, 'r2_client', lambda: fake)
    return fake


@pytest.fixture
def clock():
    with time_machine.travel(NOW, tick=False) as traveller:
        yield traveller


@pytest.fixture
def database(monkeypatch, tmp_path):
    """A real database file in write-ahead log mode, as on the Pi, with a connection left open like the running app's.
    The rows are still in the log file when the backup runs, which is what a plain file copy would miss."""
    path = tmp_path / 'made-up.sqlite3'
    app = sqlite3.connect(path)
    app.execute('PRAGMA journal_mode=WAL')
    app.execute('CREATE TABLE django_session (session_key TEXT, session_data TEXT)')
    app.execute('CREATE TABLE auth_user (username TEXT, password TEXT)')
    app.execute('CREATE TABLE core_watch (note TEXT)')
    app.execute('INSERT INTO django_session VALUES (?, ?)', (SESSION_KEY, 'made-up-session-data'))
    app.execute('INSERT INTO auth_user VALUES (?, ?)', ('made-up-user', 'made-up-scrambled-password'))
    app.execute('INSERT INTO core_watch VALUES (?)', ('first watch',))
    app.commit()
    monkeypatch.setattr(backups, 'database_path', lambda: path)
    yield app
    app.close()


def write(database, sql, *values):
    database.execute(sql, values)
    database.commit()


def rows(database, table):
    # The table's name comes from the tests themselves.
    return database.execute(f'SELECT * FROM {table}').fetchall()


def open_upload(tmp_path, data):
    path = tmp_path / 'uploaded.sqlite3'
    path.write_bytes(data)
    return closing(sqlite3.connect(path))


def test_the_uploaded_copy_is_a_valid_database_with_the_same_rows(r2, database, clock, tmp_path):
    call_command('backup_db', stdout=io.StringIO())

    assert list(r2.objects) == [FIRST_NAME]
    with open_upload(tmp_path, r2.objects[FIRST_NAME]) as copy:
        assert copy.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert rows(copy, 'core_watch') == [('first watch',)]
        assert rows(copy, 'auth_user') == [('made-up-user', 'made-up-scrambled-password')]


def test_the_login_sessions_are_not_in_the_upload_and_stay_in_the_database(r2, database, clock, tmp_path):
    call_command('backup_db', stdout=io.StringIO())

    data = r2.objects[FIRST_NAME]
    assert SESSION_KEY.encode() not in data
    with open_upload(tmp_path, data) as copy:
        assert rows(copy, 'django_session') == []
    assert rows(database, 'django_session') == [(SESSION_KEY, 'made-up-session-data')]


def test_no_key_is_in_the_upload(r2, database, clock):
    call_command('backup_db', stdout=io.StringIO())

    for value in KEY_VALUES.values():
        assert value.encode() not in r2.objects[FIRST_NAME]


@pytest.mark.parametrize('setting', KEY_VALUES)
def test_a_copy_that_holds_a_key_is_not_uploaded(r2, database, setting):
    write(database, 'INSERT INTO core_watch VALUES (?)', f'pasted by mistake: {KEY_VALUES[setting]}')

    with pytest.raises(CommandError) as problem:
        call_command('backup_db', stdout=io.StringIO())

    assert r2.objects == {}
    assert setting in str(problem.value)
    assert KEY_VALUES[setting] not in str(problem.value)


def test_after_15_backups_the_newest_14_are_left(r2, database, clock):
    names = []
    for _ in range(15):
        names.append(backups.backup()[0])
        clock.shift(datetime.timedelta(days=1))

    assert sorted(r2.objects) == names[1:]


def test_copies_that_are_not_couchlogs_are_never_deleted(r2, database, clock):
    others = ['photo.jpg', 'couchlog-notes.sqlite3', 'couchlog-2026-01-01.sqlite3', 'other/couchlog-2026-01-01-100000.sqlite3']
    for name in others:
        r2.objects[name] = b'not ours'

    for _ in range(15):
        backups.backup()
        clock.shift(datetime.timedelta(days=1))

    for name in others:
        assert r2.objects[name] == b'not ours'
    assert len(backups.couchlog_copies(r2)) == 14


@pytest.mark.parametrize('setting', backups.R2_SETTINGS)
def test_without_the_settings_nothing_is_uploaded(r2, database, settings, setting):
    setattr(settings, setting, '')
    out = io.StringIO()

    call_command('backup_db', stdout=out)

    assert r2.objects == {}
    assert f'No backup made: {setting} not set' in out.getvalue()


def test_the_local_copy_is_removed_after_the_upload(r2, database, monkeypatch, tmp_path):
    folder = tmp_path / 'temporary'
    folder.mkdir()
    monkeypatch.setattr(tempfile, 'tempdir', str(folder))

    call_command('backup_db', stdout=io.StringIO())

    assert len(r2.objects) == 1
    assert list(folder.iterdir()) == []


def test_after_a_failed_upload_the_local_copy_is_gone_and_no_old_copy_is_deleted(r2, database, clock, monkeypatch, tmp_path):
    folder = tmp_path / 'temporary'
    folder.mkdir()
    monkeypatch.setattr(tempfile, 'tempdir', str(folder))
    for day in range(1, 15):
        r2.objects[f'couchlog-2026-10-{day:02}-100000.sqlite3'] = b'an older copy'
    before = dict(r2.objects)
    r2.upload_problem = EndpointConnectionError(endpoint_url='https://made-up')

    with pytest.raises(CommandError, match='R2 did not work'):
        call_command('backup_db', stdout=io.StringIO())

    assert r2.objects == before
    assert list(folder.iterdir()) == []


def test_a_restore_puts_the_copy_back_and_undo_puts_the_previous_data_back(r2, database, clock):
    name, _ = backups.backup()
    write(database, 'INSERT INTO core_watch VALUES (?)', 'watched after the backup')
    write(database, 'INSERT INTO django_session VALUES (?, ?)', 'later-session', 'data')
    before_restore = rows(database, 'core_watch'), rows(database, 'django_session')

    call_command('restore_db', name, stdout=io.StringIO())

    assert rows(database, 'core_watch') == [('first watch',)]
    assert rows(database, 'django_session') == []
    assert database.execute('PRAGMA journal_mode').fetchone()[0] == 'wal'

    call_command('restore_db', '--undo', stdout=io.StringIO())

    assert (rows(database, 'core_watch'), rows(database, 'django_session')) == before_restore
    assert database.execute('PRAGMA journal_mode').fetchone()[0] == 'wal'
    assert not backups.before_restore_path().exists()


def test_the_database_saved_by_a_restore_is_on_this_machine_and_not_in_the_bucket(r2, database, clock):
    name, _ = backups.backup()

    call_command('restore_db', name, stdout=io.StringIO())

    assert backups.before_restore_path().exists()
    assert list(r2.objects) == [name]


@pytest.mark.parametrize(
    ('name', 'content'),
    [
        ('couchlog-2026-11-01-100000.sqlite3', b'this is not a database'),
        ('couchlog-2026-11-02-100000.sqlite3', b''),
        ('couchlog-2026-11-03-100000.sqlite3', None),
        ('photo.jpg', b'not ours'),
    ],
)
def test_a_bad_copy_changes_nothing(r2, database, name, content):
    if content is not None:
        r2.objects[name] = content
    before = rows(database, 'core_watch'), rows(database, 'django_session')

    with pytest.raises(CommandError):
        call_command('restore_db', name, stdout=io.StringIO())

    assert (rows(database, 'core_watch'), rows(database, 'django_session')) == before
    assert not backups.before_restore_path().exists()


def test_undo_with_no_restore_says_so(database):
    with pytest.raises(CommandError, match='no restore to undo'):
        call_command('restore_db', '--undo', stdout=io.StringIO())


def test_restore_without_a_name_lists_the_copies_newest_first(r2, database):
    r2.objects['couchlog-2026-11-01-100000.sqlite3'] = b''
    r2.objects['couchlog-2026-11-02-100000.sqlite3'] = b''
    r2.objects['photo.jpg'] = b''
    out = io.StringIO()

    call_command('restore_db', stdout=out)

    assert out.getvalue().split() == ['couchlog-2026-11-02-100000.sqlite3', 'couchlog-2026-11-01-100000.sqlite3']


def test_restore_without_the_settings_does_nothing(database):
    before = rows(database, 'core_watch')
    out = io.StringIO()

    call_command('restore_db', FIRST_NAME, stdout=out)

    assert 'Nothing done' in out.getvalue()
    assert rows(database, 'core_watch') == before


def test_the_client_talks_to_the_accounts_own_r2_address(settings):
    settings.R2_ACCOUNT_ID = 'made-up-account'
    settings.R2_ACCESS_KEY_ID = 'made-up-id'
    settings.R2_SECRET_ACCESS_KEY = 'made-up-secret'

    client = backups.r2_client()

    assert client.meta.endpoint_url == 'https://made-up-account.r2.cloudflarestorage.com'
    assert client.meta.region_name == 'auto'
