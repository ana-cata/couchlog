from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import connection

# Read when this file is loaded, before pytest-django swaps in the temporary database.
REAL_DATABASE = Path(settings.DATABASES['default']['NAME'])


def test_the_real_database_is_the_file_in_the_project_folder():
    assert REAL_DATABASE == settings.BASE_DIR / 'db.sqlite3'


@pytest.mark.django_db
def test_tests_use_a_temporary_database_not_the_real_one():
    real_file_before = REAL_DATABASE.stat().st_mtime_ns if REAL_DATABASE.exists() else None

    User.objects.create_user(username='made-up-user', password='made-up-password')

    # pytest-django swaps in a database that lives in memory, so no file is involved.
    name = str(connection.settings_dict['NAME'])
    assert 'memory' in name
    assert Path(name) != REAL_DATABASE
    # Whatever the test saved never reached the real file.
    real_file_after = REAL_DATABASE.stat().st_mtime_ns if REAL_DATABASE.exists() else None
    assert real_file_after == real_file_before


@pytest.mark.django_db
def test_every_table_change_has_a_migration_file():
    # Fails if a model was changed without running `makemigrations`.
    # check=True makes the command fail instead of passing; dry_run=True writes no file.
    # It reads the migration history from the database, hence the temporary one.
    call_command('makemigrations', check=True, dry_run=True, verbosity=0)
