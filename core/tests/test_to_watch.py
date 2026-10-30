import datetime
import re

import httpx
import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone

from core.models import Profile, Title, ToWatchItem

SEARCH_URL = 'https://api.themoviedb.org/3/search/multi'
MOVIE_URL = 'https://api.themoviedb.org/3/movie/603'
SERIES_URL = 'https://api.themoviedb.org/3/tv/1399'

# Made-up TMDB answers. The tests never call the real TMDB.
MADE_UP_MOVIE = {
    'id': 603,
    'title': 'Made-up Movie',
    'release_date': '1999-03-31',
    'poster_path': '/made-up-movie.jpg',
    'overview': 'A made-up story about a movie.',
}
MADE_UP_SERIES = {
    'id': 1399,
    'name': 'Made-up Series',
    'first_air_date': '2011-04-17',
    'poster_path': '/made-up-series.jpg',
    'overview': 'A made-up story about a series.',
}
SECOND_MOVIE_URL = 'https://api.themoviedb.org/3/movie/604'
MADE_UP_SECOND_MOVIE = {**MADE_UP_MOVIE, 'id': 604, 'title': 'Second Made-up Movie'}

LONG_AGO = datetime.datetime(2020, 1, 15, 9, 30, tzinfo=datetime.UTC)


@pytest.fixture(autouse=True)
def tmdb_key(settings):
    settings.TMDB_API_KEY = 'made-up-secret-key'


@pytest.fixture(autouse=True)
def release_dates(respx_mock):
    """Adding a movie also collects its release dates for the Calendar. Here TMDB has none for any movie."""
    respx_mock.get(url__regex=r'https://api\.themoviedb\.org/3/movie/\d+/release_dates').respond(json={'results': []})


def make_client(name, **options):
    """A browser logged in as a new account (with a time zone chosen, so no redirect to Profile)."""
    user = User.objects.create_user(username=name, password='made-up-password')
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    client = Client(**options)
    client.force_login(user)
    client.user = user
    return client


@pytest.fixture
def logged_in_client(db):
    return make_client('made-up-user')


def add(client, kind='movie', tmdb_id=603, **extra):
    return client.post('/to-watch/add/', {'kind': kind, 'tmdb_id': tmdb_id, **extra})


def remove(client, kind='movie', tmdb_id=603, **extra):
    return client.post('/to-watch/remove/', {'kind': kind, 'tmdb_id': tmdb_id, **extra})


def undo(client, kind='movie', tmdb_id=603, **extra):
    return client.post('/to-watch/undo/', {'kind': kind, 'tmdb_id': tmdb_id, **extra})


SCREEN_OF_KIND = {'movie': '/movies/', 'series': '/series/'}


def to_watch_page(client, kind='movie'):
    """The To Watch tab of the Movies section (or, with kind='series', of the Series section)."""
    return client.get(SCREEN_OF_KIND[kind]).content.decode()


def tiles(page):
    """The addresses of the tiles on a page, in the order shown."""
    return re.findall(r'class="tile" href="([^"]+)"', page)


def snapshot():
    """Everything saved about the To Watch lists, to compare before and after."""
    return list(ToWatchItem.objects.order_by('id').values())


# --- adding ---------------------------------------------------------------------------------


def test_an_added_title_is_still_on_the_list_after_reloading(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_URL).respond(json=MADE_UP_MOVIE)

    response = add(logged_in_client)

    assert response.status_code == 302
    page = to_watch_page(logged_in_client)  # a fresh request, like reloading the page
    assert 'Made-up Movie' in page
    assert '1999 · Movie' in page
    assert 'https://image.tmdb.org/t/p/w342/made-up-movie.jpg' in page
    assert 'class="tile" href="/movie/603/"' in page


def test_adding_saves_the_tmdb_details_in_our_own_table(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_URL).respond(json=MADE_UP_MOVIE)

    add(logged_in_client)

    saved = Title.objects.get()
    assert (saved.kind, saved.tmdb_id) == ('movie', 603)
    assert saved.title == 'Made-up Movie'
    assert saved.year == '1999'
    assert saved.poster_url == 'https://image.tmdb.org/t/p/w342/made-up-movie.jpg'
    assert saved.overview == 'A made-up story about a movie.'
    assert ToWatchItem.objects.get().user == logged_in_client.user


def test_the_list_works_from_the_saved_details_not_from_tmdb(logged_in_client, respx_mock):
    route = respx_mock.get(MOVIE_URL).respond(json=MADE_UP_MOVIE)
    add(logged_in_client)
    assert route.call_count == 1

    # Opening the list asks TMDB for nothing; a second account adding it does not either.
    assert 'Made-up Movie' in to_watch_page(logged_in_client)
    other = make_client('second-user')
    add(other)

    assert route.call_count == 1
    assert Title.objects.count() == 1
    assert ToWatchItem.objects.count() == 2


def test_a_series_is_saved_as_a_series(logged_in_client, respx_mock):
    respx_mock.get(SERIES_URL).respond(json=MADE_UP_SERIES)

    add(logged_in_client, kind='series', tmdb_id=1399)

    page = to_watch_page(logged_in_client, 'series')
    assert 'Made-up Series' in page
    assert '2011 · Series' in page
    assert 'class="tile" href="/series/1399/"' in page


def test_a_movie_and_a_series_with_the_same_tmdb_number_are_different_titles(logged_in_client, respx_mock):
    respx_mock.get('https://api.themoviedb.org/3/movie/5').respond(json={**MADE_UP_MOVIE, 'id': 5})
    respx_mock.get('https://api.themoviedb.org/3/tv/5').respond(json={**MADE_UP_SERIES, 'id': 5})

    add(logged_in_client, kind='movie', tmdb_id=5)
    add(logged_in_client, kind='series', tmdb_id=5)

    assert ToWatchItem.objects.count() == 2


def test_adding_the_same_title_twice_keeps_one_entry(logged_in_client, respx_mock):
    route = respx_mock.get(MOVIE_URL).respond(json=MADE_UP_MOVIE)
    add(logged_in_client)
    first = snapshot()

    response = add(logged_in_client, next='/movies/')
    page = logged_in_client.get(response['Location']).content.decode()

    assert snapshot() == first
    assert Title.objects.count() == 1
    assert route.call_count == 1
    assert 'already on your To Watch list' in page
    assert page.count('class="tile"') == 1


def test_adding_a_title_again_after_removing_it_puts_it_back_as_newly_added(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_URL).respond(json=MADE_UP_MOVIE)
    add(logged_in_client)
    ToWatchItem.objects.update(added_at=LONG_AGO)
    remove(logged_in_client)

    add(logged_in_client)

    item = ToWatchItem.objects.get()  # still one entry, not two
    assert item.removed_at is None
    assert item.added_at > LONG_AGO
    assert 'Made-up Movie' in to_watch_page(logged_in_client)


def test_the_newest_title_comes_first(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_URL).respond(json=MADE_UP_MOVIE)
    respx_mock.get(SECOND_MOVIE_URL).respond(json=MADE_UP_SECOND_MOVIE)
    add(logged_in_client)
    add(logged_in_client, tmdb_id=604)
    ToWatchItem.objects.filter(title__tmdb_id=603).update(added_at=LONG_AGO)

    assert tiles(to_watch_page(logged_in_client)) == ['/movie/604/', '/movie/603/']


def test_a_tmdb_failure_shows_a_friendly_message_and_saves_nothing(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_URL).mock(side_effect=httpx.ConnectError('no network'))

    response = add(logged_in_client)
    page = logged_in_client.get(response['Location']).content.decode()

    assert 'Could not reach TMDB' in page
    assert Title.objects.count() == 0
    assert ToWatchItem.objects.count() == 0


def test_a_title_tmdb_does_not_have_is_not_found_and_saves_nothing(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_URL).respond(404, json={'status_message': 'The resource could not be found.'})

    assert add(logged_in_client).status_code == 404
    assert Title.objects.count() == 0
    assert ToWatchItem.objects.count() == 0


# --- removing and undoing -------------------------------------------------------------------


def test_a_removed_title_leaves_the_list_and_stays_gone_after_reloading(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_URL).respond(json=MADE_UP_MOVIE)
    add(logged_in_client)

    response = remove(logged_in_client)

    assert response.status_code == 302
    page = to_watch_page(logged_in_client)
    assert 'No movies on your To Watch list yet' in page
    assert page.count('class="tile"') == 0


def test_undo_puts_everything_back_as_it_was(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_URL).respond(json=MADE_UP_MOVIE)
    add(logged_in_client)
    ToWatchItem.objects.update(added_at=LONG_AGO)
    before = snapshot()
    tiles_before = tiles(to_watch_page(logged_in_client))

    remove(logged_in_client)
    assert snapshot() != before
    assert tiles(to_watch_page(logged_in_client)) == []
    undo(logged_in_client)

    # The same entry, with its old date added, and the list shows what it showed.
    assert snapshot() == before
    assert ToWatchItem.objects.get().added_at == LONG_AGO
    assert tiles(to_watch_page(logged_in_client)) == tiles_before == ['/movie/603/']
    assert 'Recently removed' not in to_watch_page(logged_in_client)


def test_undo_returns_a_title_to_its_old_place_in_the_list(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_URL).respond(json=MADE_UP_MOVIE)
    respx_mock.get(SECOND_MOVIE_URL).respond(json=MADE_UP_SECOND_MOVIE)
    add(logged_in_client)
    add(logged_in_client, tmdb_id=604)
    ToWatchItem.objects.filter(title__tmdb_id=603).update(added_at=LONG_AGO)

    remove(logged_in_client)
    undo(logged_in_client)

    assert tiles(to_watch_page(logged_in_client)) == ['/movie/604/', '/movie/603/']


def test_a_removed_title_can_be_undone_after_reloading_the_page(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_URL).respond(json=MADE_UP_MOVIE)
    add(logged_in_client)
    remove(logged_in_client)

    page = to_watch_page(logged_in_client)  # reload: the Undo button is still there
    assert 'Recently removed' in page
    assert 'action="/to-watch/undo/"' in page
    undo(logged_in_client)

    assert 'class="tile" href="/movie/603/"' in to_watch_page(logged_in_client)


def test_removing_shows_no_notice_but_the_title_is_offered_for_undo(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_URL).respond(json=MADE_UP_MOVIE)
    add(logged_in_client)
    logged_in_client.get('/movies/')  # the notice about adding has been shown and is gone

    removed = logged_in_client.post('/to-watch/remove/', {'kind': 'movie', 'tmdb_id': 603}, follow=True)

    page = removed.content.decode()
    assert 'Removed “' not in page
    assert 'to undo it' not in page
    assert 'role="status"' not in page  # no notice at all
    assert 'Recently removed' in page
    assert 'You can undo a removal for 10 seconds.' in page


def test_undoing_says_what_happened(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_URL).respond(json=MADE_UP_MOVIE)
    add(logged_in_client)
    remove(logged_in_client)

    restored = logged_in_client.post('/to-watch/undo/', {'kind': 'movie', 'tmdb_id': 603}, follow=True)
    assert 'Put “Made-up Movie” back on your To Watch list.' in restored.content.decode()


def make_removed_title(user, number, removed_ago, kind='movie'):
    title = Title.objects.create(kind=kind, tmdb_id=number, title=f'Made-up Movie {number}')
    return ToWatchItem.objects.create(user=user, title=title, removed_at=timezone.now() - removed_ago)


def test_recently_removed_offers_only_what_was_removed_in_the_last_10_seconds(logged_in_client):
    for number, removed_ago in [
        (1, datetime.timedelta(seconds=2)),
        (2, datetime.timedelta(seconds=6)),
        (3, datetime.timedelta(seconds=20)),
        (4, datetime.timedelta(days=3)),
    ]:
        make_removed_title(logged_in_client.user, number, removed_ago)

    page = to_watch_page(logged_in_client)

    assert page.count('action="/to-watch/undo/"') == 2
    assert 'Made-up Movie 1 ' in page
    assert 'Made-up Movie 2 ' in page
    assert 'Made-up Movie 3 ' not in page
    assert 'Made-up Movie 4 ' not in page


def test_with_nothing_removed_in_the_last_10_seconds_there_is_no_undo_section(logged_in_client):
    make_removed_title(logged_in_client.user, 1, datetime.timedelta(minutes=5))

    page = to_watch_page(logged_in_client)

    assert 'Recently removed' not in page
    assert 'action="/to-watch/undo/"' not in page
    assert 'hx-get' not in page  # nothing to count down, so nothing asks again


def test_the_undo_block_asks_again_just_after_the_oldest_removal_runs_out(logged_in_client):
    make_removed_title(logged_in_client.user, 1, datetime.timedelta(seconds=2))
    make_removed_title(logged_in_client.user, 2, datetime.timedelta(seconds=7))  # runs out first: 3 s left

    page = to_watch_page(logged_in_client)

    assert 'hx-get="/to-watch/removed/?kind=movie"' in page
    delay = int(re.search(r'hx-trigger="load delay:(\d+)s"', page).group(1))
    assert 3 <= delay <= 5  # the 3 seconds left, plus a second of margin


def test_the_removed_block_alone_shows_only_what_can_still_be_undone(logged_in_client):
    make_removed_title(logged_in_client.user, 1, datetime.timedelta(seconds=2))
    make_removed_title(logged_in_client.user, 2, datetime.timedelta(seconds=20))

    response = logged_in_client.get('/to-watch/removed/?kind=movie')

    body = response.content.decode()
    assert '<html' not in body
    assert 'Made-up Movie 1 ' in body
    assert 'Made-up Movie 2 ' not in body
    # Undo brings you back to the To Watch screen, not to this fragment.
    assert 'name="next" value="/movies/"' in body
    # The answer must never be cached, or an expired title could come back on screen.
    assert 'no-cache' in response['Cache-Control']


def test_when_time_is_up_the_removed_block_comes_back_empty_and_stops_asking(logged_in_client):
    make_removed_title(logged_in_client.user, 1, datetime.timedelta(seconds=20))

    body = logged_in_client.get('/to-watch/removed/?kind=movie').content.decode()

    assert 'Recently removed' not in body
    assert 'action="/to-watch/undo/"' not in body
    assert 'hx-get' not in body


def test_the_undo_section_is_above_the_list(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_URL).respond(json=MADE_UP_MOVIE)
    respx_mock.get(SECOND_MOVIE_URL).respond(json=MADE_UP_SECOND_MOVIE)
    add(logged_in_client)
    add(logged_in_client, tmdb_id=604)
    remove(logged_in_client)

    page = to_watch_page(logged_in_client)

    # A long list must not push the Undo button out of sight.
    assert page.index('Recently removed') < page.index('class="tile"')


def test_undo_is_refused_after_the_10_seconds(logged_in_client):
    item = make_removed_title(logged_in_client.user, 603, datetime.timedelta(seconds=20))
    before = snapshot()

    response = undo(logged_in_client)

    assert 'too late to undo' in logged_in_client.get(response['Location']).content.decode()
    assert snapshot() == before
    item.refresh_from_db()
    assert item.removed_at is not None


def test_undo_still_works_just_inside_the_10_seconds(logged_in_client):
    item = make_removed_title(logged_in_client.user, 603, datetime.timedelta(seconds=6))

    undo(logged_in_client)

    item.refresh_from_db()
    assert item.removed_at is None


def test_after_the_10_seconds_a_title_comes_back_by_adding_it_again(logged_in_client):
    item = make_removed_title(logged_in_client.user, 603, datetime.timedelta(seconds=20))
    item.added_at = LONG_AGO
    item.save()

    add(logged_in_client)  # the details are already saved, so TMDB is not asked

    item.refresh_from_db()
    assert item.removed_at is None
    assert item.added_at > LONG_AGO
    assert ToWatchItem.objects.count() == 1


def test_removing_a_title_that_is_not_on_the_list_does_not_crash(logged_in_client):
    response = remove(logged_in_client)

    assert response.status_code == 302
    assert 'not on your To Watch list' in logged_in_client.get(response['Location']).content.decode()


def test_undoing_when_there_is_nothing_to_undo_does_not_crash(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_URL).respond(json=MADE_UP_MOVIE)
    add(logged_in_client)  # on the list, never removed
    before = snapshot()

    response = undo(logged_in_client)

    assert response.status_code == 302
    assert snapshot() == before


# --- each account has its own list -----------------------------------------------------------


def test_each_account_sees_only_its_own_list(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_URL).respond(json=MADE_UP_MOVIE)
    add(logged_in_client)
    other = make_client('second-user')

    assert 'Made-up Movie' not in to_watch_page(other)
    assert 'Made-up Movie' in to_watch_page(logged_in_client)


def test_one_account_cannot_remove_or_undo_for_another(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_URL).respond(json=MADE_UP_MOVIE)
    add(logged_in_client)
    other = make_client('second-user')
    add(other)
    before = snapshot()

    remove(other)  # removes only the second account's own entry
    undo(logged_in_client)  # nothing of the first account's was removed

    mine, theirs = ToWatchItem.objects.order_by('id')
    assert mine.removed_at is None
    assert theirs.removed_at is not None
    assert snapshot()[0] == before[0]


# --- the buttons on the search results -------------------------------------------------------


def test_search_results_show_add_or_remove_for_each_title(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_URL).respond(json=MADE_UP_MOVIE)
    add(logged_in_client)
    found = [
        {'media_type': 'movie', **MADE_UP_MOVIE},
        {'media_type': 'tv', **MADE_UP_SERIES},
    ]
    respx_mock.get(SEARCH_URL).respond(json={'page': 1, 'results': found})

    page = logged_in_client.get('/search/', {'q': 'made-up'}).content.decode()

    # The movie is already on the list, the series is not.
    assert page.count('action="/to-watch/remove/"') == 1
    assert page.count('action="/to-watch/add/"') == 1
    assert page.count('class="tile"') == 2


def test_the_search_buttons_use_htmx_and_the_buttons_on_the_list_do_not(logged_in_client, respx_mock):
    found = [{'media_type': 'movie', **MADE_UP_MOVIE}]
    respx_mock.get(SEARCH_URL).respond(json={'page': 1, 'results': found})
    respx_mock.get(MOVIE_URL).respond(json=MADE_UP_MOVIE)

    search_page = logged_in_client.get('/search/', {'q': 'made-up'}).content.decode()
    add(logged_in_client)
    list_page = to_watch_page(logged_in_client)

    assert 'hx-post="/to-watch/add/"' in search_page
    assert 'hx-post' not in list_page


def test_with_htmx_only_the_button_changes(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_URL).respond(json=MADE_UP_MOVIE)
    htmx = {'headers': {'HX-Request': 'true'}}

    added = logged_in_client.post(
        '/to-watch/add/', {'kind': 'movie', 'tmdb_id': 603, 'next': '/search/?q=made-up'}, **htmx
    )
    assert added.status_code == 200
    assert 'action="/to-watch/remove/"' in added.content.decode()
    assert '<html' not in added.content.decode()
    assert ToWatchItem.objects.get().removed_at is None

    removed = logged_in_client.post(
        '/to-watch/remove/', {'kind': 'movie', 'tmdb_id': 603, 'next': '/search/?q=made-up'}, **htmx
    )
    assert removed.status_code == 200
    assert 'action="/to-watch/add/"' in removed.content.decode()
    assert ToWatchItem.objects.get().removed_at is not None


def test_with_htmx_a_tmdb_failure_shows_the_message_next_to_the_button(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_URL).respond(500)

    response = logged_in_client.post(
        '/to-watch/add/', {'kind': 'movie', 'tmdb_id': 603}, headers={'HX-Request': 'true'}
    )

    body = response.content.decode()
    assert response.status_code == 200
    assert 'TMDB answered with an error' in body
    assert 'action="/to-watch/add/"' in body
    assert Title.objects.count() == 0
    # With htmx the message belongs to the button, so none is queued for the next full page.
    assert 'TMDB answered with an error' not in to_watch_page(logged_in_client)


# --- safety ----------------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    'url',
    [
        '/movies/', '/series/', '/to-watch/', '/to-watch/removed/?kind=movie',
        '/to-watch/add/', '/to-watch/remove/', '/to-watch/undo/',
    ],
)
def test_these_addresses_are_closed_when_logged_out(client, respx_mock, url):
    form = {'kind': 'movie', 'tmdb_id': 603}
    is_a_page = url.startswith(('/movies/', '/series/', '/to-watch/removed/')) or url == '/to-watch/'
    response = client.get(url) if is_a_page else client.post(url, form)

    assert response.status_code == 302
    assert response['Location'].startswith('/login/')
    assert respx_mock.calls.call_count == 0
    assert ToWatchItem.objects.count() == 0


@pytest.mark.parametrize('url', ['/to-watch/add/', '/to-watch/remove/', '/to-watch/undo/'])
def test_the_buttons_only_accept_posts(logged_in_client, respx_mock, url):
    assert logged_in_client.get(url).status_code == 405
    assert respx_mock.calls.call_count == 0


@pytest.mark.parametrize(
    'form',
    [
        {'kind': 'person', 'tmdb_id': 603},
        {'kind': 'movie', 'tmdb_id': 'abc'},
        {'kind': 'movie', 'tmdb_id': 0},
        {'kind': 'movie', 'tmdb_id': -4},
        {'kind': 'movie'},
        {},
    ],
)
def test_a_button_with_nonsense_is_refused(logged_in_client, respx_mock, form):
    for url in ('/to-watch/add/', '/to-watch/remove/', '/to-watch/undo/'):
        assert logged_in_client.post(url, form).status_code == 400

    assert respx_mock.calls.call_count == 0
    assert ToWatchItem.objects.count() == 0


def test_a_button_needs_the_csrf_token(db, respx_mock):
    strict = make_client('made-up-user', enforce_csrf_checks=True)

    response = strict.post('/to-watch/add/', {'kind': 'movie', 'tmdb_id': 603})

    assert response.status_code == 403
    assert respx_mock.calls.call_count == 0


@pytest.mark.parametrize('elsewhere', ['https://evil.example/', '//evil.example/', 'javascript:alert(1)'])
def test_a_button_never_sends_you_to_another_site(logged_in_client, respx_mock, elsewhere):
    respx_mock.get(MOVIE_URL).respond(json=MADE_UP_MOVIE)

    response = add(logged_in_client, next=elsewhere)

    assert response['Location'] == '/movies/'


def test_a_button_returns_you_to_the_page_you_were_on(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_URL).respond(json=MADE_UP_MOVIE)

    response = add(logged_in_client, next='/search/?q=made-up')

    assert response['Location'] == '/search/?q=made-up'


def test_the_tmdb_key_never_reaches_the_browser(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_URL).respond(json=MADE_UP_MOVIE)
    add(logged_in_client)

    response = logged_in_client.get('/movies/')

    assert 'made-up-secret-key' not in response.content.decode()
    assert 'made-up-secret-key' not in str(response.headers)


# --- the Movies and Series sections ----------------------------------------------------------


def test_the_header_links_to_the_movies_and_series_sections(logged_in_client):
    page = logged_in_client.get('/').content.decode()
    header = page[page.index('<header'):page.index('</header>')]

    assert 'href="/movies/"' in header
    assert 'href="/series/"' in header
    # The two screens that moved are no longer links of their own in the header.
    assert 'href="/to-watch/"' not in header
    assert 'href="/history/"' not in header


def test_each_section_lists_only_its_own_kind(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_URL).respond(json=MADE_UP_MOVIE)
    respx_mock.get(SERIES_URL).respond(json=MADE_UP_SERIES)
    add(logged_in_client)
    add(logged_in_client, kind='series', tmdb_id=1399)

    assert tiles(to_watch_page(logged_in_client, 'movie')) == ['/movie/603/']
    assert tiles(to_watch_page(logged_in_client, 'series')) == ['/series/1399/']


def test_an_empty_section_says_which_kind_is_missing(logged_in_client):
    assert 'No movies on your To Watch list yet' in to_watch_page(logged_in_client, 'movie')
    assert 'No series on your To Watch list yet' in to_watch_page(logged_in_client, 'series')


def test_the_movies_section_has_the_tabs_to_watch_and_history(logged_in_client):
    page = to_watch_page(logged_in_client)

    assert 'href="/movies/" aria-current="page">To Watch</a>' in page  # the tab you are on
    assert 'href="/movies/history/">History</a>' in page


def test_the_series_section_has_the_tabs_to_watch_watching_and_finished(logged_in_client):
    page = to_watch_page(logged_in_client, 'series')

    assert 'href="/series/" aria-current="page">To Watch</a>' in page  # the tab you are on
    assert 'href="/series/watching/">Watching</a>' in page
    assert 'href="/series/finished/">Finished</a>' in page
    assert 'History' not in page


def test_the_old_addresses_still_work(logged_in_client):
    to_watch, history = logged_in_client.get('/to-watch/'), logged_in_client.get('/history/')

    assert (to_watch.status_code, to_watch['Location']) == (302, '/movies/')
    assert (history.status_code, history['Location']) == (302, '/movies/history/')


def test_recently_removed_stays_within_its_own_section(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_URL).respond(json=MADE_UP_MOVIE)
    respx_mock.get(SERIES_URL).respond(json=MADE_UP_SERIES)
    add(logged_in_client)
    add(logged_in_client, kind='series', tmdb_id=1399)
    remove(logged_in_client)
    remove(logged_in_client, kind='series', tmdb_id=1399)
    logged_in_client.get('/')  # the notices about adding are shown once, on the next page, and then gone

    movies, series = to_watch_page(logged_in_client, 'movie'), to_watch_page(logged_in_client, 'series')

    assert 'Made-up Movie' in movies and 'Made-up Series' not in movies
    assert 'Made-up Series' in series and 'Made-up Movie' not in series
    assert 'hx-get="/to-watch/removed/?kind=series"' in series  # and it checks back for its own kind only


def test_the_removed_block_of_one_kind_ignores_the_other(logged_in_client):
    make_removed_title(logged_in_client.user, 1, datetime.timedelta(seconds=2), kind='movie')
    make_removed_title(logged_in_client.user, 2, datetime.timedelta(seconds=2), kind='series')

    movies = logged_in_client.get('/to-watch/removed/?kind=movie').content.decode()
    series = logged_in_client.get('/to-watch/removed/?kind=series').content.decode()

    assert 'Made-up Movie 1 ' in movies and 'Made-up Movie 2 ' not in movies
    assert 'Made-up Movie 2 ' in series and 'Made-up Movie 1 ' not in series
    assert 'name="next" value="/series/"' in series


@pytest.mark.parametrize('query', ['', '?kind=person', '?kind='])
def test_the_removed_block_needs_a_real_kind(logged_in_client, query):
    assert logged_in_client.get('/to-watch/removed/' + query).status_code == 400


def test_a_series_removal_can_be_undone_from_the_series_section(logged_in_client, respx_mock):
    respx_mock.get(SERIES_URL).respond(json=MADE_UP_SERIES)
    add(logged_in_client, kind='series', tmdb_id=1399)
    ToWatchItem.objects.update(added_at=LONG_AGO)
    before = snapshot()

    removed = remove(logged_in_client, kind='series', tmdb_id=1399)
    assert removed['Location'] == '/series/'  # no page to return to: back to its own section
    assert tiles(to_watch_page(logged_in_client, 'series')) == []
    restored = undo(logged_in_client, kind='series', tmdb_id=1399)

    assert restored['Location'] == '/series/'
    assert snapshot() == before
    assert tiles(to_watch_page(logged_in_client, 'series')) == ['/series/1399/']


# --- the button on the title page ------------------------------------------------------------


def test_the_movie_page_has_an_add_button_below_the_poster(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_URL).respond(json=MADE_UP_MOVIE)

    page = logged_in_client.get('/movie/603/').content.decode()

    assert 'action="/to-watch/add/"' in page
    assert 'Add to To Watch' in page
    assert 'name="kind" value="movie"' in page
    assert 'name="tmdb_id" value="603"' in page
    # After the poster and before the description: it sits under the poster.
    assert page.index('Poster of Made-up Movie') < page.index('Add to To Watch') < page.index('A made-up story')


def test_the_series_page_has_an_add_button(logged_in_client, respx_mock):
    respx_mock.get(SERIES_URL).respond(json=MADE_UP_SERIES)

    page = logged_in_client.get('/series/1399/').content.decode()

    assert 'Add to To Watch' in page
    assert 'name="kind" value="series"' in page
    assert 'name="tmdb_id" value="1399"' in page


def test_the_title_page_shows_remove_when_the_title_is_on_the_list(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_URL).respond(json=MADE_UP_MOVIE)
    add(logged_in_client)

    page = logged_in_client.get('/movie/603/').content.decode()

    assert 'action="/to-watch/remove/"' in page
    assert 'Remove from To Watch' in page
    assert 'action="/to-watch/add/"' not in page


def test_the_title_page_button_is_about_your_own_list(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_URL).respond(json=MADE_UP_MOVIE)
    add(logged_in_client)
    other = make_client('second-user')

    assert 'action="/to-watch/add/"' in other.get('/movie/603/').content.decode()


def test_the_title_page_button_updates_without_reloading(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_URL).respond(json=MADE_UP_MOVIE)

    page = logged_in_client.get('/movie/603/').content.decode()

    assert 'hx-post="/to-watch/add/"' in page


def test_adding_from_the_title_page_brings_you_back_to_it(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_URL).respond(json=MADE_UP_MOVIE)
    page = logged_in_client.get('/movie/603/').content.decode()
    assert 'name="next" value="/movie/603/"' in page

    response = add(logged_in_client, next='/movie/603/')

    assert response['Location'] == '/movie/603/'
    assert 'action="/to-watch/remove/"' in logged_in_client.get(response['Location']).content.decode()


def test_a_removed_title_shows_add_again_on_its_page(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_URL).respond(json=MADE_UP_MOVIE)
    add(logged_in_client)
    remove(logged_in_client)

    page = logged_in_client.get('/movie/603/').content.decode()

    assert 'action="/to-watch/add/"' in page


def test_a_title_page_that_tmdb_cannot_show_has_no_button(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_URL).respond(500)

    page = logged_in_client.get('/movie/603/').content.decode()

    assert 'TMDB answered with an error' in page
    assert 'action="/to-watch/add/"' not in page
    assert 'action="/to-watch/remove/"' not in page
