"""Ratings and notes: the stars (1 to 5) and the short note of a movie or a series, saved from its page.

Saving, changing and removing each leave the right values, and each can be undone for 10 seconds. A title does not
have to be watched, or saved yet. Each account sees and changes only its own."""

import datetime
import re

import httpx
import pytest
import time_machine
from django.contrib.auth.models import User
from django.test import Client

from core.models import Profile, Rating, Title, ToWatchItem, Watch

MOVIE_URL = 'https://api.themoviedb.org/3/movie/603'
MOVIE_PAGE = '/movie/603/'
SERIES_PAGE = '/series/1399/'

# Made-up TMDB answer. The tests never call the real TMDB.
MADE_UP_MOVIE = {
    'id': 603,
    'title': 'Made-up Movie',
    'release_date': '1999-03-31',
    'poster_path': '/made-up-movie.jpg',
    'overview': 'A made-up story about a movie.',
}

# The fixed "now" for every test here.
NOW = datetime.datetime(2026, 11, 1, 20, 0, tzinfo=datetime.UTC)


@pytest.fixture(autouse=True)
def tmdb_key(settings):
    settings.TMDB_API_KEY = 'made-up-secret-key'


@pytest.fixture(autouse=True)
def clock():
    with time_machine.travel(NOW, tick=False) as traveller:
        yield traveller


def make_client(name):
    """A browser logged in as a new account (with a time zone chosen, so no redirect to Profile)."""
    user = User.objects.create_user(username=name, password='made-up-password')
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    client = Client()
    client.force_login(user)
    client.user = user
    return client


@pytest.fixture
def logged_in_client(db):
    return make_client('made-up-user')


@pytest.fixture
def movie_route(respx_mock):
    return respx_mock.get(MOVIE_URL).respond(json=MADE_UP_MOVIE)


@pytest.fixture
def series(db):
    """A series already saved (with its episodes marked as fresh, so opening its page does not ask TMDB)."""
    return Title.objects.create(kind='series', tmdb_id=1399, title='Made-up Series', episodes_refreshed_at=NOW)


def save(client, stars='', note='', kind='movie', tmdb_id=603, **extra):
    """The Save button of the rating box. `stars` is the radio button picked: '' is "No rating"."""
    return client.post(
        '/rating/save/', {'kind': kind, 'tmdb_id': tmdb_id, 'stars': stars, 'note': note, 'next': MOVIE_PAGE, **extra}
    )


def undo(client, kind='movie', tmdb_id=603, **extra):
    return client.post('/rating/undo/', {'kind': kind, 'tmdb_id': tmdb_id, 'next': MOVIE_PAGE, **extra})


def message_after(client, response):
    """The page the button sent the browser back to, as the browser shows it."""
    return client.get(response['Location']).content.decode()


def mine(client):
    """This account's saved stars and note for the movie, or None when it has no row."""
    rating = Rating.objects.filter(user=client.user, title__tmdb_id=603).first()
    return (rating.stars, rating.note) if rating else None


def undo_form(page):
    return 'action="/rating/undo/"' in page


# --- saving, changing, removing ---------------------------------------------------------------


def test_a_rating_and_a_note_are_saved_and_shown_on_the_movie_page(logged_in_client, movie_route):
    response = save(logged_in_client, 4, 'Loved the ending.')

    assert response.status_code == 302
    assert response['Location'] == MOVIE_PAGE
    page = logged_in_client.get(MOVIE_PAGE).content.decode()  # a fresh request, like reloading the page
    assert re.search(r'name="stars" value="4"[^>]* checked', page)
    assert not re.search(r'name="stars" value="[^4"][^>]* checked', page)
    assert '★★★★☆' in page and '4 of 5' in page
    assert re.search(r'<textarea[^>]*>Loved the ending\.</textarea>', page)
    assert mine(logged_in_client) == (4, 'Loved the ending.')


def test_a_rating_and_a_note_are_shown_on_the_series_page(logged_in_client, series):
    save(logged_in_client, 2, 'Slow start.', kind='series', tmdb_id=1399)

    page = logged_in_client.get(SERIES_PAGE).content.decode()

    assert re.search(r'name="stars" value="2"[^>]* checked', page)
    assert '★★☆☆☆' in page
    assert 'Slow start.' in page
    rating = Rating.objects.get()
    assert (rating.title, rating.stars, rating.note) == (series, 2, 'Slow start.')


def test_the_box_is_empty_before_anything_is_saved(logged_in_client, movie_route):
    page = logged_in_client.get(MOVIE_PAGE).content.decode()

    assert re.search(r'name="stars" value=""[^>]* checked', page)  # "No rating"
    assert 'rating-stars' not in page
    assert undo_form(page) is False
    assert Rating.objects.count() == 0


def test_a_title_that_is_not_saved_yet_is_saved_from_tmdb_first(logged_in_client, movie_route):
    assert Title.objects.count() == 0

    save(logged_in_client, 5)

    saved = Title.objects.get()
    assert (saved.kind, saved.tmdb_id, saved.title, saved.year) == ('movie', 603, 'Made-up Movie', '1999')
    assert saved.poster_url == 'https://image.tmdb.org/t/p/w342/made-up-movie.jpg'
    assert Rating.objects.get().title == saved


def test_the_rating_does_not_ask_tmdb_again_for_a_title_already_saved(logged_in_client, movie_route):
    Title.objects.create(kind='movie', tmdb_id=603, title='Made-up Movie')

    save(logged_in_client, 3)

    assert movie_route.call_count == 0
    assert mine(logged_in_client) == (3, '')


def test_a_title_i_have_not_watched_can_be_rated(logged_in_client, movie_route):
    save(logged_in_client, 1, 'Not for me.')

    assert Watch.objects.count() == 0
    assert mine(logged_in_client) == (1, 'Not for me.')


def test_rating_changes_nothing_but_the_rating(logged_in_client, movie_route):
    movie = Title.objects.create(kind='movie', tmdb_id=603, title='Made-up Movie')
    ToWatchItem.objects.create(user=logged_in_client.user, title=movie)
    Watch.objects.create(user=logged_in_client.user, title=movie, watched_on=datetime.date(2026, 10, 1))
    before = (list(ToWatchItem.objects.values()), list(Watch.objects.values()))

    save(logged_in_client, 5, 'Great.')
    save(logged_in_client, 2, 'Meh.')
    undo(logged_in_client)

    assert (list(ToWatchItem.objects.values()), list(Watch.objects.values())) == before


def test_saving_again_changes_the_rating_and_the_note(logged_in_client, movie_route):
    save(logged_in_client, 4, 'Loved the ending.')

    save(logged_in_client, 2, 'Second time, not so sure.')

    assert mine(logged_in_client) == (2, 'Second time, not so sure.')
    assert Rating.objects.count() == 1  # one row per account and title


def test_changing_only_the_stars_keeps_the_note(logged_in_client, movie_route):
    save(logged_in_client, 4, 'Keep me.')

    save(logged_in_client, 5, 'Keep me.')

    assert mine(logged_in_client) == (5, 'Keep me.')


def test_a_note_alone_can_be_saved_without_stars(logged_in_client, movie_route):
    save(logged_in_client, '', 'Only a note.')

    assert mine(logged_in_client) == (None, 'Only a note.')
    page = logged_in_client.get(MOVIE_PAGE).content.decode()
    assert re.search(r'name="stars" value=""[^>]* checked', page)
    assert 'Only a note.' in page


def test_removing_the_rating_keeps_the_note(logged_in_client, movie_route):
    save(logged_in_client, 4, 'Keep me.')

    response = save(logged_in_client, '', 'Keep me.')

    assert mine(logged_in_client) == (None, 'Keep me.')
    assert 'Rating removed.' in message_after(logged_in_client, response)


def test_removing_the_note_keeps_the_rating(logged_in_client, movie_route):
    save(logged_in_client, 4, 'Remove me.')

    response = save(logged_in_client, 4, '')

    assert mine(logged_in_client) == (4, '')
    assert 'Note removed.' in message_after(logged_in_client, response)


def test_removing_both_leaves_nothing_shown(logged_in_client, movie_route):
    save(logged_in_client, 4, 'Remove me.')

    save(logged_in_client, '', '')

    assert mine(logged_in_client) == (None, '')
    page = logged_in_client.get(MOVIE_PAGE).content.decode()
    assert 'rating-stars' not in page
    assert 'Remove me.' not in page


def test_one_star_is_not_the_same_as_no_rating(logged_in_client, movie_route):
    save(logged_in_client, 1)

    assert mine(logged_in_client) == (1, '')
    assert '★☆☆☆☆' in logged_in_client.get(MOVIE_PAGE).content.decode()


def test_saving_says_what_happened(logged_in_client, movie_route):
    response = save(logged_in_client, 3, 'A note.')

    assert 'Rating saved and note saved.' in message_after(logged_in_client, response)


def test_a_note_keeps_its_line_breaks_and_is_shown_as_text(logged_in_client, movie_route):
    save(logged_in_client, 3, '  First line\r\nSecond <b>line</b>  ')

    assert mine(logged_in_client) == (3, 'First line\nSecond <b>line</b>')
    page = logged_in_client.get(MOVIE_PAGE).content.decode()
    assert 'Second &lt;b&gt;line&lt;/b&gt;' in page
    assert 'Second <b>line</b>' not in page


# --- what is refused --------------------------------------------------------------------------


def test_a_note_over_500_characters_is_refused_and_nothing_is_saved(logged_in_client, movie_route):
    save(logged_in_client, 4, 'Before.')

    response = save(logged_in_client, 2, 'x' * 501)

    assert 'at most 500 characters' in message_after(logged_in_client, response)
    assert mine(logged_in_client) == (4, 'Before.')


def test_a_note_of_exactly_500_characters_is_saved(logged_in_client, movie_route):
    save(logged_in_client, '', 'x' * 500)

    assert mine(logged_in_client) == (None, 'x' * 500)


def test_a_line_break_counts_as_one_character_like_in_the_box(logged_in_client, movie_route):
    note = ('x' * 49 + '\r\n') * 10  # 500 characters in the box, 510 as the browser sends them (the end is trimmed)

    save(logged_in_client, '', note)

    assert Rating.objects.get().note == note.replace('\r\n', '\n').strip()


@pytest.mark.parametrize('stars', ['0', '6', '-1', 'three', '2.5'])
def test_stars_other_than_1_to_5_are_refused(logged_in_client, movie_route, stars):
    save(logged_in_client, 4, 'Before.')

    save(logged_in_client, stars, 'After.')

    assert mine(logged_in_client) == (4, 'Before.')


@pytest.mark.parametrize('data', [{}, {'kind': 'movie'}, {'kind': 'book', 'tmdb_id': 1}, {'kind': 'movie', 'tmdb_id': 0}])
def test_a_save_for_no_real_title_is_refused(logged_in_client, data):
    assert logged_in_client.post('/rating/save/', {**data, 'stars': 3}).status_code == 400
    assert Rating.objects.count() == 0


def test_the_buttons_only_answer_to_a_post(logged_in_client):
    assert logged_in_client.get('/rating/save/').status_code == 405
    assert logged_in_client.get('/rating/undo/').status_code == 405


def test_a_title_tmdb_does_not_know_is_not_found(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_URL).respond(404)

    assert save(logged_in_client, 3).status_code == 404
    assert Rating.objects.count() == 0


def test_when_tmdb_does_not_answer_nothing_is_saved_and_a_message_says_so(logged_in_client, respx_mock):
    respx_mock.get(MOVIE_URL).mock(side_effect=httpx.ConnectError('no network'))

    response = save(logged_in_client, 3, 'Lost?')

    assert 'Could not reach TMDB' in message_after(logged_in_client, response)
    assert Title.objects.count() == 0
    assert Rating.objects.count() == 0


def test_the_note_is_not_lost_from_the_page_when_a_save_is_refused(logged_in_client, movie_route):
    save(logged_in_client, 4, 'Saved note.')

    save(logged_in_client, 4, 'x' * 600)

    assert 'Saved note.' in logged_in_client.get(MOVIE_PAGE).content.decode()


def test_the_page_comes_back_to_the_address_the_form_was_on(logged_in_client, series):
    response = save(logged_in_client, 3, kind='series', tmdb_id=1399, next='/series/1399/?season=2')

    assert response['Location'] == '/series/1399/?season=2'


def test_the_page_never_goes_to_another_site(logged_in_client, movie_route):
    response = save(logged_in_client, 3, next='https://example.com/elsewhere')

    assert response['Location'] != 'https://example.com/elsewhere'
    assert response['Location'].startswith('/')


# --- saving what is already saved --------------------------------------------------------------


def test_saving_with_nothing_to_save_creates_no_row_and_does_not_ask_tmdb(logged_in_client, movie_route):
    response = save(logged_in_client, '', '')

    assert movie_route.call_count == 0  # before the page below is opened, which does ask TMDB for the movie
    assert 'Nothing changed' in message_after(logged_in_client, response)
    assert Rating.objects.count() == 0
    assert Title.objects.count() == 0


def test_saving_the_same_values_again_keeps_the_undo_of_the_earlier_change(logged_in_client, movie_route):
    save(logged_in_client, 4, 'First.')
    save(logged_in_client, 2, 'Second.')

    response = save(logged_in_client, 2, 'Second.')  # pressed Save twice

    assert 'Nothing changed' in message_after(logged_in_client, response)
    undo(logged_in_client)
    assert mine(logged_in_client) == (4, 'First.')


# --- undo ---------------------------------------------------------------------------------------


def test_undoing_the_first_save_puts_everything_back_to_nothing(logged_in_client, movie_route):
    save(logged_in_client, 4, 'Loved the ending.')

    response = undo(logged_in_client)

    assert 'Brought back your previous rating and note.' in message_after(logged_in_client, response)
    assert mine(logged_in_client) == (None, '')
    rating = Rating.objects.get()
    assert (rating.previous_stars, rating.previous_note, rating.changed_at) == (None, '', None)
    page = logged_in_client.get(MOVIE_PAGE).content.decode()
    assert 'rating-stars' not in page and 'Loved the ending.' not in page and undo_form(page) is False


def test_undoing_a_change_brings_back_the_previous_stars_and_note(logged_in_client, movie_route, clock):
    save(logged_in_client, 4, 'Loved the ending.')
    clock.shift(datetime.timedelta(minutes=5))
    save(logged_in_client, 2, 'Second thoughts.')

    undo(logged_in_client)

    assert mine(logged_in_client) == (4, 'Loved the ending.')
    assert Rating.objects.get().changed_at is None


def test_undoing_a_removal_brings_back_what_was_removed(logged_in_client, movie_route, clock):
    save(logged_in_client, 4, 'Loved the ending.')
    clock.shift(datetime.timedelta(minutes=5))
    save(logged_in_client, '', '')
    assert mine(logged_in_client) == (None, '')

    undo(logged_in_client)

    assert mine(logged_in_client) == (4, 'Loved the ending.')


def test_undoing_the_removal_of_only_the_stars_or_only_the_note(logged_in_client, movie_route, clock):
    save(logged_in_client, 4, 'Loved the ending.')
    clock.shift(datetime.timedelta(minutes=5))
    save(logged_in_client, '', 'Loved the ending.')
    undo(logged_in_client)
    assert mine(logged_in_client) == (4, 'Loved the ending.')

    clock.shift(datetime.timedelta(minutes=5))
    save(logged_in_client, 4, '')
    undo(logged_in_client)
    assert mine(logged_in_client) == (4, 'Loved the ending.')


def test_undo_only_goes_one_step_back(logged_in_client, movie_route, clock):
    save(logged_in_client, 5, 'One.')
    clock.shift(datetime.timedelta(minutes=5))
    save(logged_in_client, 3, 'Two.')
    clock.shift(datetime.timedelta(minutes=5))
    save(logged_in_client, 1, 'Three.')

    undo(logged_in_client)
    response = undo(logged_in_client)  # nothing more to undo

    assert 'nothing to undo' in message_after(logged_in_client, response)
    assert mine(logged_in_client) == (3, 'Two.')


def test_undo_with_nothing_saved_does_not_crash(logged_in_client):
    response = undo(logged_in_client)

    assert response.status_code == 302
    assert 'nothing to undo' in message_after(logged_in_client, response)
    assert Rating.objects.count() == 0


def test_undo_works_just_inside_the_10_seconds(logged_in_client, movie_route, clock):
    save(logged_in_client, 4, 'Mine.')
    save(logged_in_client, 1, 'Changed.')
    clock.shift(datetime.timedelta(seconds=9))

    undo(logged_in_client)

    assert mine(logged_in_client) == (4, 'Mine.')


def test_undo_is_refused_after_the_10_seconds(logged_in_client, movie_route, clock):
    save(logged_in_client, 4, 'Mine.')
    save(logged_in_client, 1, 'Changed.')
    clock.shift(datetime.timedelta(seconds=11))
    before = list(Rating.objects.values())

    response = undo(logged_in_client)

    assert 'too late to undo' in message_after(logged_in_client, response)
    assert list(Rating.objects.values()) == before
    assert mine(logged_in_client) == (1, 'Changed.')


def test_after_10_seconds_the_page_offers_no_undo_but_the_rating_can_be_edited_again(
    logged_in_client, movie_route, clock
):
    save(logged_in_client, 4, 'Mine.')
    clock.shift(datetime.timedelta(seconds=11))

    page = logged_in_client.get(MOVIE_PAGE).content.decode()
    assert undo_form(page) is False
    assert 'hx-get' not in page

    save(logged_in_client, 5, 'Mine, edited.')
    assert mine(logged_in_client) == (5, 'Mine, edited.')


# --- the Undo notice ----------------------------------------------------------------------------


def test_right_after_saving_the_page_offers_undo_for_10_seconds(logged_in_client, movie_route):
    save(logged_in_client, 4, 'Mine.')

    page = logged_in_client.get(MOVIE_PAGE).content.decode()

    assert undo_form(page)
    assert 'You can undo this change for 10 seconds.' in page
    # The notice asks again just after its time runs out, so an open page loses it by itself.
    delay = int(re.search(r'hx-trigger="load delay:(\d+)s"', page).group(1))
    assert delay == 11
    assert 'hx-get="/rating/undo/notice/?kind=movie&amp;tmdb_id=603&amp;next=/movie/603/"' in page


def test_the_notice_asks_again_sooner_the_less_time_is_left(logged_in_client, movie_route, clock):
    save(logged_in_client, 4, 'Mine.')
    clock.shift(datetime.timedelta(seconds=6))

    page = logged_in_client.get(MOVIE_PAGE).content.decode()

    assert int(re.search(r'hx-trigger="load delay:(\d+)s"', page).group(1)) == 5  # 4 seconds left, plus a second


def test_the_notice_alone_is_empty_once_the_time_has_run_out(logged_in_client, movie_route, clock):
    save(logged_in_client, 4, 'Mine.')
    address = '/rating/undo/notice/?kind=movie&tmdb_id=603&next=/movie/603/'
    assert undo_form(logged_in_client.get(address).content.decode())

    clock.shift(datetime.timedelta(seconds=11))
    body = logged_in_client.get(address).content.decode()

    assert undo_form(body) is False
    assert 'hx-get' not in body
    assert re.search(r'<div id="rating-undo">\s*</div>', body)


@pytest.mark.parametrize('query', ['', '?kind=movie', '?kind=book&tmdb_id=1', '?kind=movie&tmdb_id=x'])
def test_the_notice_needs_a_real_title(logged_in_client, query):
    assert logged_in_client.get('/rating/undo/notice/' + query).status_code == 400


def test_the_series_page_has_the_notice_too(logged_in_client, series):
    save(logged_in_client, 3, kind='series', tmdb_id=1399, next=SERIES_PAGE)

    page = logged_in_client.get(SERIES_PAGE).content.decode()

    assert undo_form(page)
    assert 'value="series"' in page


# --- only my own account ------------------------------------------------------------------------


def test_one_account_never_sees_the_rating_of_another(logged_in_client, movie_route):
    save(logged_in_client, 5, 'Private thought.')
    other = make_client('second-user')

    page = other.get(MOVIE_PAGE).content.decode()

    assert 'Private thought.' not in page
    assert 'rating-stars' not in page
    assert undo_form(page) is False
    assert other.get('/rating/undo/notice/?kind=movie&tmdb_id=603&next=/movie/603/').content.decode().count('<form') == 0


def test_each_account_has_its_own_rating_for_the_same_title(logged_in_client, movie_route):
    other = make_client('second-user')
    save(logged_in_client, 5, 'Mine.')
    save(other, 1, 'Theirs.')

    assert mine(logged_in_client) == (5, 'Mine.')
    assert mine(other) == (1, 'Theirs.')
    assert Rating.objects.count() == 2
    assert Title.objects.count() == 1


def test_one_account_cannot_change_or_undo_for_another(logged_in_client, movie_route):
    save(logged_in_client, 4, 'Mine.')
    save(logged_in_client, 2, 'Changed.')
    other = make_client('second-user')
    before = list(Rating.objects.values())

    response = undo(other)
    save(other, '', '')  # nothing of theirs to remove

    assert 'nothing to undo' in message_after(other, response)
    assert list(Rating.objects.values()) == before
    assert mine(logged_in_client) == (2, 'Changed.')
