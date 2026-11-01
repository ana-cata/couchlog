"""Server-side calls to TMDB. The key is read from the settings and never leaves the server."""

import datetime

import httpx
from django.conf import settings

TMDB_BASE_URL = 'https://api.themoviedb.org/3'
# Posters are public pictures: the browser loads them from here directly, with no key.
IMAGE_BASE_URL = 'https://image.tmdb.org/t/p/w342'
# Banners (the wide pictures, shown in the News section) are public too.
BACKDROP_BASE_URL = 'https://image.tmdb.org/t/p/w780'


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


def _backdrop_url(raw):
    """The address of the banner in one TMDB movie or series, or empty when TMDB has none."""
    backdrop_path = raw.get('backdrop_path')
    return f'{BACKDROP_BASE_URL}{backdrop_path}' if backdrop_path else ''


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
        'backdrop_url': _backdrop_url(raw),
        'overview': raw.get('overview') or '',
        # A movie's runtime in minutes. Only a movie's own details have it: not a search result, not a series.
        'runtime': raw.get('runtime') or None,
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


def _day(text):
    """A TMDB date such as 2011-04-17 as a date, or None when TMDB has none (or it makes no sense)."""
    try:
        return datetime.date.fromisoformat(text or '')
    except ValueError:
        return None


def get_series_episodes(tmdb_id):
    """A series' status, IMDb id, banner and every one of its episodes, specials included. Nothing is saved.

    One call gives the status, the IMDb id and the banner and lists the seasons, then there is one call per
    season, so a long series takes a moment.
    """
    series = _get(f'/tv/{tmdb_id}', {'append_to_response': 'external_ids'})
    episodes = []
    for season in series.get('seasons', []):
        number = season['season_number']
        try:
            data = _get(f'/tv/{tmdb_id}/season/{number}')
        except TmdbNotFound:
            continue  # TMDB lists a season it has no details for: skip it, do not lose the others
        for raw in data.get('episodes', []):
            episodes.append({
                'tmdb_id': raw['id'],
                'season_number': raw.get('season_number', number),
                'episode_number': raw['episode_number'],
                'name': raw.get('name') or '',
                'air_date': _day(raw.get('air_date')),
                'runtime': raw.get('runtime') or None,
            })
    return {
        'status': series.get('status') or '',
        'imdb_id': (series.get('external_ids') or {}).get('imdb_id') or '',
        'backdrop_url': _backdrop_url(series),
        'episodes': episodes,
    }


# TMDB's numbers for the kinds of release in a movie's list of release dates: 1 is a premiere (an event, not
# counted), 2 and 3 are in cinemas (limited and wide), 4 is streaming (digital), 5 is a disc, 6 is TV.
CINEMA_RELEASES = (2, 3)
DIGITAL_RELEASE = 4


def get_movie_releases(tmdb_id):
    """The earliest cinema release and the earliest streaming (digital) release of a movie in any country, and its
    banner and runtime.

    Returns {'cinema': moment or None, 'streaming': moment or None, 'backdrop_url': address or '', 'runtime': minutes
    or None}, None when TMDB lists no such release or has no runtime. A moment looks like 2024-04-15T00:00:00.000Z in
    TMDB's answer (midnight UTC), and so it is here. One call gives it all: the release dates are asked along with
    the movie itself. Nothing is saved.
    """
    data = _get(f'/movie/{tmdb_id}', {'append_to_response': 'release_dates'})
    earliest = {
        'cinema': None,
        'streaming': None,
        'backdrop_url': _backdrop_url(data),
        'runtime': data.get('runtime') or None,
    }
    for country in (data.get('release_dates') or {}).get('results', []):
        for release in country.get('release_dates', []):
            kind = release.get('type')
            if kind in CINEMA_RELEASES:
                name = 'cinema'
            elif kind == DIGITAL_RELEASE:
                name = 'streaming'
            else:
                continue
            try:
                moment = datetime.datetime.fromisoformat(release.get('release_date') or '')
            except ValueError:
                continue  # an entry with no date, or one that makes no sense: skip it, keep the others
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=datetime.UTC)
            if earliest[name] is None or moment < earliest[name]:
                earliest[name] = moment
    return earliest


def get_title(kind, tmdb_id):
    """One movie or series from TMDB. Nothing is saved."""
    path = f'/movie/{tmdb_id}' if kind == 'movie' else f'/tv/{tmdb_id}'
    return _title_from(_get(path), kind)
