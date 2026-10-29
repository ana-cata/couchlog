"""Server-side calls to TMDB. The key is read from the settings and never leaves the server."""

import httpx
from django.conf import settings

TMDB_BASE_URL = 'https://api.themoviedb.org/3'


class TmdbError(Exception):
    """A TMDB problem, with a message that is fine to show to the user."""


def _get(path):
    api_key = settings.TMDB_API_KEY
    if not api_key:
        raise TmdbError('TMDB_API_KEY is not set. Put your TMDB key in the .env file (see .env.example).')

    # TMDB hands out two kinds of credential. The long "read access token" (starts with eyJ)
    # goes in a header; the short "API key" goes in the query string.
    headers = {}
    params = {}
    if api_key.startswith('eyJ'):
        headers['Authorization'] = f'Bearer {api_key}'
    else:
        params['api_key'] = api_key

    try:
        response = httpx.get(TMDB_BASE_URL + path, headers=headers, params=params, timeout=10)
    except httpx.HTTPError:
        raise TmdbError('Could not reach TMDB. Check the internet connection and try again.') from None

    if response.status_code == 401:
        raise TmdbError('TMDB did not accept the key. Check TMDB_API_KEY in the .env file.')
    if response.status_code != 200:
        raise TmdbError(f'TMDB answered with an error (code {response.status_code}). Try again later.')
    return response.json()


def get_configuration():
    """TMDB's settings (for example where the poster images live). A cheap call to test the key."""
    return _get('/configuration')
