"""The series page, looked at in a real browser because where things sit is what these tests are about: the bar and
the small buttons under the poster, the season's "3 of 10 episodes" line, and the rating box (no arrow on the Rate
button, and the edit pencil right after the saved note).

The titles and episodes are made up and saved already, with fresh episodes, so the page never asks TMDB."""

import datetime
import os

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from playwright.sync_api import expect

from core.models import Episode, Profile, Rating, Title, ToWatchItem, Watch

# The browser's driver runs inside an event loop, and Django refuses database calls from
# there unless told it is fine. It is fine in a test.
os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')

PAGE = '/series/1399/'
LONG_AGO = datetime.date(2020, 1, 1)


@pytest.fixture
def me(db):
    user = User.objects.create_user(username='made-up-user', password='made-up-password')
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    return user


@pytest.fixture
def series(me):
    """A series on the To Watch list: two episodes have aired and a third is still to come."""
    series = Title.objects.create(
        kind='series', tmdb_id=1399, title='Made-up Series', status='Returning Series', episodes_refreshed_at=timezone.now()
    )
    soon = datetime.date.today() + datetime.timedelta(days=30)
    for number, air_date in ((1, LONG_AGO), (2, LONG_AGO), (3, soon)):
        Episode.objects.create(
            title=series, tmdb_id=1399000 + number, season_number=1, episode_number=number, name=f'Name {number}', air_date=air_date
        )
    ToWatchItem.objects.create(user=me, title=series)
    return series


@pytest.fixture
def opened(live_server, page, series):
    page.goto(live_server.url)
    page.get_by_label('Username').fill('made-up-user')
    page.get_by_label('Password').fill('made-up-password')
    page.get_by_role('button', name='Log in').click()
    page.goto(live_server.url + PAGE)
    page.wait_for_load_state('load')
    return page


def box(locator):
    return locator.bounding_box()


def start(series, user):
    """Mark the first episode as watched, so the series is one I started."""
    Watch.objects.create(user=user, title=series, episode=series.episodes.get(episode_number=1), watched_on=LONG_AGO)


# --- under the poster ---------------------------------------------------------------------------------------------


def test_a_series_only_on_the_list_has_its_bar_and_remove_button_under_the_poster_and_no_stop_watching(opened):
    page = opened
    poster = box(page.locator('.title-poster .poster'))
    bar = box(page.locator('#progress-series progress'))
    to_watch = box(page.get_by_role('button', name='Remove from To Watch'))

    expect(page.locator('#progress-series')).to_contain_text('0 of 3 episodes')
    assert poster['y'] + poster['height'] <= bar['y'] < to_watch['y']  # the bar, then the button
    for part in (bar, to_watch):
        assert part['x'] < poster['x'] + poster['width']  # both in the poster's column, not next to the title
    assert bar['width'] <= poster['width']  # a small bar, no wider than the poster
    # Nothing is marked, so there is nothing to stop: it leaves the list with the button above.
    expect(page.get_by_role('button', name='Stop watching')).to_have_count(0)
    # The bar is not above the seasons any more.
    expect(page.locator('#progress-series')).to_have_count(1)


def test_a_series_i_started_has_its_bar_then_stop_watching_under_the_poster(opened, series, me):
    start(series, me)
    page = opened
    page.reload()
    poster = box(page.locator('.title-poster .poster'))
    bar = box(page.locator('#progress-series progress'))
    stop = box(page.get_by_role('button', name='Stop watching'))

    expect(page.locator('#progress-series')).to_contain_text('1 of 3 episodes')
    assert poster['y'] + poster['height'] <= bar['y'] < stop['y']  # the bar, then the button
    for part in (bar, stop):
        assert part['x'] < poster['x'] + poster['width']
    # I started it, so it is under Watching: no To Watch button, and the right column has no second Stop watching.
    expect(page.get_by_role('button', name='Remove from To Watch')).to_have_count(0)
    expect(page.get_by_role('button', name='Stop watching')).to_have_count(1)


def test_a_dropped_series_has_bring_back_and_remove_from_all_lists_under_the_poster(opened, series, me):
    start(series, me)
    page = opened
    page.reload()
    page.get_by_role('button', name='Stop watching').click()
    expect(page.get_by_role('button', name='Bring back')).to_be_visible()

    poster = box(page.locator('.title-poster .poster'))
    for name in ('Bring back', 'Remove from all lists'):
        button = box(page.get_by_role('button', name=name))
        assert button['y'] > poster['y'] + poster['height']
        assert button['x'] < poster['x'] + poster['width']


# --- the season's line --------------------------------------------------------------------------------------------


def test_the_season_line_says_how_many_of_all_its_episodes_are_watched(opened):
    page = opened
    line = page.locator('#progress-season-1')

    # Two have aired and one is still to come, and all three count.
    expect(line).to_contain_text('Season 1')
    expect(line).to_contain_text('0 of 3 episodes')
    assert 'aired' not in line.inner_text()

    page.get_by_role('button', name='Mark episode 1 as watched').click()
    expect(line).to_contain_text('1 of 3 episodes')
    expect(page.locator('#progress-series')).to_contain_text('1 of 3 episodes')


# --- the rating box -----------------------------------------------------------------------------------------------


def test_the_rate_button_has_no_arrow_and_opens_the_form(opened):
    page = opened
    button = page.locator('summary.rating-open')

    expect(button).to_have_text('Rate it or add a note')
    arrow = button.evaluate('element => getComputedStyle(element, "::after").display')
    assert arrow == 'none'
    expect(page.locator('.rating-section form')).to_be_hidden()

    button.click()

    expect(page.locator('.rating-section form')).to_be_visible()


def test_the_edit_pencil_sits_right_after_the_saved_note(opened, series, me):
    Rating.objects.create(user=me, title=series, stars=4, note='Loved the fights.')
    page = opened
    page.reload()

    note, pencil = box(page.locator('.rating-note')), box(page.locator('summary.rating-edit'))

    assert pencil['x'] >= note['x'] + note['width'] - 2  # to the right of the note, not under it
    assert note['y'] - 4 <= pencil['y'] + pencil['height'] / 2 <= note['y'] + note['height'] + 4  # on the same line


def test_the_pencil_follows_the_last_line_of_a_long_note_on_a_narrow_screen(opened, series, me):
    Rating.objects.create(user=me, title=series, stars=None, note='A long note that wraps over several lines. ' * 6)
    page = opened
    page.set_viewport_size({'width': 360, 'height': 800})
    page.reload()

    note, pencil = box(page.locator('.rating-note')), box(page.locator('summary.rating-edit'))
    middle = pencil['y'] + pencil['height'] / 2

    assert note['height'] > 80  # the note wraps over several lines
    assert note['y'] + note['height'] - 40 <= middle <= note['y'] + note['height'] + 10  # level with the last one


def test_the_pencil_opens_the_form(opened, series, me):
    Rating.objects.create(user=me, title=series, stars=4, note='Loved the fights.')
    page = opened
    page.reload()
    expect(page.locator('.rating-section form')).to_be_hidden()

    page.locator('summary.rating-edit').click()

    expect(page.locator('.rating-section form')).to_be_visible()
