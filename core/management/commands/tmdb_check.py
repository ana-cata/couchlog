from django.core.management.base import BaseCommand, CommandError

from core import tmdb


class Command(BaseCommand):
    help = 'Make one request to TMDB to check that the key in .env works.'

    def handle(self, *args, **options):
        try:
            configuration = tmdb.get_configuration()
        except tmdb.TmdbError as error:
            raise CommandError(str(error)) from None
        image_url = configuration['images']['secure_base_url']
        self.stdout.write(self.style.SUCCESS(f'TMDB key works. Poster images live at {image_url}'))
