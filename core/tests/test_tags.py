"""My own tags (card #119): made, renamed and deleted on Profile, added to and removed from a title on its page.

Neither has an Undo (my decisions on the card): deleting a tag deletes it for good, and adding a tag to a title again
is the way back after removing it. A problem is shown next to the tags, since the page does not move. Each account
sees and changes only its own tags."""

import datetime

import httpx
import pytest
import time_machine
from django.contrib.auth.models import User
from django.test import Client

from core.models import DemoEvent, Profile, Tag, Title, TitleTag

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
def me(db):
    return make_client('made-up-user')


@pytest.fixture
def movie(db):
    """A movie already saved, with its length and genres, so its page never asks TMDB."""
    return Title.objects.create(
        kind='movie', tmdb_id=603, title='Made-up Movie', runtime=136, genres=[{'id': 18, 'name': 'Drama'}]
    )


@pytest.fixture
def series(db):
    """A series already saved (with its episodes marked as fresh, so opening its page does not ask TMDB)."""
    return Title.objects.create(kind='series', tmdb_id=1399, title='Made-up Series', episodes_refreshed_at=NOW)


def create(client, name, next_page='/profile/', **title):
    """The "Add tag" button on Profile, or (with `kind` and `tmdb_id`) the "New tag" box on a title's page."""
    return client.post('/tags/create/', {'name': name, 'next': next_page, **title})


def page_after(client, response):
    """The page the button sent the browser back to, as the browser shows it."""
    return client.get(response['Location']).content.decode()


def names(client):
    """This account's tags in use, by name."""
    return sorted(Tag.objects.filter(user=client.user).values_list('name', flat=True))


def tags_on(client, title):
    """The names of this account's tags on a title."""
    return sorted(
        TitleTag.objects.filter(tag__user=client.user, title=title).values_list('tag__name', flat=True)
    )


def everything(client):
    """All of the account's tag rows, to check that something put everything back as it was."""
    return (
        list(Tag.objects.filter(user=client.user).order_by('id').values()),
        list(TitleTag.objects.filter(tag__user=client.user).order_by('id').values()),
    )


# --- Profile: create, rename, delete ----------------------------------------------------------


def test_profile_has_my_tags_with_a_box_to_make_one(me):
    page = me.get('/profile/').content.decode()

    assert 'My tags' in page
    assert 'action="/tags/create/"' in page
    assert 'Only you see them' in page


def test_making_a_tag_on_profile_shows_it_there_as_a_chip(me, movie):
    response = create(me, '  comfort   food ')

    assert response['Location'] == '/profile/'
    page = page_after(me, response)
    assert names(me) == ['comfort food']
    assert 'aria-label="Rename the tag comfort food"' in page
    assert 'aria-label="Delete the tag comfort food"' in page
    # No message (the chip says it), and no count of titles.
    assert 'role="status"' not in page
    TitleTag.objects.create(tag=Tag.objects.get(user=me.user), title=movie)
    assert '1 title' not in me.get('/profile/').content.decode()


def test_a_tag_needs_a_name_and_at_most_30_characters(me):
    empty = page_after(me, create(me, '   '))
    long = page_after(me, create(me, 'x' * 31))
    create(me, 'y' * 30)

    assert 'Give the tag a name. Nothing was saved.' in empty
    assert 'A tag can be at most 30 characters, and yours has 31. Nothing was saved.' in long
    assert names(me) == ['y' * 30]


def test_two_tags_never_have_the_same_name_whatever_the_capital_letters(me):
    create(me, 'Comfort')

    page = page_after(me, create(me, 'comfort'))

    assert 'You already have a tag called “Comfort”.' in page
    assert names(me) == ['Comfort']


def test_renaming_a_tag_keeps_it_on_its_titles(me, movie):
    tag = Tag.objects.create(user=me.user, name='comfort')
    TitleTag.objects.create(tag=tag, title=movie)

    page = page_after(me, me.post('/tags/rename/', {'tag_id': tag.id, 'name': 'cosy', 'next': '/profile/'}))

    assert 'aria-label="Rename the tag cosy"' in page
    assert 'role="status"' not in page  # no message: the chip's new name says it
    assert tags_on(me, movie) == ['cosy']
    # Renaming it back is the undo.
    me.post('/tags/rename/', {'tag_id': tag.id, 'name': 'comfort'})
    assert tags_on(me, movie) == ['comfort']


def test_renaming_to_another_tags_name_is_refused_but_capital_letters_can_change(me):
    comfort = Tag.objects.create(user=me.user, name='comfort')
    Tag.objects.create(user=me.user, name='family')

    refused = page_after(me, me.post('/tags/rename/', {'tag_id': comfort.id, 'name': 'Family'}))
    me.post('/tags/rename/', {'tag_id': comfort.id, 'name': 'Comfort'})

    assert 'You already have a tag called “family”.' in refused
    assert names(me) == ['Comfort', 'family']


def test_deleting_a_tag_deletes_it_for_good_and_takes_it_off_all_its_titles(me, movie, series):
    tag = Tag.objects.create(user=me.user, name='comfort')
    TitleTag.objects.create(tag=tag, title=movie)
    TitleTag.objects.create(tag=tag, title=series)

    page = page_after(me, me.post('/tags/delete/', {'tag_id': tag.id, 'next': '/profile/'}))

    assert everything(me) == ([], [])
    assert 'Rename the tag comfort' not in page
    assert 'Undo' not in page
    assert 'comfort' not in me.get(MOVIE_PAGE).content.decode()
    assert Title.objects.count() == 2  # the titles themselves are never touched
    # Its name is free again.
    create(me, 'comfort')
    assert names(me) == ['comfort']


def test_a_problem_is_shown_next_to_the_tags_not_at_the_top(me, movie):
    Tag.objects.create(user=me.user, name='comfort')

    on_profile = page_after(me, create(me, 'Comfort'))
    on_title = page_after(me, create(me, 'x' * 31, next_page=MOVIE_PAGE, kind='movie', tmdb_id=603))

    for page in (on_profile, on_title):
        tags = page.split('class="tags-section"')[1]
        assert 'class="tag-problem"' in tags
        assert 'role="status"' not in page


# --- a title's page: add, remove, new tag ---------------------------------------------------------


def test_a_titles_page_has_my_tags_and_a_box_for_a_new_one(me, movie):
    Tag.objects.create(user=me.user, name='comfort')

    page = me.get(MOVIE_PAGE).content.decode()

    assert 'My tags' in page
    assert '+ comfort' in page
    assert 'aria-label="New tag for this title"' in page


def test_adding_a_tag_to_a_title_shows_it_as_a_chip_and_removing_it_takes_it_off(me, movie):
    tag = Tag.objects.create(user=me.user, name='comfort')
    form = {'tag_id': tag.id, 'kind': 'movie', 'tmdb_id': 603, 'next': MOVIE_PAGE}

    page = page_after(me, me.post('/tags/add/', form))

    assert tags_on(me, movie) == ['comfort']
    assert 'aria-label="Remove the tag comfort"' in page
    assert '+ comfort' not in page

    page = page_after(me, me.post('/tags/remove/', form))

    assert tags_on(me, movie) == []
    assert '+ comfort' in page
    assert names(me) == ['comfort']  # the tag itself stays

    # Adding it again is the way back.
    me.post('/tags/add/', form)
    assert tags_on(me, movie) == ['comfort']


def test_adding_the_same_tag_twice_makes_one_link(me, movie):
    tag = Tag.objects.create(user=me.user, name='comfort')
    form = {'tag_id': tag.id, 'kind': 'movie', 'tmdb_id': 603}

    me.post('/tags/add/', form)
    me.post('/tags/add/', form)

    assert TitleTag.objects.count() == 1


def test_tags_work_on_a_series_page_too(me, series):
    tag = Tag.objects.create(user=me.user, name='with family')

    page = page_after(me, me.post('/tags/add/', {'tag_id': tag.id, 'kind': 'series', 'tmdb_id': 1399, 'next': SERIES_PAGE}))

    assert tags_on(me, series) == ['with family']
    assert 'aria-label="Remove the tag with family"' in page


def test_a_new_tag_on_a_titles_page_is_made_and_put_on_the_title(me, movie):
    response = create(me, 'comfort', next_page=MOVIE_PAGE, kind='movie', tmdb_id=603)

    assert response['Location'] == MOVIE_PAGE
    assert names(me) == ['comfort']
    assert tags_on(me, movie) == ['comfort']


def test_a_new_tag_with_the_name_of_one_i_have_puts_that_one_on_the_title(me, movie):
    Tag.objects.create(user=me.user, name='comfort')

    create(me, 'Comfort', next_page=MOVIE_PAGE, kind='movie', tmdb_id=603)

    assert names(me) == ['comfort']
    assert tags_on(me, movie) == ['comfort']


def test_tagging_a_title_not_saved_yet_saves_it_from_tmdb_first(me, respx_mock):
    route = respx_mock.get(MOVIE_URL).respond(json=MADE_UP_MOVIE)
    tag = Tag.objects.create(user=me.user, name='comfort')

    me.post('/tags/add/', {'tag_id': tag.id, 'kind': 'movie', 'tmdb_id': 603, 'next': MOVIE_PAGE})
    create(me, 'to show a friend', next_page=MOVIE_PAGE, kind='movie', tmdb_id=603)

    movie = Title.objects.get(kind='movie', tmdb_id=603)
    assert movie.title == 'Made-up Movie'
    assert tags_on(me, movie) == ['comfort', 'to show a friend']
    assert route.call_count == 1  # saved once, then used from our own table


def test_when_tmdb_does_not_answer_nothing_is_saved_and_a_friendly_message_shows(me, respx_mock):
    respx_mock.get(MOVIE_URL).mock(side_effect=httpx.ConnectError('no network'))
    tag = Tag.objects.create(user=me.user, name='comfort')

    response = me.post('/tags/add/', {'tag_id': tag.id, 'kind': 'movie', 'tmdb_id': 603, 'next': '/profile/'})
    create(me, 'new one', kind='movie', tmdb_id=603)

    assert 'Could not reach TMDB' in page_after(me, response)
    assert not Title.objects.exists()
    assert not TitleTag.objects.exists()
    assert names(me) == ['comfort']  # the new tag was not made either


# --- each account has its own ---------------------------------------------------------------------


def test_another_account_never_sees_my_tags(me, movie):
    tag = Tag.objects.create(user=me.user, name='my secret label')
    TitleTag.objects.create(tag=tag, title=movie)
    friend = make_client('friend')

    assert 'my secret label' not in friend.get('/profile/').content.decode()
    assert 'my secret label' not in friend.get(MOVIE_PAGE).content.decode()
    # And the same name is free for them.
    create(friend, 'my secret label')
    assert names(friend) == ['my secret label']


def test_another_account_cannot_touch_my_tags(me, movie):
    tag = Tag.objects.create(user=me.user, name='comfort')
    TitleTag.objects.create(tag=tag, title=movie)
    before = everything(me)
    friend = make_client('friend')
    title = {'kind': 'movie', 'tmdb_id': 603}

    answers = [
        friend.post('/tags/rename/', {'tag_id': tag.id, 'name': 'stolen'}),
        friend.post('/tags/remove/', {'tag_id': tag.id, **title}),
        friend.post('/tags/add/', {'tag_id': tag.id, **title}),
        friend.post('/tags/delete/', {'tag_id': tag.id}),
    ]

    assert [answer.status_code for answer in answers] == [404] * 4
    assert everything(me) == before


# --- the demo -------------------------------------------------------------------------------------


def test_in_the_demo_only_making_and_adding_a_tag_count_as_changes(me, movie, settings):
    settings.DEMO_MODE = True
    settings.DEMO_CHANGES_PER_DAY = 2
    create(me, 'comfort')
    tag = Tag.objects.get(user=me.user)
    title = {'tag_id': tag.id, 'kind': 'movie', 'tmdb_id': 603}
    me.post('/tags/add/', title)

    # The limit is reached, but renaming, removing and deleting still work and are not counted.
    create(me, 'refused')
    me.post('/tags/rename/', {'tag_id': tag.id, 'name': 'cosy'})
    me.post('/tags/remove/', title)
    assert names(me) == ['cosy']
    assert tags_on(me, movie) == []
    me.post('/tags/delete/', {'tag_id': tag.id})
    assert names(me) == []
    assert DemoEvent.objects.filter(kind=DemoEvent.Kind.CHANGE, user=me.user).count() == 2
