"""Server-side calls to TMDB. The key is read from the settings and never leaves the server."""

import httpx
from django.conf import settings

TMDB_BASE_URL = 'https://api.themoviedb.org/3'
# Posters are public pictures: the browser loads them from here directly, with no key.
IMAGE_BASE_URL = 'https://image.tmdb.org/t/p/w342'


class TmdbError(Exception):
    """A TMDB problem, with a message that is fine to show to the user."""


class TmdbNotFound(TmdbError):
    """TMDB has no title with that ID."""


def _get(path, query=None):
    api_key = settings.TMDB_API_KEY
    if not api_key:
        raise TmdbError('TMDB_API_KEY is not set. Put your TMDB key in the .env file (see .env.example).')

    # TMDB hands out two kinds of credential. The long "read access token" (starts with eyJ)
    # goes in a header; the short "API key" goes in the query string.
    headers = {}
    params = dict(query or {})
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
    if response.status_code == 404:
        raise TmdbNotFound('TMDB does not have that title.')
    if response.status_code != 200:
        raise TmdbError(f'TMDB answered with an error (code {response.status_code}). Try again later.')
    return response.json()


def get_configuration():
    """TMDB's settings (for example where the poster images live). A cheap call to test the key."""
    return _get('/configuration')


def _title_from(raw, kind):
    """The few fields we show, from one TMDB movie or series. `kind` is 'movie' or 'series'."""
    if kind == 'movie':
        name, date = raw.get('title'), raw.get('release_date')
    else:
        name, date = raw.get('name'), raw.get('first_air_date')
    poster_path = raw.get('poster_path')
    return {
        'kind': kind,
        'tmdb_id': raw['id'],
        'title': name or '',
        # TMDB dates look like 2010-07-16, or are empty. The year is used as given.
        'year': (date or '')[:4],
        'poster_url': f'{IMAGE_BASE_URL}{poster_path}' if poster_path else '',
        'overview': raw.get('overview') or '',
    }


def search(query):
    """Movies and series that match the text. Nothing is saved. Only the first page of results."""
    kinds = {'movie': 'movie', 'tv': 'series'}  # TMDB also returns people, which we skip
    data = _get('/search/multi', {'query': query})
    return [
        _title_from(raw, kinds[raw['media_type']])
        for raw in data.get('results', [])
        if raw.get('media_type') in kinds
    ]


def get_title(kind, tmdb_id):
    """One movie or series from TMDB. Nothing is saved."""
    path = f'/movie/{tmdb_id}' if kind == 'movie' else f'/tv/{tmdb_id}'
    return _title_from(_get(path), kind)
