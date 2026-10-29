from io import StringIO

import httpx
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

CONFIGURATION_URL = 'https://api.themoviedb.org/3/configuration'

# A made-up TMDB answer. The tests never call the real TMDB.
MADE_UP_CONFIGURATION = {'images': {'secure_base_url': 'https://images.example/t/p/'}}


def run_tmdb_check():
    out = StringIO()
    call_command('tmdb_check', stdout=out)
    return out.getvalue()


def test_works_with_an_api_key(settings, respx_mock):
    settings.TMDB_API_KEY = 'made-up-key'
    route = respx_mock.get(CONFIGURATION_URL).respond(json=MADE_UP_CONFIGURATION)

    output = run_tmdb_check()

    assert 'TMDB key works' in output
    assert 'https://images.example/t/p/' in output
    assert route.calls.last.request.url.params['api_key'] == 'made-up-key'


def test_works_with_a_read_access_token(settings, respx_mock):
    settings.TMDB_API_KEY = 'eyJmade-up-token'
    route = respx_mock.get(CONFIGURATION_URL).respond(json=MADE_UP_CONFIGURATION)

    run_tmdb_check()

    request = route.calls.last.request
    assert request.headers['Authorization'] == 'Bearer eyJmade-up-token'
    assert 'api_key' not in request.url.params


def test_says_so_when_there_is_no_key(settings, respx_mock):
    settings.TMDB_API_KEY = ''

    with pytest.raises(CommandError, match='TMDB_API_KEY is not set'):
        run_tmdb_check()

    assert respx_mock.calls.call_count == 0


def test_says_so_when_tmdb_rejects_the_key(settings, respx_mock):
    settings.TMDB_API_KEY = 'wrong-key'
    respx_mock.get(CONFIGURATION_URL).respond(401, json={'status_message': 'Invalid API key'})

    with pytest.raises(CommandError, match='did not accept the key'):
        run_tmdb_check()


def test_says_so_when_tmdb_does_not_answer(settings, respx_mock):
    settings.TMDB_API_KEY = 'made-up-key'
    respx_mock.get(CONFIGURATION_URL).mock(side_effect=httpx.ConnectError('no network'))

    with pytest.raises(CommandError, match='Could not reach TMDB'):
        run_tmdb_check()
