from django.core.management.base import BaseCommand

from core import backups


class Command(BaseCommand):
    help = (
        'Upload a copy of the database to Cloudflare R2 and keep the newest 14 copies. Without the R2 settings in '
        '.env it says so and does nothing.'
    )

    def handle(self, *args, **options):
        missing = backups.missing_r2_settings()
        if missing:
            self.stdout.write(f'No backup made: {", ".join(missing)} not set in .env.')
            return
        name, deleted = backups.backup()
        self.stdout.write(f'Uploaded {name}.')
        for old_name in deleted:
            self.stdout.write(f'Deleted the old copy {old_name}.')
