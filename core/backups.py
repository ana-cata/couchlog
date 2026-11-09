"""Copies of the database in Cloudflare R2 (private online storage that works like Amazon S3).

The commands backup_db and restore_db use this. A copy that leaves the Pi holds no keys: the keys live in .env, the
login sessions are erased from the copy, and the copy is searched for the keys before it is sent.
"""

import re
import sqlite3
import tempfile
from contextlib import closing, contextmanager
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.core.management.base import CommandError
from django.utils import timezone

KEEP = 14

# R2's free plan has 10 GB, and Cloudflare has no hard spending limit. Couchlog stops at half of that, so it stays free.
STORAGE_LIMIT = 5_000_000_000  # bytes

# The date and time in the name make the alphabetical order the same as the order in time.
NAME_FORMAT = 'couchlog-%Y-%m-%d-%H%M%S.sqlite3'
IS_COUCHLOG_COPY = re.compile(r'couchlog-\d{4}-\d{2}-\d{2}-\d{6}\.sqlite3')

R2_SETTINGS = ('R2_ACCOUNT_ID', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_BUCKET')
KEY_SETTINGS = ('TMDB_API_KEY', 'SECRET_KEY', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY')

# How long to wait, in seconds, if the app is writing to the database at that moment.
WAIT_FOR_THE_APP = 30


def missing_r2_settings():
    return [name for name in R2_SETTINGS if not getattr(settings, name)]


def r2_client():
    return boto3.client(
        's3',
        endpoint_url=f'https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com',
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        region_name='auto',
        # R2 does not accept the extra checksums that newer versions of boto3 add by themselves.
        config=Config(request_checksum_calculation='when_required', response_checksum_validation='when_required'),
    )


@contextmanager
def r2_errors():
    """Turns a problem with R2 into one readable line, for the log or the terminal."""
    try:
        yield
    except (BotoCoreError, ClientError) as problem:
        raise CommandError(f'Cloudflare R2 did not work: {problem}') from problem


def database_path():
    return Path(settings.DATABASES['default']['NAME'])


def before_restore_path():
    """Where a restore keeps the database it replaces. It stays on this machine and is never uploaded."""
    database = database_path()
    return database.with_name(f'{database.stem}-before-restore{database.suffix}')


def copy_database(source_path, target_path):
    """Copy with SQLite's backup command, which is safe while the app is writing, unlike a plain file copy."""
    with (
        closing(sqlite3.connect(source_path, timeout=WAIT_FOR_THE_APP)) as source,
        closing(sqlite3.connect(target_path, timeout=WAIT_FOR_THE_APP)) as target,
    ):
        source.backup(target)


def make_clean_copy(path):
    """A copy of the database in one file, without the login sessions. VACUUM rebuilds the file, because erased rows
    otherwise stay readable in it."""
    copy_database(database_path(), path)
    with closing(sqlite3.connect(path)) as copy:
        copy.execute('PRAGMA journal_mode=DELETE')
        copy.execute(f'DELETE FROM {Session._meta.db_table}')
        copy.commit()
        copy.execute('VACUUM')


def refuse_if_it_holds_a_key(data):
    """The last check before the copy leaves. The message names the setting, never its value."""
    for name in KEY_SETTINGS:
        value = getattr(settings, name)
        if value and value.encode() in data:
            raise CommandError(f'Nothing was uploaded: the copy of the database contains the value of {name}.')


def couchlog_copies(client):
    """Couchlog's copies in the bucket, oldest first, each with its Key (name) and Size. Anything else is not ours."""
    listing = client.list_objects_v2(Bucket=settings.R2_BUCKET, Prefix='couchlog-')
    copies = [item for item in listing.get('Contents', []) if IS_COUCHLOG_COPY.fullmatch(item['Key'])]
    return sorted(copies, key=lambda item: item['Key'])


def refuse_if_over_the_limit(copies, new_size):
    if sum(item['Size'] for item in copies) + new_size > STORAGE_LIMIT:
        raise CommandError('Nothing was uploaded: the copies in R2 would take more than 5 GB, the limit that keeps it free.')


def delete_oldest(client, names):
    """`names` is every copy, oldest first. Returns the ones it deleted."""
    oldest = names[:-KEEP]
    for name in oldest:
        client.delete_object(Bucket=settings.R2_BUCKET, Key=name)
    return oldest


def backup():
    """Upload a clean copy of the database and keep the newest copies. Returns the new name and the deleted names."""
    name = timezone.now().strftime(NAME_FORMAT)
    # The folder and the copy in it are removed when this block ends, also after a problem.
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / name
        make_clean_copy(path)
        data = path.read_bytes()
    refuse_if_it_holds_a_key(data)
    with r2_errors():
        client = r2_client()
        # One list and one upload per backup. Cloudflare counts both, and deleting is free.
        copies = couchlog_copies(client)
        refuse_if_over_the_limit(copies, len(data))
        # Standard, whatever the bucket's own setting says: the free plan does not cover Infrequent Access.
        client.put_object(Bucket=settings.R2_BUCKET, Key=name, Body=data, StorageClass='STANDARD')
        return name, delete_oldest(client, sorted({item['Key'] for item in copies} | {name}))


def list_copies():
    with r2_errors():
        return [item['Key'] for item in couchlog_copies(r2_client())]


def check_is_couchlog_database(path, name):
    try:
        with closing(sqlite3.connect(path)) as copy:
            verdict = copy.execute('PRAGMA integrity_check').fetchone()[0]
            copy.execute(f'SELECT 1 FROM {User._meta.db_table} LIMIT 1')
    except sqlite3.DatabaseError as problem:
        raise CommandError(f'{name} is not a working Couchlog database, so nothing was changed.') from problem
    if verdict != 'ok':
        raise CommandError(f'{name} is damaged, so nothing was changed.')


def restore(name):
    """Put a copy from the bucket in place of the database, after saving the current one so this can be undone."""
    if not IS_COUCHLOG_COPY.fullmatch(name):
        raise CommandError(f'{name} is not the name of a Couchlog copy. Run restore_db without a name to see them.')
    with tempfile.TemporaryDirectory() as folder:
        downloaded = Path(folder) / name
        with r2_errors():
            data = r2_client().get_object(Bucket=settings.R2_BUCKET, Key=name)['Body'].read()
        downloaded.write_bytes(data)
        check_is_couchlog_database(downloaded, name)

        saved = before_restore_path()
        saved.unlink(missing_ok=True)
        copy_database(database_path(), saved)
        copy_database(downloaded, database_path())


def undo_restore():
    saved = before_restore_path()
    if not saved.exists():
        raise CommandError('There is no restore to undo.')
    copy_database(saved, database_path())
    saved.unlink()
