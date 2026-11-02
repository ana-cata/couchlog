"""Settings for running in Docker: the database path, the power-cut settings and the static files with debug off.

The settings file is read once when Python starts, so the settings tests start a fresh Python (a subprocess)
with the environment they want. The container itself is checked by hand, not here (docs/deploying.md).
"""

import os
import subprocess
import sys

from django.conf import settings
from django.core.management import call_command

SECRET_KEY = 'made-up-secret-key'


def run_python(code, **environment):
    """Run `code` in a fresh Python that has loaded Couchlog's settings; return the finished process.

    Debug and the secret key are set here (a value in the environment wins over the .env file), so what
    happens does not depend on the .env of whoever runs the tests.
    """
    return subprocess.run(
        [sys.executable, '-c', code],
        check=False,
        cwd=settings.BASE_DIR,
        env={
            **os.environ,
            'DJANGO_SETTINGS_MODULE': 'config.settings',
            'DJANGO_DEBUG': 'true',
            'DJANGO_SECRET_KEY': SECRET_KEY,
            **environment,
        },
        capture_output=True,
        text=True,
    )


def test_the_database_path_comes_from_the_setting(tmp_path):
    database = str(tmp_path / 'made-up.sqlite3')

    result = run_python(
        'from django.conf import settings; print(settings.DATABASES["default"]["NAME"])',
        DJANGO_DB_PATH=database,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == database


def test_the_database_is_db_sqlite3_in_the_project_folder_when_the_setting_is_not_used():
    # An empty value counts as not set. It also keeps a DJANGO_DB_PATH in the real .env from reaching this test.
    result = run_python(
        'from django.conf import settings; print(settings.DATABASES["default"]["NAME"])',
        DJANGO_DB_PATH='',
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(settings.BASE_DIR / 'db.sqlite3')


def test_the_database_is_safe_against_power_cuts(tmp_path):
    # A real database file, because an in-memory one cannot use the write-ahead log.
    result = run_python(
        'import django; django.setup()\n'
        'from django.db import connection\n'
        'cursor = connection.cursor()\n'
        'print(cursor.execute("PRAGMA journal_mode").fetchone()[0])\n'
        'print(cursor.execute("PRAGMA synchronous").fetchone()[0])',
        DJANGO_DB_PATH=str(tmp_path / 'made-up.sqlite3'),
    )

    assert result.returncode == 0, result.stderr
    journal_mode, synchronous = result.stdout.split()
    assert journal_mode == 'wal'
    assert synchronous == '1'  # 1 is SQLite's number for "normal"


def test_debug_off_without_a_secret_key_refuses_to_start():
    result = run_python('import config.settings', DJANGO_DEBUG='false', DJANGO_SECRET_KEY='')

    assert result.returncode != 0
    assert 'DJANGO_SECRET_KEY' in result.stderr


def test_debug_off_with_a_secret_key_starts():
    result = run_python('import config.settings', DJANGO_DEBUG='false', DJANGO_SECRET_KEY=SECRET_KEY)

    assert result.returncode == 0, result.stderr


def test_with_debug_off_the_static_files_are_served_without_a_login(client, settings, tmp_path):
    # What the Dockerfile does at build time: copy every static file into STATIC_ROOT. WhiteNoise serves them from there.
    # The tests always run with debug off, and the test client sends no login.
    settings.STATIC_ROOT = tmp_path
    call_command('collectstatic', interactive=False, verbosity=0)

    for file in ['core/couchlog.css', 'core/pico.min.css', 'core/htmx.min.js', 'core/logo-couchlog.svg']:
        response = client.get(f'/static/{file}')

        assert response.status_code == 200, file
        assert b''.join(response.streaming_content) == (tmp_path / file).read_bytes(), file
        # Unlike a page (core/middleware.py, NeverCacheMiddleware), a static file may be kept by the browser.
        assert 'no-store' not in response.get('Cache-Control', ''), file
