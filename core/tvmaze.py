"""Server-side calls to TVmaze, the second source for the dates of upcoming episodes. TVmaze needs no key."""

import datetime

import httpx

TVMAZE_BASE_URL = 'https://api.tvmaze.com'


class TvmazeError(Exception):
    """A TVmaze problem, with a message that is fine to show to the user."""


class TvmazeNotFound(TvmazeError):
    """TVmaze has nothing with that ID."""


def _get(path, query=None):
    try:
        # The lookup answers with a redirect to the show, so redirects are followed.
        response = httpx.get(TVMAZE_BASE_URL + path, params=query, follow_redirects=True, timeout=10)
    except httpx.HTTPError:
        raise TvmazeError('Could not reach TVmaze. Check the internet connection and try again.') from None

    if response.status_code == 404:
        raise TvmazeNotFound('TVmaze does not have that series.')
    if response.status_code != 200:
        # 429 is "too many questions": TVmaze allows 20 every 10 seconds.
        raise TvmazeError(f'TVmaze answered with an error (code {response.status_code}). Try again later.')
    return response.json()


def _day(text):
    """A TVmaze date such as 2026-12-08 as a date, or None when TVmaze has none (or it makes no sense)."""
    try:
        return datetime.date.fromisoformat(text or '')
    except ValueError:
        return None


def find_show_id(imdb_id):
    """TVmaze's own id for the series with this IMDb id, or None when TVmaze does not know it."""
    try:
        return _get('/lookup/shows', {'imdb': imdb_id})['id']
    except TvmazeNotFound:
        return None


def get_upcoming_episodes(show_id, since):
    """The episodes of a TVmaze show that air on or after the day `since`. Nothing is saved.

    Raises `TvmazeNotFound` when TVmaze has no show with that id. Specials are not in TVmaze's list unless asked
    for, and an episode with no number or no air date yet is left out.
    """
    upcoming = []
    for raw in _get(f'/shows/{show_id}/episodes'):
        air_date = _day(raw.get('airdate'))
        if raw.get('season') is None or raw.get('number') is None or air_date is None or air_date < since:
            continue
        upcoming.append({
            'season_number': raw['season'],
            'episode_number': raw['number'],
            'name': raw.get('name') or '',
            'air_date': air_date,
        })
    return upcoming
