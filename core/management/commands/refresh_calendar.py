from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from core import tmdb, tvmaze
from core.details import refresh_details, stale_titles
from core.episodes import refresh_episodes
from core.models import Title, ToWatchItem, Watch
from core.releases import refresh_movie, refresh_upcoming


class Command(BaseCommand):
    help = (
        'Ask TMDB again for what the calendar shows: every series that is on someone\'s To Watch list or has a '
        'watched episode (new episodes, air dates, status, typical episode runtime), and every movie on someone\'s '
        'To Watch list (their cinema and streaming dates) and every watched movie with no runtime or no genres saved yet. '
        'Every series is also asked about on TVmaze, the second source for upcoming episode dates.'
    )

    def handle(self, *args, **options):
        failed = 0
        # The titles whose dates or episodes were asked from TMDB in this run, so the last step does not ask again.
        refreshed = set()

        # Series and movies nobody follows are only asked about once their details get old (the last step).
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
            refreshed.add(series.id)
            new = series.episodes.count() - before
            line = f'“{series.title}”: {series.status or "status unknown"}, {new} new episode{"" if new == 1 else "s"}'
            try:
                refresh_upcoming(series)
            except tvmaze.TvmazeError as problem:
                # TMDB's part is saved. The upcoming episodes from TVmaze keep what they had.
                failed += 1
                self.stderr.write(f'Could not refresh the upcoming episodes of “{series.title}” from TVmaze: {problem}')
            else:
                more = series.upcoming_episodes.count()
                if more:
                    line += f', {more} upcoming on TVmaze'
            self.stdout.write(line)
        self.stdout.write(self.style.SUCCESS(f'Refreshed {done} series.'))

        # A movie that was watched left the To Watch list, so only movies still waiting are asked about, and movies
        # that were watched and have no runtime or no genres saved yet (saved before they were kept): their time spent
        # needs the runtime, and their title page the genres.
        waiting = Q(id__in=ToWatchItem.objects.filter(removed_at=None).values('title'))
        watched = Q(id__in=Watch.objects.filter(episode=None).values('title'))
        incomplete = watched & (Q(runtime=None) | Q(genres=[]))
        all_movies = Title.objects.filter(kind='movie').filter(waiting | incomplete).order_by('title')
        done = 0
        for movie in all_movies:
            try:
                refresh_movie(movie)
            except tmdb.TmdbError as problem:
                failed += 1
                self.stderr.write(f'Could not refresh “{movie.title}”: {problem}')
                continue
            done += 1
            refreshed.add(movie.id)
            cinema = movie.cinema_at.date().isoformat() if movie.cinema_at else 'no date yet'
            streaming = movie.streaming_at.date().isoformat() if movie.streaming_at else 'no date yet'
            self.stdout.write(f'“{movie.title}”: in cinemas {cinema}, streaming {streaming}')
        self.stdout.write(self.style.SUCCESS(f'Refreshed {done} movie{"" if done == 1 else "s"}.'))

        # TMDB's terms allow keeping its details for at most 6 months, so every saved title, followed or not, is asked
        # about again once its details are older than 5 months: its name, year, poster and summary, and its dates or
        # episodes (unless the steps above just did that). A title TMDB no longer has keeps its saved details (watches
        # point to it) and is asked about again the next day.
        done = 0
        for title in stale_titles():
            try:
                if title.id not in refreshed:
                    if title.kind == 'series':
                        refresh_episodes(title)
                    else:
                        refresh_movie(title)
                refresh_details(title)
            except tmdb.TmdbNotFound:
                self.stdout.write(f'TMDB no longer has “{title.title}”. Its saved details are kept.')
                continue
            except tmdb.TmdbError as problem:
                failed += 1
                self.stderr.write(f'Could not refresh the details of “{title.title}”: {problem}')
                continue
            done += 1
            self.stdout.write(f'“{title.title}”: details refreshed')
        self.stdout.write(self.style.SUCCESS(f'Refreshed the details of {done} title{"" if done == 1 else "s"}.'))

        if failed:
            # A non-zero exit, so whatever runs this on a schedule can tell something went wrong.
            raise CommandError(f'{failed} title{"" if failed == 1 else "s"} could not be refreshed. Run the command again later.')
