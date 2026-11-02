"""Ratings and notes: the stars (1 to 5) and the short note of a movie or a series, saved from its page.

Saving, changing and removing each leave the right values, and the page's form is always there to change them back
(there is no Undo button). A title does not have to be watched, or saved yet. Each account sees and changes only its
own."""

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

# The fixed "now" for every test here (so a saved series' episodes count as fresh and its page does not ask TMDB).
NOW = datetime.datetime(2026, 11, 1, 20, 0, tzinfo=datetime.UTC)


@pytest.fixture(autouse=True)
def tmdb_key(settings):
    settings.TMDB_API_KEY = 'made-up-secret-key'


@pytest.fixture(autouse=True)
def clock():
    with time_machine.travel(NOW, tick=False):
        yield


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


def message_after(client, response):
    """The page the button sent the browser back to, as the browser shows it."""
    return client.get(response['Location']).content.decode()


def mine(client):
    """This account's saved stars and note for the movie, or None when it has no row."""
    rating = Rating.objects.filter(user=client.user, title__tmdb_id=603).first()
    return (rating.stars, rating.note) if rating else None


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
    assert 'Rate it or add a note' in page
    assert 'rating-edit' not in page
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
    save(logged_in_client, '', '')

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


def test_removing_both_leaves_nothing_saved_or_shown(logged_in_client, movie_route):
    save(logged_in_client, 4, 'Remove me.')

    response = save(logged_in_client, '', '')

    assert mine(logged_in_client) is None
    assert Rating.objects.count() == 0  # nothing is kept
    page = message_after(logged_in_client, response)
    assert 'Rating removed and note removed.' in page
    assert 'rating-stars' not in page
    assert 'Remove me.' not in page
    assert 'Rate it or add a note' in page


def test_editing_again_puts_back_what_was_removed(logged_in_client, movie_route):
    save(logged_in_client, 4, 'Loved the ending.')
    save(logged_in_client, '', '')

    save(logged_in_client, 4, 'Loved the ending.')

    assert mine(logged_in_client) == (4, 'Loved the ending.')
    assert Rating.objects.count() == 1


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


def test_the_button_only_answers_to_a_post(logged_in_client):
    assert logged_in_client.get('/rating/save/').status_code == 405


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


def test_a_refused_save_leaves_the_saved_note_on_the_page(logged_in_client, movie_route):
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


def test_saving_the_same_values_again_changes_nothing(logged_in_client, movie_route):
    save(logged_in_client, 4, 'First.')
    save(logged_in_client, 2, 'Second.')
    before = list(Rating.objects.values())

    response = save(logged_in_client, 2, 'Second.')  # pressed Save twice

    assert 'Nothing changed' in message_after(logged_in_client, response)
    assert list(Rating.objects.values()) == before


# --- the saved rating and note are one box ----------------------------------------------------


def test_a_saved_rating_and_note_are_one_box_with_the_pencil_after_the_note(logged_in_client, movie_route):
    save(logged_in_client, 4, 'Loved the ending.')

    page = logged_in_client.get(MOVIE_PAGE).content.decode()
    card = page[page.index('class="rating-card"') : page.index('</details>')]

    # The stars are a picture; the score says the same in words, and the words for screen readers are there.
    assert re.search(r'class="rating-stars" aria-hidden="true">★★★★☆<', card)
    assert 'class="rating-score">4 of 5<' in card
    assert '<span class="visually-hidden">Your rating: </span>' in card
    assert '<span class="visually-hidden">Your note: </span>' in card
    # In this order: the stars and score, the note, then the pencil that opens the form.
    assert card.index('4 of 5') < card.index('Loved the ending.') < card.index('rating-edit') < card.index('<form')


def test_with_stars_only_the_pencil_follows_the_score_and_there_is_no_note(logged_in_client, movie_route):
    save(logged_in_client, 5, '')

    page = logged_in_client.get(MOVIE_PAGE).content.decode()
    card = page[page.index('class="rating-card"') : page.index('</details>')]

    assert card.index('5 of 5') < card.index('rating-edit')
    assert 'rating-note' not in page and 'Your note:' not in page


def test_with_a_note_only_there_are_no_stars_in_the_box(logged_in_client, movie_route):
    save(logged_in_client, '', 'Just a note.')

    page = logged_in_client.get(MOVIE_PAGE).content.decode()
    card = page[page.index('class="rating-card"') : page.index('</details>')]

    assert 'rating-stars' not in page and 'rating-score' not in page and 'Your rating:' not in page
    assert card.index('Just a note.') < card.index('rating-edit')


def test_with_nothing_saved_there_is_no_box_only_the_rate_button(logged_in_client, movie_route):
    page = logged_in_client.get(MOVIE_PAGE).content.decode()

    assert 'rating-card' not in page
    assert 'class="outline secondary rating-open"' in page and 'Rate it or add a note' in page


# --- no Undo button: the edit icon is always there ---------------------------------------------


def test_the_page_has_no_undo_button_but_always_has_the_edit_icon(logged_in_client, movie_route):
    save(logged_in_client, 4, 'Mine.')

    for _ in range(2):  # right after saving, and again on a later visit
        page = logged_in_client.get(MOVIE_PAGE).content.decode()
        assert 'Undo' not in page
        assert '/rating/undo/' not in page
        assert 'hx-get' not in page
        # The way to change or remove is the pencil icon, not words: its name is only for screen readers and the tooltip.
        summary = re.search(r'<summary class="rating-edit"[^>]*>(.*?)</summary>', page, re.DOTALL)
        assert summary
        assert 'aria-label="Change or remove your rating and note"' in summary.group(0)
        assert '<svg' in summary.group(1)
        assert 'Change or remove' not in re.sub(r'<[^>]*>', '', summary.group(1))


def test_the_edit_icon_opens_a_form_with_what_is_saved(logged_in_client, movie_route):
    save(logged_in_client, 3, 'Mine.')

    page = logged_in_client.get(MOVIE_PAGE).content.decode()

    form = page[page.index('<details') : page.index('</details>')]
    assert form.index('rating-edit') < form.index('action="/rating/save/"')  # the icon opens the form
    assert re.search(r'name="stars" value="3"[^>]* checked', form)
    assert re.search(r'<textarea[^>]*>Mine\.</textarea>', form)


def test_the_series_page_has_the_edit_icon_too(logged_in_client, series):
    save(logged_in_client, 3, kind='series', tmdb_id=1399, next=SERIES_PAGE)

    page = logged_in_client.get(SERIES_PAGE).content.decode()

    assert 'class="rating-edit"' in page
    assert 'Undo' not in page


def test_the_undo_addresses_are_gone(logged_in_client):
    assert logged_in_client.post('/rating/undo/', {'kind': 'movie', 'tmdb_id': 603}).status_code == 404
    assert logged_in_client.get('/rating/undo/notice/?kind=movie&tmdb_id=603').status_code == 404


# --- only my own account ------------------------------------------------------------------------


def test_one_account_never_sees_the_rating_of_another(logged_in_client, movie_route):
    save(logged_in_client, 5, 'Private thought.')
    other = make_client('second-user')

    page = other.get(MOVIE_PAGE).content.decode()

    assert 'Private thought.' not in page
    assert 'rating-stars' not in page
    assert 'rating-edit' not in page


def test_each_account_has_its_own_rating_for_the_same_title(logged_in_client, movie_route):
    other = make_client('second-user')
    save(logged_in_client, 5, 'Mine.')
    save(other, 1, 'Theirs.')

    assert mine(logged_in_client) == (5, 'Mine.')
    assert mine(other) == (1, 'Theirs.')
    assert Rating.objects.count() == 2
    assert Title.objects.count() == 1


def test_one_account_cannot_change_or_remove_the_rating_of_another(logged_in_client, movie_route):
    save(logged_in_client, 4, 'Mine.')
    other = make_client('second-user')
    before = list(Rating.objects.values())

    response = save(other, '', '')  # nothing of theirs to remove

    assert 'Nothing changed' in message_after(other, response)
    assert list(Rating.objects.values()) == before
    save(other, 1, 'Theirs.')
    save(other, '', '')  # removing their own rating leaves mine alone
    assert mine(logged_in_client) == (4, 'Mine.')
    assert mine(other) is None
