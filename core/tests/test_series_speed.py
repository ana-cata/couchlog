"""Opening a series for the first time is quick: TMDB sends up to 20 seasons in one answer, so a series takes a couple
of calls instead of one call per season. These tests look at the real calls, so they turn off the helper in
conftest.py that builds the combined answer from season pages."""

import datetime

import httpx
import pytest
import time_machine
from django.contrib.auth.models import User
from django.test import Client

from core import tmdb
from core.models import Episode, Profile, Title

SERIES_URL = 'https://api.themoviedb.org/3/tv/1399'
NOW = datetime.datetime(2026, 11, 16, 20, 0, tzinfo=datetime.UTC)


def made_up_series(numbers):
    """TMDB's answer for the series itself, listing the seasons with these numbers (0 is the specials)."""
    return {
        'id': 1399,
        'name': 'Made-up Series',
        'first_air_date': '2023-04-17',
        'overview': 'A made-up story.',
        'status': 'Returning Series',
        'external_ids': {'imdb_id': 'tt0000001'},
        'seasons': [{'season_number': number} for number in numbers],
    }


def made_up_season(number):
    """A season with two episodes, with ids that tell the season apart."""
    return {
        'season_number': number,
        'episodes': [
            {'id': number * 100 + episode, 'season_number': number, 'episode_number': episode,
             'name': f'S{number}E{episode}', 'air_date': '2023-04-17', 'runtime': 50}
            for episode in (1, 2)
        ],
    }


def tmdb_answers(numbers, missing=()):
    """A side effect for /tv/1399: the series itself, or the seasons it is asked for (all but `missing`)."""

    def answer(request):
        asked = request.url.params['append_to_response']
        if asked == 'external_ids':
            return httpx.Response(200, json=made_up_series(numbers))
        parts = asked.split(',')
        return httpx.Response(200, json={
            part: made_up_season(int(part.split('/')[1])) for part in parts if int(part.split('/')[1]) not in missing
        })

    return answer


@pytest.fixture(autouse=True)
def tmdb_key(settings):
    settings.TMDB_API_KEY = 'made-up-secret-key'


@pytest.fixture(autouse=True)
def clock():
    with time_machine.travel(NOW, tick=False) as traveller:
        yield traveller


@pytest.fixture
def series_route(respx_mock):
    respx_mock.pop('tmdb seasons asked together')  # these tests check the real calls
    return respx_mock.get(SERIES_URL)


def seasons_asked(route):
    """What each call for seasons asked for, like ['season/0,season/1'], in order."""
    asked = [call.request.url.params['append_to_response'] for call in route.calls]
    return [part for part in asked if part != 'external_ids']


def test_a_series_with_a_few_seasons_takes_two_calls(series_route):
    series_route.mock(side_effect=tmdb_answers([0, 1, 2]))

    details = tmdb.get_series_episodes(1399)

    assert series_route.call_count == 2  # the series, then all its seasons at once
    assert seasons_asked(series_route) == ['season/0,season/1,season/2']
    assert [(episode['season_number'], episode['episode_number']) for episode in details['episodes']] == [
        (0, 1), (0, 2), (1, 1), (1, 2), (2, 1), (2, 2)
    ]
    assert details['status'] == 'Returning Series' and details['imdb_id'] == 'tt0000001'


def test_a_long_series_asks_for_twenty_seasons_at_a_time(series_route):
    series_route.mock(side_effect=tmdb_answers(list(range(1, 26))))

    details = tmdb.get_series_episodes(1399)

    asked = seasons_asked(series_route)
    assert series_route.call_count == 3  # the series, seasons 1 to 20, seasons 21 to 25
    assert asked[0] == ','.join(f'season/{number}' for number in range(1, 21))
    assert asked[1] == ','.join(f'season/{number}' for number in range(21, 26))
    assert len(details['episodes']) == 25 * 2


def test_a_season_tmdb_has_no_details_for_is_skipped_and_the_others_are_kept(series_route):
    series_route.mock(side_effect=tmdb_answers([1, 2, 3], missing={2}))

    details = tmdb.get_series_episodes(1399)

    assert sorted({episode['season_number'] for episode in details['episodes']}) == [1, 3]


def test_tmdb_failing_on_the_seasons_call_is_a_problem_to_show(series_route):
    answers = iter([httpx.Response(200, json=made_up_series([1, 2])), httpx.Response(500)])
    series_route.mock(side_effect=lambda request: next(answers))

    with pytest.raises(tmdb.TmdbError):
        tmdb.get_series_episodes(1399)


def test_opening_a_series_for_the_first_time_takes_three_calls_whatever_its_seasons(db, series_route):
    # The details to save it, the series, then its 8 seasons at once (it used to be 1 + 1 + 8 calls).
    numbers = list(range(8))  # the specials (0) and seasons 1 to 7
    user = User.objects.create_user(username='made-up-user', password='made-up-password')
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    client = Client()
    client.force_login(user)

    def answer(request):
        if 'append_to_response' not in request.url.params:
            return httpx.Response(200, json=made_up_series(numbers))  # the plain details call that saves the title
        return tmdb_answers(numbers)(request)

    series_route.mock(side_effect=answer)

    response = client.get('/series/1399/')

    assert response.status_code == 200
    assert series_route.call_count == 3
    assert Title.objects.filter(kind='series', tmdb_id=1399).exists()
    assert Episode.objects.filter(title__tmdb_id=1399).count() == 8 * 2
