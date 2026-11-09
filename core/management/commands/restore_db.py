from django.core.management.base import BaseCommand

from core import backups


class Command(BaseCommand):
    help = 'Without a name: list the copies in Cloudflare R2. With a name: put that copy in place of the database.'

    def add_arguments(self, parser):
        parser.add_argument('name', nargs='?', help='The copy to restore, as the list shows it.')
        parser.add_argument('--undo', action='store_true', help='Put back the database from before the last restore.')

    def handle(self, *args, name, undo, **options):
        if undo:
            backups.undo_restore()
            self.stdout.write('The restore is undone: the database is back as it was before it.')
            return

        missing = backups.missing_r2_settings()
        if missing:
            self.stdout.write(f'Nothing done: {", ".join(missing)} not set in .env.')
            return

        if name:
            backups.restore(name)
            self.stdout.write(f'Restored {name}. To go back: restore_db --undo')
            return

        names = backups.list_copies()
        if not names:
            self.stdout.write('There are no copies in the bucket yet.')
        for copy_name in reversed(names):
            self.stdout.write(copy_name)
