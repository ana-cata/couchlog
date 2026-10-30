from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from core import tmdb
from core.episodes import refresh_episodes
from core.models import Title, ToWatchItem, Watch
from core.releases import refresh_movie


class Command(BaseCommand):
    help = (
        'Ask TMDB again for what the calendar shows: every series that is on someone\'s To Watch list or has a '
        'watched episode (new episodes, air dates, status), and every movie on someone\'s To Watch list '
        '(their cinema and streaming dates).'
    )

    def handle(self, *args, **options):
        failed = 0

        # Series and movies nobody follows are left alone, so TMDB is not asked about them for nothing.
        followed = Q(id__in=ToWatchItem.objects.filter(removed_at=None).values('title')) | Q(
            id__in=Watch.objects.filter(episode__isnull=False).values('title')
        )
        all_series = Title.objects.filter(kind='series').filter(followed).order_by('title')
        done = 0
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

        # A movie that was watched left the To Watch list, so only movies still waiting are asked about.
        all_movies = Title.objects.filter(
            kind='movie', id__in=ToWatchItem.objects.filter(removed_at=None).values('title')
        ).order_by('title')
        done = 0
        for movie in all_movies:
            try:
                refresh_movie(movie)
            except tmdb.TmdbError as problem:
                failed += 1
                self.stderr.write(f'Could not refresh “{movie.title}”: {problem}')
                continue
            done += 1
            cinema = movie.cinema_at.date().isoformat() if movie.cinema_at else 'no date yet'
            streaming = movie.streaming_at.date().isoformat() if movie.streaming_at else 'no date yet'
            self.stdout.write(f'“{movie.title}”: in cinemas {cinema}, streaming {streaming}')
        self.stdout.write(self.style.SUCCESS(f'Refreshed {done} movie{"" if done == 1 else "s"}.'))

        if failed:
            # A non-zero exit, so whatever runs this on a schedule can tell something went wrong.
            raise CommandError(f'{failed} title{"" if failed == 1 else "s"} could not be refreshed. Run the command again later.')
