from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from core import tmdb
from core.episodes import refresh_episodes
from core.models import Title, ToWatchItem, Watch


class Command(BaseCommand):
    help = (
        'Ask TMDB again for every series that is on someone\'s To Watch list or has a watched episode, '
        'and save its new episodes, air dates and status (ended or still running).'
    )

    def handle(self, *args, **options):
        # Series nobody follows are left alone, so TMDB is not asked about them for nothing.
        followed = Q(id__in=ToWatchItem.objects.filter(removed_at=None).values('title')) | Q(
            id__in=Watch.objects.filter(episode__isnull=False).values('title')
        )
        all_series = Title.objects.filter(kind='series').filter(followed).order_by('title')

        done, failed = 0, 0
        for series in all_series:
            before = series.episodes.count()
            try:
                refresh_episodes(series)
            except tmdb.TmdbError as problem:
                failed += 1
                self.stderr.write(f'Could not refresh “{series.title}”: {problem}')
                continue
            done += 1
            new = series.episodes.count() - before
            self.stdout.write(f'“{series.title}”: {series.status or "status unknown"}, {new} new episode{"" if new == 1 else "s"}')

        self.stdout.write(self.style.SUCCESS(f'Refreshed {done} series.'))
        if failed:
            # A non-zero exit, so whatever runs this on a schedule can tell something went wrong.
            raise CommandError(f'{failed} series could not be refreshed. Run the command again later.')
