import time

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.utils import OperationalError
from django.utils import timezone

# What runs once a day, in this order. One failing does not stop the next.
DAILY_COMMANDS = ['refresh_calendar']

A_DAY = 24 * 60 * 60  # seconds
MIGRATIONS_CHECK_EVERY = 5  # seconds


def migrations_are_applied():
    """True when the database has every migration this code knows about. A database that is still being created or
    is busy with the migrations can answer with an error, and that counts as not yet."""
    try:
        executor = MigrationExecutor(connection)
        return not executor.migration_plan(executor.loader.graph.leaf_nodes())
    except OperationalError:
        return False
    finally:
        connection.close()


def stamp():
    return timezone.now().strftime('%Y-%m-%d %H:%M UTC')


class Command(BaseCommand):
    help = (
        'Run the daily commands straight away and then every 24 hours, for as long as it runs. It first waits until '
        'the migrations are applied. A command that fails is reported in the log and runs again the next day.'
    )

    def handle(self, *args, **options):
        self.wait_for_migrations()
        while True:
            self.run_commands()
            self.stdout.write('Next run in 24 hours.')
            time.sleep(A_DAY)

    def wait_for_migrations(self):
        # The app applies the migrations when its own container starts, and both containers start together.
        if migrations_are_applied():
            return
        self.stdout.write('Waiting for the app to apply the migrations.')
        while True:
            time.sleep(MIGRATIONS_CHECK_EVERY)
            if migrations_are_applied():
                return

    def run_commands(self):
        for name in DAILY_COMMANDS:
            self.stdout.write(f'{stamp()} Starting {name}.')
            try:
                call_command(name, stdout=self.stdout, stderr=self.stderr)
            except Exception as problem:  # noqa: BLE001
                # Anything at all, not only TMDB not answering: this has to be running again tomorrow.
                self.stderr.write(f'{stamp()} {name} failed: {problem}. It runs again in 24 hours.')
            else:
                self.stdout.write(f'{stamp()} Finished {name}.')
        # So the 24 hours of waiting do not keep the database open.
        connection.close()
