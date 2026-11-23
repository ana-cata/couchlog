"""Filters on the Movies and Series lists (card #120): by genre, by my rating and by my tag, and a sort by year.

The choices go in the page's address, so Back and a bookmark keep them. Only my own ratings and tags count. Filters
only change what is shown, never my data, so there is nothing to undo: clearing them shows the whole list again."""

import datetime
import re

import pytest
import time_machine
from django.contrib.auth.models import User
from django.test import Client

from core.models import (
    DroppedSeries,
    Episode,
    Profile,
    Rating,
    Tag,
    Title,
    TitleTag,
    ToWatchItem,
    Watch,
)

# The fixed "now" for every test here.
NOW = datetime.datetime(2026, 11, 1, 20, 0, tzinfo=datetime.UTC)
LONG_AGO = datetime.date(2011, 4, 17)

DRAMA = {'id': 18, 'name': 'Drama'}
COMEDY = {'id': 35, 'name': 'Comedy'}
HORROR = {'id': 27, 'name': 'Horror'}
WESTERN = {'id': 37, 'name': 'Western'}


@pytest.fixture(autouse=True)
def clock():
    with time_machine.travel(NOW, tick=False) as traveller:
        yield traveller


def make_user(name):
    user = User.objects.create_user(username=name, password='made-up-password')
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    return user


@pytest.fixture
def me(db):
    return make_user('made-up-user')


@pytest.fixture
def other(db):
    return make_user('someone-else')


def client_for(user):
    client = Client()
    client.force_login(user)
    return client


def make_title(tmdb_id, year, genres, kind='movie', status=''):
    return Title.objects.create(
        kind=kind, tmdb_id=tmdb_id, title=f'Made-up {kind} {tmdb_id}', year=year, genres=genres, status=status
    )


def on_to_watch(user, title, minutes):
    """Put a title on the To Watch list, added `minutes` after the first one (the list shows the newest first)."""
    return ToWatchItem.objects.create(user=user, title=title, added_at=NOW + datetime.timedelta(minutes=minutes))


def tag(user, name, *titles):
    made = Tag.objects.create(user=user, name=name)
    for title in titles:
        TitleTag.objects.create(tag=made, title=title)
    return made


def tiles(html):
    """The TMDB ids of the tiles on a page, in their order."""
    return [int(tmdb_id) for tmdb_id in re.findall(r'class="tile" href="/(?:movie|series)/(\d+)/"', html)]


def page(client, address):
    response = client.get(address)
    assert response.status_code == 200
    return response.content.decode()


# --- Movies → To Watch, with four films ---------------------------------------------------------------------------
#
#  film  year  genres          added    my rating           my tag    someone else's
#  1     2001  Drama           first    5 stars             comfort
#  2     1999  Comedy, Drama   second   3 stars                       their tag
#  3     -     Comedy          third    a note, no stars    comfort
#  4     2001  Horror          last     -                             5 stars, their tag
#
# The list's own order is the newest added first: 4, 3, 2, 1.


@pytest.fixture
def films(me, other):
    one = make_title(1, '2001', [DRAMA])
    two = make_title(2, '1999', [COMEDY, DRAMA])
    three = make_title(3, '', [COMEDY])
    four = make_title(4, '2001', [HORROR])
    for minutes, title in enumerate((one, two, three, four)):
        on_to_watch(me, title, minutes)
    Rating.objects.create(user=me, title=one, stars=5)
    Rating.objects.create(user=me, title=two, stars=3)
    Rating.objects.create(user=me, title=three, note='Made-up note.')
    Rating.objects.create(user=other, title=four, stars=5)
    comfort = tag(me, 'comfort', one, three)
    theirs = tag(other, 'their tag', two, four)
    return {'comfort': comfort, 'theirs': theirs}


def test_without_filters_the_list_keeps_its_own_order(me, films):
    html = page(client_for(me), '/movies/')

    assert tiles(html) == [4, 3, 2, 1]
    assert 'Clear filters' not in html
    assert '<details class="list-filters">' in html  # folded on a phone until opened


def test_genre_alone(me, films):
    client = client_for(me)

    assert tiles(page(client, '/movies/?genre=18')) == [2, 1]
    assert tiles(page(client, '/movies/?genre=35')) == [3, 2]
    assert tiles(page(client, '/movies/?genre=27')) == [4]


def test_only_the_genres_found_in_that_list_are_offered(me, films):
    # A Western in History is not on To Watch, so To Watch does not offer it.
    western = make_title(5, '1960', [WESTERN])
    Watch.objects.create(user=me, title=western, watched_on=LONG_AGO)

    to_watch = page(client_for(me), '/movies/')
    history = page(client_for(me), '/movies/history/')

    assert re.findall(r'<option value="(\d+)"', to_watch.split('name="genre"')[1].split('</select>')[0]) == [
        '35',
        '18',
        '27',
    ]  # by name: Comedy, Drama, Horror
    assert 'Western' not in to_watch
    assert '<option value="37">Western</option>' in history


def test_rating_alone(me, films):
    client = client_for(me)

    assert tiles(page(client, '/movies/?rating=5')) == [1]
    assert tiles(page(client, '/movies/?rating=4')) == [1]
    assert tiles(page(client, '/movies/?rating=3')) == [2, 1]
    assert tiles(page(client, '/movies/?rating=1')) == [2, 1]
    # A note without stars is not a rating, and someone else's 5 stars on film 4 do not count.
    assert tiles(page(client, '/movies/?rating=none')) == [4, 3]


def test_tag_alone(me, films):
    html = page(client_for(me), f'/movies/?tag={films["comfort"].id}')

    assert tiles(html) == [3, 1]


def test_only_my_own_tags_are_offered_and_count(me, films):
    client = client_for(me)

    html = page(client, f'/movies/?tag={films["theirs"].id}')

    # Someone else's tag in the address is ignored, as if no tag was chosen.
    assert tiles(html) == [4, 3, 2, 1]
    assert '>comfort</option>' in html
    assert 'their tag' not in html


def test_the_tag_box_is_left_out_when_i_have_no_tags(other, films):
    on_to_watch(other, Title.objects.get(tmdb_id=1), 0)
    Tag.objects.filter(user=other).delete()

    html = page(client_for(other), '/movies/')

    assert 'name="tag"' not in html
    assert 'name="rating"' in html and 'name="sort"' in html


def test_the_filters_together(me, films):
    client = client_for(me)
    comfort = films['comfort'].id

    assert tiles(page(client, f'/movies/?genre=18&rating=1&tag={comfort}&sort=oldest')) == [1]
    assert tiles(page(client, '/movies/?genre=35&rating=none')) == [3]
    assert tiles(page(client, f'/movies/?genre=35&tag={comfort}&sort=newest')) == [3]


def test_sort_by_year_puts_a_title_with_no_year_last_and_keeps_the_list_order_within_a_year(me, films):
    client = client_for(me)

    # Films 4 and 1 are both from 2001: 4 was added last, so it stays before 1 in both sorts.
    assert tiles(page(client, '/movies/?sort=newest')) == [4, 1, 2, 3]
    assert tiles(page(client, '/movies/?sort=oldest')) == [2, 4, 1, 3]


def test_no_match_says_so_with_a_link_that_clears_the_filters(me, films):
    client = client_for(me)

    html = page(client, '/movies/?genre=27&rating=5')

    assert tiles(html) == []
    assert 'No titles match these filters.' in html
    assert '<a href="/movies/">Clear filters</a>' in html
    # Clearing is the page's own address with nothing chosen: the whole list again.
    assert tiles(page(client, '/movies/')) == [4, 3, 2, 1]


def test_a_filtered_list_that_matches_has_the_clear_link_too(me, films):
    html = page(client_for(me), '/movies/?genre=18')

    assert 'No titles match' not in html
    assert '<a href="/movies/">Clear filters</a>' in html


def test_the_choices_stay_in_the_address_and_show_as_chosen(me, films):
    comfort = films['comfort'].id

    html = page(client_for(me), f'/movies/?genre=18&rating=3&tag={comfort}&sort=newest')

    assert '<option value="18" selected>Drama</option>' in html
    assert '<option value="3" selected>3 stars or more</option>' in html
    assert f'<option value="{comfort}" selected>comfort</option>' in html
    assert '<option value="newest" selected>Year, newest first</option>' in html
    assert '<details class="list-filters" open>' in html  # a filter is on, so the bar is open even on a phone


def test_a_value_that_is_not_a_choice_is_ignored(me, films):
    html = page(client_for(me), '/movies/?genre=99&rating=6&tag=nope&sort=sideways')

    assert tiles(html) == [4, 3, 2, 1]
    assert 'Clear filters' not in html


def test_the_bar_is_a_plain_form_that_htmx_can_send_to_update_only_the_list(me, films):
    html = page(client_for(me), '/movies/')

    assert '<form method="get" action="/movies/" hx-get="/movies/"' in html
    assert 'hx-target="#list" hx-select="#list"' in html
    assert 'hx-push-url="true"' in html  # the address changes with the choices
    assert '<noscript><button type="submit" class="outline secondary">Show</button></noscript>' in html
    assert '<div id="list">' in html


def test_filtering_never_changes_my_data(me, films):
    def everything():
        return [
            list(model.objects.order_by('id').values())
            for model in (Title, ToWatchItem, Rating, Tag, TitleTag, Watch, DroppedSeries)
        ]

    before = everything()
    page(client_for(me), f'/movies/?genre=18&rating=none&tag={films["comfort"].id}&sort=oldest')

    assert everything() == before


def test_an_empty_list_has_no_filter_bar(me):
    html = page(client_for(me), '/movies/?genre=18')

    assert 'list-filters' not in html
    assert 'Keep the movies you want to see here.' in html


# --- every list on Movies and Series ----------------------------------------------------------------------------
#
# Each list gets two titles: a Drama from 2001 I gave 4 stars, and a Comedy from 1999 with my tag. The Drama is the
# newer one in the list's own order.


def put_on_list(user, address, title, minutes):
    """Put a title on the list at `address`, `minutes` later than the first one."""
    later = NOW + datetime.timedelta(minutes=minutes)
    if address in ('/movies/', '/series/'):
        on_to_watch(user, title, minutes)
    elif address == '/movies/history/':
        Watch.objects.create(user=user, title=title, watched_on=LONG_AGO, created_at=later)
    elif address == '/series/dropped/':
        DroppedSeries.objects.create(user=user, title=title, dropped_at=later)
    else:  # Watching or Finished: one aired episode, watched (the status says which tab)
        episode = Episode.objects.create(
            title=title, tmdb_id=title.tmdb_id * 100, season_number=1, episode_number=1, air_date=LONG_AGO
        )
        Watch.objects.create(user=user, title=title, episode=episode, watched_on=LONG_AGO, created_at=later)


LISTS = {
    '/movies/': ('movie', ''),
    '/movies/history/': ('movie', ''),
    '/series/watching/': ('series', 'Returning Series'),
    '/series/': ('series', 'Returning Series'),
    '/series/finished/': ('series', 'Ended'),
    '/series/dropped/': ('series', 'Returning Series'),
}


@pytest.mark.parametrize('address', LISTS)
def test_every_list_can_be_filtered_and_sorted_and_cleared(me, other, address):
    kind, status = LISTS[address]
    comedy = make_title(10, '1999', [COMEDY], kind=kind, status=status)
    drama = make_title(20, '2001', [DRAMA], kind=kind, status=status)
    put_on_list(me, address, comedy, 0)
    put_on_list(me, address, drama, 1)
    Rating.objects.create(user=me, title=drama, stars=4)
    Rating.objects.create(user=other, title=comedy, stars=5)
    mine = tag(me, 'mine', comedy)
    tag(other, 'theirs', drama)
    client = client_for(me)

    assert tiles(page(client, address)) == [20, 10]
    assert tiles(page(client, f'{address}?genre=18')) == [20]
    assert tiles(page(client, f'{address}?rating=4')) == [20]  # someone else's 5 stars on the Comedy do not count
    assert tiles(page(client, f'{address}?rating=none')) == [10]
    assert tiles(page(client, f'{address}?tag={mine.id}')) == [10]
    assert tiles(page(client, f'{address}?sort=oldest')) == [10, 20]
    assert tiles(page(client, f'{address}?sort=newest')) == [20, 10]
    assert tiles(page(client, f'{address}?genre=35&rating=1&tag={mine.id}')) == []
    empty = page(client, f'{address}?genre=18&tag={mine.id}')
    assert 'No titles match these filters.' in empty
    assert f'<a href="{address}">Clear filters</a>' in empty
    assert tiles(page(client, address)) == [20, 10]
