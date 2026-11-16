import pytest


@pytest.fixture(autouse=True)
def fast_password_hasher(settings):
    # Django hashes passwords slowly on purpose (about 0.4 seconds each), and almost every test creates a user
    # with a password. A fast hasher makes the tests much quicker. It only applies while tests run: the real
    # app keeps its strong hashing. The login tests still check that a right password logs in and a wrong one does not.
    settings.PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']


@pytest.fixture(autouse=True)
def no_real_r2(settings):
    # Whatever is in the .env of whoever runs the tests, no test can reach the real backup storage.
    settings.R2_ACCOUNT_ID = ''
    settings.R2_ACCESS_KEY_ID = ''
    settings.R2_SECRET_ACCESS_KEY = ''
    settings.R2_BUCKET = ''


@pytest.fixture(autouse=True)
def no_demo_mode(settings):
    # Whatever is in the .env of whoever runs the tests, the app is the real one. The demo tests turn it on themselves.
    settings.DEMO_MODE = False


@pytest.fixture(autouse=True)
def no_streaming_services_in_the_browser(request, monkeypatch):
    # A title's page loads its "Where to watch" line from the browser, which asks TMDB. In a real-browser test that
    # answer is "none found", so no browser test reaches the real TMDB. test_where_to_watch.py tests the line itself.
    if 'live_server' in request.fixturenames:
        from core import tmdb

        monkeypatch.setattr(tmdb, 'get_watch_providers', lambda kind, tmdb_id, country: None)


@pytest.fixture(autouse=True)
def tmdb_seasons_asked_together(request):
    # The tests describe a series' seasons one by one, as TMDB's season pages (`/tv/<id>/season/<n>`). The app asks
    # for up to 20 seasons in one call, added to the series' answer (`/tv/<id>?append_to_response=season/1,...`, see
    # `get_series_episodes`). This builds that answer from the test's own season pages, so each test keeps saying
    # what each season holds. A season page that answers anything but 200 is left out, as TMDB leaves out a season it
    # has no details for. test_series_speed.py checks the real calls.
    if 'respx_mock' not in request.fixturenames:
        yield
        return
    import httpx

    respx_mock = request.getfixturevalue('respx_mock')

    def answer(asked):
        parts = [part for part in asked.url.params.get('append_to_response', '').split(',') if part.startswith('season/')]
        if not parts:
            return None  # not a call for seasons: the test's own route for the series answers it
        series_url = str(asked.url.copy_with(query=None))
        combined = {}
        for part in parts:
            page = respx_mock.resolve(httpx.Request('GET', f'{series_url}/{part}')).response
            respx_mock.calls.pop()  # a made-up season page is not a call to TMDB: only the combined call counts
            if page.status_code == 200:
                combined[part] = page.json()
        return httpx.Response(200, json=combined)

    respx_mock.route(name='tmdb seasons asked together', method='GET', url__regex=r'^https://api\.themoviedb\.org/3/tv/\d+(\?|$)').mock(
        side_effect=answer
    )
    yield
    # It is only there to help: a test that never asks for seasons does not have to call it.
    respx_mock.pop('tmdb seasons asked together', None)
