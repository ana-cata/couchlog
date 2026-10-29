import httpx
import pytest
from django.contrib.auth.models import User

from core.models import Profile

SEARCH_URL = 'https://api.themoviedb.org/3/search/multi'
MOVIE_URL = 'https://api.themoviedb.org/3/movie/603'
SERIES_URL = 'https://api.themoviedb.org/3/tv/1399'

# Made-up TMDB answers. The tests never call the real TMDB.
MADE_UP_MOVIE = {
    'media_type': 'movie',
    'id': 603,
    'title': 'Made-up Movie',
    'release_date': '1999-03-31',
    'poster_path': '/made-up-movie.jpg',
    'overview': 'A made-up story about a movie.',
}
MADE_UP_SERIES = {
    'media_type': 'tv',
    'id': 1399,
    'name': 'Made-up Series',
    'first_air_date': '2011-04-17',
    'poster_path': '/made-up-series.jpg',
    'overview': 'A made-up story about a series.',
}
MADE_UP_PERSON = {'media_type': 'person', 'id': 7, 'name': 'Made-up Actor', 'profile_path': '/actor.jpg'}


@pytest.fixture(autouse=True)
def tmdb_key(settings):
    settings.TMDB_API_KEY = 'made-up-secret-key'


@pytest.fixture
def logged_in_client(client, db):
    user = User.objects.create_user(username='made-up-user', password='made-up-password')
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    client.force_login(user)
    return client


def made_up_search(respx_mock, results):
    return respx_mock.get(SEARCH_URL).respond(json={'page': 1, 'results': results})


def test_shows_movies_and_series_and_skips_people(logged_in_client, respx_mock):
    route = made_up_search(respx_mock, [MADE_UP_MOVIE, MADE_UP_PERSON, MADE_UP_SERIES])

    page = logged_in_client.get('/search/', {'q': 'made-up'}).content.decode()

    assert route.calls.last.request.url.params['query'] == 'made-up'
    assert 'Made-up Movie' in page
    assert '1999 · Movie' in page
    assert 'https://image.tmdb.org/t/p/w185/made-up-movie.jpg' in page
    assert 'Made-up Series' in page
    assert '2011 · Series' in page
    assert 'Made-up Actor' not in page
    # Each result opens its own page.
    assert 'href="/movie/603/"' in page
    assert 'href="/series/1399/"' in page


def test_a_result_without_poster_or_date_still_shows(logged_in_client, respx_mock):
    bare_movie = {'media_type': 'movie', 'id': 5, 'title': 'Bare Movie', 'poster_path': None, 'release_date': ''}
    made_up_search(respx_mock, [bare_movie])

    page = logged_in_client.get('/search/', {'q': 'bare'}).content.decode()

    assert 'Bare Movie' in page
    assert 'No poster' in page
    assert 'Year unknown' in page


def test_says_so_when_nothing_matches(logged_in_client, respx_mock):
    made_up_search(respx_mock, [])

    page = logged_in_client.get('/search/', {'q': 'zzzz'}).content.decode()

    assert 'No movies or series match' in page


@pytest.mark.parametrize('query', ['', '   '])
def test_an_empty_search_does_not_call_tmdb(logged_in_client, respx_mock, query):
    response = logged_in_client.get('/search/', {'q': query})

    assert response.status_code == 200
    assert respx_mock.calls.call_count == 0


def test_a_tmdb_failure_shows_a_friendly_message(logged_in_client, respx_mock):
    respx_mock.get(SEARCH_URL).mock(side_effect=httpx.ConnectError('no network'))

    response = logged_in_client.get('/search/', {'q': 'anything'})

    assert response.status_code == 200
    assert 'Could not reach TMDB' in response.content.decode()


def test_the_tmdb_key_never_reaches_the_browser(logged_in_client, respx_mock):
    made_up_search(respx_mock, [MADE_UP_MOVIE])

    response = logged_in_client.get('/search/', {'q': 'made-up'})

    assert 'made-up-secret-key' not in response.content.decode()
    assert 'made-up-secret-key' not in str(response.headers)


def test_the_search_page_updates_as_you_type(logged_in_client):
    page = logged_in_client.get('/search/').content.decode()

    # htmx asks for results shortly after typing stops, instead of on every key.
    assert 'hx-get="/search/"' in page
    assert 'delay:400ms' in page


def test_a_live_update_gets_only_the_results(logged_in_client, respx_mock):
    made_up_search(respx_mock, [MADE_UP_MOVIE])

    response = logged_in_client.get('/search/', {'q': 'made-up'}, headers={'HX-Request': 'true'})

    body = response.content.decode()
    assert 'Made-up Movie' in body
    assert '<html' not in body
    # Caches must not hand this fragment out for a normal page load of the same address.
    assert 'HX-Request' in response['Vary']


def test_restoring_a_page_from_htmx_history_gets_the_whole_page(logged_in_client, respx_mock):
    made_up_search(respx_mock, [MADE_UP_MOVIE])

    response = logged_in_client.get(
        '/search/', {'q': 'made-up'}, headers={'HX-Request': 'true', 'HX-History-Restore-Request': 'true'}
    )

    assert '<html' in response.content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize('url', ['/search/', '/search/?q=made-up', '/movie/603/', '/series/1399/'])
def test_these_pages_are_closed_when_logged_out(client, respx_mock, url):
    response = client.get(url)

    assert response.status_code == 302
    assert response['Location'].startswith('/login/')
    assert respx_mock.calls.call_count == 0


def test_the_movie_page_shows_the_movie(logged_in_client, respx_mock):
    route = respx_mock.get(MOVIE_URL).respond(json=MADE_UP_MOVIE)

    response = logged_in_client.get('/movie/603/')

    page = response.content.decode()
    assert route.called
    assert 'Made-up Movie' in page
    assert '1999 · Movie' in page
    assert 'A made-up story about a movie.' in page
    assert 'https://image.tmdb.org/t/p/w342/made-up-movie.jpg' in page


def test_the_series_page_shows_the_series(logged_in_client, respx_mock):
    respx_mock.get(SERIES_URL).respond(json=MADE_UP_SERIES)

    page = logged_in_client.get('/series/1399/').content.decode()

    assert 'Made-up Series' in page
    assert '2011 · Series' in page
    assert 'A made-up story about a series.' in page


def test_a_title_tmdb_does_not_have_is_not_found(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_URL).respond(404, json={'status_message': 'The resource could not be found.'})

    assert logged_in_client.get('/movie/603/').status_code == 404


def test_a_tmdb_failure_on_a_title_page_shows_a_friendly_message(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_URL).respond(500)

    response = logged_in_client.get('/movie/603/')

    assert response.status_code == 200
    assert 'TMDB answered with an error' in response.content.decode()


def test_only_movie_and_series_addresses_exist(logged_in_client, respx_mock):
    assert logged_in_client.get('/person/603/').status_code == 404
    assert respx_mock.calls.call_count == 0
