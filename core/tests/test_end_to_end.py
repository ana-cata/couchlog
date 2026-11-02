"""The first end-to-end test: a real browser walks through the app, as I would."""

import datetime
import os
import re

from django.contrib.auth.models import User
from django.utils import timezone
from playwright.sync_api import expect

from core.models import Episode, Profile, Title, ToWatchItem, Watch

# The browser's driver runs inside an event loop, and Django refuses database calls from
# there unless told it is fine. It is fine in a test.
os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')

# Made-up TMDB answers. The server side of this test never calls the real TMDB either.
MADE_UP_MOVIE = {
    'id': 603,
    'title': 'Made-up Movie',
    'release_date': '1999-03-31',
    'poster_path': '/made-up-movie.jpg',
    'overview': 'A made-up story about a movie.',
}


def test_log_in_search_add_a_title_then_remove_it_and_undo(live_server, page, respx_mock, settings, monkeypatch):
    # A long window, so a slow machine can never run out of undo time in the middle of this test.
    monkeypatch.setattr('core.views.UNDO_WINDOW', datetime.timedelta(minutes=5))
    settings.TMDB_API_KEY = 'made-up-secret-key'
    user = User.objects.create_user(username='made-up-user', password='made-up-password')
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    # The app's server asks TMDB (made up here). The browser's poster downloads are blocked.
    respx_mock.get('https://api.themoviedb.org/3/search/multi').respond(
        json={'page': 1, 'results': [{'media_type': 'movie', **MADE_UP_MOVIE}]}
    )
    # Adding a movie also collects its release dates for the Calendar (from this same answer); here TMDB has none.
    respx_mock.get('https://api.themoviedb.org/3/movie/603').respond(json=MADE_UP_MOVIE)
    page.route('https://image.tmdb.org/**', lambda route: route.abort())

    # Log in.
    page.goto(live_server.url)
    page.get_by_label('Username').fill('made-up-user')
    page.get_by_label('Password').fill('made-up-password')
    page.get_by_role('button', name='Log in').click()

    # Search: results appear as I type, with no button pressed.
    page.get_by_role('link', name='Search', exact=True).click()
    # htmx starts when the page has loaded. Typing before that is ignored, and a robot types much
    # faster than a person does, so wait for the page first (this was flaky on GitHub's slower machine).
    page.wait_for_load_state('load')
    page.get_by_role('searchbox').press_sequentially('made-up')
    expect(page.locator('.tile')).to_have_count(1)
    expect(page.locator('.tile')).to_contain_text('Made-up Movie')

    # Add it. Only the button changes; the results stay where they are.
    page.get_by_role('button', name='Add to To Watch').click()
    expect(page.get_by_role('button', name='Remove from To Watch')).to_be_visible()

    # It is on the Movies section's To Watch tab, and still there after reloading. The Series section is empty.
    page.get_by_role('link', name='Movies', exact=True).click()
    expect(page.locator('.tile')).to_have_count(1)
    expect(page.locator('.tile')).to_contain_text('Made-up Movie')
    page.reload()
    expect(page.locator('.tile')).to_have_count(1)
    page.get_by_role('link', name='Series', exact=True).click()
    page.get_by_role('link', name='To Watch', exact=True).click()
    expect(page.get_by_text('No series on your To Watch list yet')).to_be_visible()
    expect(page.locator('.tile')).to_have_count(0)
    page.get_by_role('link', name='Movies', exact=True).click()

    # Remove it: it leaves the list and is offered under "Recently removed".
    page.get_by_role('button', name='Remove from To Watch').click()
    expect(page.locator('.tile')).to_have_count(0)
    expect(page.get_by_role('heading', name='Recently removed')).to_be_visible()
    # No "Removed ..." notice at the top: the list itself shows it.
    expect(page.get_by_text('Removed “')).to_have_count(0)

    # Undo brings it back.
    page.get_by_role('button', name='Undo').click()
    expect(page.locator('.tile')).to_have_count(1)
    expect(page.locator('.tile')).to_contain_text('Made-up Movie')

    # Opening the title shows the same button under the poster, and it works in place.
    page.locator('.tile').click()
    expect(page.get_by_role('heading', name='Made-up Movie')).to_be_visible()
    expect(page.get_by_role('button', name='Remove from To Watch')).to_be_visible()
    page.get_by_role('button', name='Remove from To Watch').click()
    expect(page.get_by_role('button', name='Add to To Watch')).to_be_visible()
    page.get_by_role('button', name='Add to To Watch').click()
    expect(page.get_by_role('button', name='Remove from To Watch')).to_be_visible()


def test_every_tile_is_the_same_size_whatever_the_title(live_server, page, respx_mock, settings):
    settings.TMDB_API_KEY = 'made-up-secret-key'
    user = User.objects.create_user(username='made-up-user', password='made-up-password')
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    # Short, long, very long and undated titles, so the tiles would be uneven if nothing evened them out.
    names = [
        'Up',
        'A made-up film with a fairly long name',
        'A made-up title that is so long that it could never fit on two lines of a small tile',
        'Another',
    ]
    found = [{'media_type': 'movie', 'id': number, 'title': name} for number, name in enumerate(names, start=1)]
    respx_mock.get('https://api.themoviedb.org/3/search/multi').respond(json={'page': 1, 'results': found})
    # Three narrow tiles per row (the narrowest they get), so there is more than one row to compare.
    page.set_viewport_size({'width': 500, 'height': 900})

    page.goto(live_server.url)
    page.get_by_label('Username').fill('made-up-user')
    page.get_by_label('Password').fill('made-up-password')
    page.get_by_role('button', name='Log in').click()
    page.goto(live_server.url + '/search/?q=made-up')
    expect(page.locator('.tile')).to_have_count(4)

    sizes = page.locator('.results li').evaluate_all(
        """tiles => tiles.map(tile => {
            const box = tile.getBoundingClientRect();
            const button = tile.querySelector('button').getBoundingClientRect();
            return [Math.round(box.width), Math.round(box.height),
                    Math.round(button.top - box.top), Math.round(button.height)];
        })"""
    )

    # Same width, same height, and the button in the same place in every tile.
    assert len(sizes) == 4
    assert len(set(map(tuple, sizes))) == 1, sizes

    # The year line ("Year unknown · Movie" here) is never cut off. The page's text grows with the
    # screen but the tiles stay narrow, so a wide desktop screen is where it is tightest.
    page.set_viewport_size({'width': 1280, 'height': 900})
    cut_off = page.locator('.tile small').evaluate_all('lines => lines.some(line => line.scrollWidth > line.clientWidth)')
    assert not cut_off


def test_a_page_left_open_stops_offering_undo_when_time_is_up(live_server, page, monkeypatch):
    # A shorter window than the real 10 seconds, so the test is quick.
    monkeypatch.setattr('core.views.UNDO_WINDOW', datetime.timedelta(seconds=3))
    user = User.objects.create_user(username='made-up-user', password='made-up-password')
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    title = Title.objects.create(kind='series', tmdb_id=1399, title='Made-up Series', year='2011')
    ToWatchItem.objects.create(user=user, title=title)

    page.goto(live_server.url)
    page.get_by_label('Username').fill('made-up-user')
    page.get_by_label('Password').fill('made-up-password')
    page.get_by_role('button', name='Log in').click()
    page.get_by_role('link', name='Series', exact=True).click()
    page.get_by_role('link', name='To Watch', exact=True).click()
    page.get_by_role('button', name='Remove from To Watch').click()
    expect(page.get_by_role('heading', name='Recently removed')).to_be_visible()
    expect(page.get_by_role('button', name='Undo')).to_be_visible()

    # Now leave the page alone: no reload, no click. The block goes away by itself.
    expect(page.get_by_role('heading', name='Recently removed')).to_be_hidden(timeout=10_000)
    expect(page.get_by_role('button', name='Undo')).to_have_count(0)
    # The title is not back on the list, and a reload agrees.
    expect(page.locator('.tile')).to_have_count(0)
    page.reload()
    expect(page.get_by_role('heading', name='Recently removed')).to_have_count(0)
    expect(page.get_by_text('No series on your To Watch list yet')).to_be_visible()


def test_mark_a_movie_as_watched_see_it_in_history_then_undo(live_server, page, respx_mock, settings):
    settings.TMDB_API_KEY = 'made-up-secret-key'
    user = User.objects.create_user(username='made-up-user', password='made-up-password')
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    title = Title.objects.create(kind='movie', tmdb_id=603, title='Made-up Movie', year='1999')
    ToWatchItem.objects.create(user=user, title=title)
    respx_mock.get('https://api.themoviedb.org/3/movie/603').respond(json=MADE_UP_MOVIE)
    page.route('https://image.tmdb.org/**', lambda route: route.abort())

    page.goto(live_server.url)
    page.get_by_label('Username').fill('made-up-user')
    page.get_by_label('Password').fill('made-up-password')
    page.get_by_role('button', name='Log in').click()

    # Open the movie from the To Watch list and mark it as watched (the date box starts on today).
    page.get_by_role('link', name='Movies', exact=True).click()
    page.locator('.tile').click()
    page.get_by_role('button', name='Mark as watched').click()
    expect(page.get_by_text('Marked “Made-up Movie” as watched.')).to_be_visible()
    expect(page.get_by_role('button', name='Mark as not watched')).to_be_visible()

    # It is in History (a tab of Movies) with a date, and it has left the To Watch tab.
    page.get_by_role('link', name='Movies', exact=True).click()
    page.get_by_role('link', name='History', exact=True).click()
    expect(page.locator('.tile')).to_contain_text('Made-up Movie')
    expect(page.get_by_text(re.compile(r'Watched \d{1,2} \w{3} \d{4}'))).to_be_visible()
    page.get_by_role('link', name='To Watch', exact=True).click()
    expect(page.locator('.tile')).to_have_count(0)
    expect(page.get_by_role('heading', name='Recently removed')).to_have_count(0)

    # Undo from History: it leaves History and is back on To Watch.
    page.get_by_role('link', name='History', exact=True).click()
    page.get_by_role('button', name='Mark as not watched').click()
    expect(page.get_by_text('Nothing in your history yet')).to_be_visible()
    page.get_by_role('link', name='To Watch', exact=True).click()
    expect(page.locator('.tile')).to_contain_text('Made-up Movie')


def test_open_a_series_tick_an_episode_and_untick_it(live_server, page, respx_mock, settings):
    settings.TMDB_API_KEY = 'made-up-secret-key'
    user = User.objects.create_user(username='made-up-user', password='made-up-password')
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    show = Title.objects.create(kind='series', tmdb_id=1399, title='Made-up Series', year='2011')
    ToWatchItem.objects.create(user=user, title=show)
    respx_mock.get('https://api.themoviedb.org/3/tv/1399').respond(
        json={'id': 1399, 'name': 'Made-up Series', 'seasons': [{'season_number': 1}]}
    )
    episodes = [
        {'id': 6001, 'season_number': 1, 'episode_number': 1, 'name': 'Made-up pilot', 'air_date': '2011-04-17'},
        {'id': 6002, 'season_number': 1, 'episode_number': 2, 'name': 'Made-up future', 'air_date': '2999-01-01'},
    ]
    respx_mock.get('https://api.themoviedb.org/3/tv/1399/season/1').respond(
        json={'season_number': 1, 'episodes': episodes}
    )
    page.route('https://image.tmdb.org/**', lambda route: route.abort())

    page.goto(live_server.url)
    page.get_by_label('Username').fill('made-up-user')
    page.get_by_label('Password').fill('made-up-password')
    page.get_by_role('button', name='Log in').click()

    # Open the series from the Series section's To Watch tab: its season is listed, and only the episode that has aired has a button.
    page.get_by_role('link', name='Series', exact=True).click()
    page.get_by_role('link', name='To Watch', exact=True).click()
    page.locator('.tile').click()
    expect(page.get_by_text('Made-up pilot')).to_be_visible()
    expect(page.get_by_text('Airs 1 Jan 2999')).to_be_visible()
    expect(page.get_by_role('button', name=re.compile(r'Mark episode \d as watched'))).to_have_count(1)

    # Tick it: the circle turns green (the button now offers "not watched"), and it is still green after reloading.
    page.get_by_role('button', name='Mark episode 1 as watched').click()
    expect(page.get_by_role('button', name='Mark episode 1 as not watched')).to_be_visible()
    page.reload()
    expect(page.get_by_role('button', name='Mark episode 1 as not watched')).to_be_visible()

    # Untick it: back to gray.
    page.get_by_role('button', name='Mark episode 1 as not watched').click()
    expect(page.get_by_role('button', name='Mark episode 1 as watched')).to_be_visible()


def test_ticking_an_episode_does_not_move_the_page(live_server, page, respx_mock, settings):
    settings.TMDB_API_KEY = 'made-up-secret-key'
    user = User.objects.create_user(username='made-up-user', password='made-up-password')
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    show = Title.objects.create(kind='series', tmdb_id=1399, title='Made-up Series', year='2011')
    ToWatchItem.objects.create(user=user, title=show)
    respx_mock.get('https://api.themoviedb.org/3/tv/1399').respond(
        json={'id': 1399, 'name': 'Made-up Series', 'seasons': [{'season_number': 1}]}
    )
    # A long season, so the page is much taller than the window and has to be scrolled.
    episodes = [
        {'id': 6000 + number, 'season_number': 1, 'episode_number': number, 'name': f'Made-up episode {number}',
         'air_date': '2011-04-17'}
        for number in range(1, 41)
    ]
    respx_mock.get('https://api.themoviedb.org/3/tv/1399/season/1').respond(
        json={'season_number': 1, 'episodes': episodes}
    )
    page.route('https://image.tmdb.org/**', lambda route: route.abort())
    page.set_viewport_size({'width': 800, 'height': 600})

    page.goto(live_server.url)
    page.get_by_label('Username').fill('made-up-user')
    page.get_by_label('Password').fill('made-up-password')
    page.get_by_role('button', name='Log in').click()
    page.goto(live_server.url + '/series/1399/')
    page.wait_for_load_state('load')  # htmx starts when the page has loaded

    # Scroll to the bottom of the season and tick the last episode.
    button = page.get_by_role('button', name='Mark episode 40 as watched')
    button.scroll_into_view_if_needed()
    address_before = page.url
    scrolled_before = page.evaluate('window.scrollY')
    assert scrolled_before > 500  # it really is scrolled down
    button.click()
    # It is the first episode marked in the series, so the pop-up asks about the earlier ones. Only this one.
    page.get_by_role('dialog').get_by_role('button', name='No, only S1E40').click()
    expect(page.get_by_role('button', name='Mark episode 40 as not watched')).to_be_visible()

    # Nothing moved: same place on the page, same address (no jump to the episode), and no reload.
    assert abs(page.evaluate('window.scrollY') - scrolled_before) < 2
    assert page.url == address_before
    # The same goes for un-ticking it.
    page.get_by_role('button', name='Mark episode 40 as not watched').click()
    expect(page.get_by_role('button', name='Mark episode 40 as watched')).to_be_visible()
    assert abs(page.evaluate('window.scrollY') - scrolled_before) < 2


def test_the_first_mark_asks_and_the_season_button_marks_and_un_marks_a_season_without_moving_the_page(
    live_server, page, respx_mock, settings
):
    settings.TMDB_API_KEY = 'made-up-secret-key'
    user = User.objects.create_user(username='made-up-user', password='made-up-password')
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    show = Title.objects.create(kind='series', tmdb_id=1399, title='Made-up Series', year='2011')
    ToWatchItem.objects.create(user=user, title=show)
    respx_mock.get('https://api.themoviedb.org/3/tv/1399').respond(
        json={'id': 1399, 'name': 'Made-up Series', 'seasons': [{'season_number': 1}, {'season_number': 2}]}
    )
    # A long first season, so the page is much taller than the window and has to be scrolled, and a short second one.
    season_one = [
        {'id': 6000 + number, 'season_number': 1, 'episode_number': number, 'name': f'Made-up episode {number}',
         'air_date': '2011-04-17'}
        for number in range(1, 41)
    ]
    season_two = [
        {'id': 6100 + number, 'season_number': 2, 'episode_number': number, 'name': f'Made-up episode {number}',
         'air_date': '2012-04-17'}
        for number in range(1, 3)
    ]
    respx_mock.get('https://api.themoviedb.org/3/tv/1399/season/1').respond(
        json={'season_number': 1, 'episodes': season_one}
    )
    respx_mock.get('https://api.themoviedb.org/3/tv/1399/season/2').respond(
        json={'season_number': 2, 'episodes': season_two}
    )
    page.route('https://image.tmdb.org/**', lambda route: route.abort())
    # Tall enough that the season button is on screen at the top of the page (with the rating line above the seasons).
    page.set_viewport_size({'width': 800, 'height': 700})

    page.goto(live_server.url)
    page.get_by_label('Username').fill('made-up-user')
    page.get_by_label('Password').fill('made-up-password')
    page.get_by_role('button', name='Log in').click()
    page.goto(live_server.url + '/series/1399/')
    page.wait_for_load_state('load')  # htmx starts when the page has loaded
    watched = page.locator('.check.watched')

    # Scroll down the long season and press the circle of episode 30, the first episode marked in the series.
    circle = page.get_by_role('button', name='Mark episode 30 as watched')
    circle.scroll_into_view_if_needed()
    address_before = page.url
    scrolled_before = page.evaluate('window.scrollY')
    open_before = page.locator('details[open]').count()
    assert scrolled_before > 500  # it really is scrolled down
    circle.click()

    # A pop-up asks about the earlier episodes. Nothing is saved yet, and Cancel closes it and changes nothing.
    question = page.get_by_role('dialog')
    expect(question.get_by_text('Did you watch the earlier episodes too?')).to_be_visible()
    expect(watched).to_have_count(0)
    question.get_by_role('button', name='Cancel').click()
    expect(question).to_be_hidden()
    expect(watched).to_have_count(0)
    assert abs(page.evaluate('window.scrollY') - scrolled_before) < 2

    # Pressing it again asks again; "Yes" marks episodes 1 to 30.
    circle.click()
    question.get_by_role('button', name='Yes, mark all 30').click()

    # Episodes 1 to 30 are green and the question is gone. There is no notice and no Undo button.
    expect(question).to_be_hidden()
    expect(watched).to_have_count(30)
    expect(page.get_by_role('button', name='Undo')).to_have_count(0)
    # Nothing moved: same place, same address, same seasons open, no reload.
    assert abs(page.evaluate('window.scrollY') - scrolled_before) < 2
    assert page.url == address_before
    assert page.locator('details[open]').count() == open_before

    # Ten episodes are left, so the season button still says "as watched". It marks them, and then turns
    # into "as not watched": pressing the same button again un-marks the whole season.
    page.evaluate('window.scrollTo(0, 0)')
    page.get_by_role('button', name='Mark Season 1 as watched').click()
    expect(watched).to_have_count(40)
    expect(page.get_by_role('button', name='Mark Season 1 as not watched')).to_be_visible()
    expect(page.get_by_role('button', name='Mark Season 1 as watched')).to_have_count(0)
    assert page.evaluate('window.scrollY') == 0
    page.get_by_role('button', name='Mark Season 1 as not watched').click()
    expect(watched).to_have_count(0)
    expect(page.get_by_role('button', name='Mark Season 1 as watched')).to_be_visible()

    # With nothing marked again, the first mark asks again. "No" marks just that episode.
    circle.click()
    question.get_by_role('button', name='No, only S1E30').click()
    expect(question).to_be_hidden()
    expect(watched).to_have_count(1)
    page.get_by_role('button', name='Mark episode 30 as not watched').click()
    expect(watched).to_have_count(0)

    # Mark the whole season again and reload: still marked, and the button still says so.
    page.evaluate('window.scrollTo(0, 0)')
    page.get_by_role('button', name='Mark Season 1 as watched').click()
    expect(watched).to_have_count(40)
    page.reload()
    expect(watched).to_have_count(40)
    expect(page.get_by_role('button', name='Mark Season 1 as not watched')).to_be_visible()
    # Un-mark one by hand: the season is not complete any more, so the button flips back to "as watched".
    page.get_by_role('button', name='Mark episode 40 as not watched').click()
    expect(watched).to_have_count(39)
    expect(page.get_by_role('button', name='Mark Season 1 as watched')).to_be_visible()

    # Watch the season again. It is offered once everything is marked, adds one watch to each episode (the rows say
    # "2×"), and the "−" next to it takes exactly that back. The page never reloads.
    counts = page.locator('.watch-count')
    expect(page.get_by_role('button', name='Watch Season 1 again')).to_have_count(0)
    page.get_by_role('button', name='Mark Season 1 as watched').click()
    expect(watched).to_have_count(40)
    page.get_by_role('button', name='Watch Season 1 again').click()
    expect(counts).to_have_count(40)
    take_back = page.get_by_role('button', name='Take back one rewatch of Season 1')
    take_back.click()
    expect(counts).to_have_count(0)
    expect(take_back).to_have_count(0)
    expect(watched).to_have_count(40)

    # An episode's green circle pressed again counts it twice, and its "−" takes the second one back.
    page.get_by_role('button', name='Watch episode 5 again').click()
    expect(counts).to_have_count(1)
    expect(counts).to_have_text('2×')
    expect(take_back).to_be_visible()  # a rewatch is there to take back
    page.get_by_role('button', name='Take back the latest watch of episode 5').click()
    expect(counts).to_have_count(0)
    expect(watched).to_have_count(40)


def test_a_series_found_in_search_and_marked_shows_up_under_watching(live_server, page, respx_mock, settings):
    settings.TMDB_API_KEY = 'made-up-secret-key'
    user = User.objects.create_user(username='made-up-user', password='made-up-password')
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    series = {'id': 1399, 'name': 'Made-up Series', 'first_air_date': '2011-04-17'}
    respx_mock.get('https://api.themoviedb.org/3/search/multi').respond(
        json={'page': 1, 'results': [{'media_type': 'tv', **series}]}
    )
    respx_mock.get('https://api.themoviedb.org/3/tv/1399').respond(
        json={**series, 'status': 'Ended', 'seasons': [{'season_number': 1}]}
    )
    episodes = [
        {'id': 6001, 'season_number': 1, 'episode_number': 1, 'name': 'Made-up pilot', 'air_date': '2011-04-17'},
        {'id': 6002, 'season_number': 1, 'episode_number': 2, 'name': 'Made-up finale', 'air_date': '2011-04-24'},
    ]
    respx_mock.get('https://api.themoviedb.org/3/tv/1399/season/1').respond(
        json={'season_number': 1, 'episodes': episodes}
    )
    page.route('https://image.tmdb.org/**', lambda route: route.abort())

    page.goto(live_server.url)
    page.get_by_label('Username').fill('made-up-user')
    page.get_by_label('Password').fill('made-up-password')
    page.get_by_role('button', name='Log in').click()

    # Search for the series and open it. It is never added to the To Watch list.
    page.get_by_role('link', name='Search', exact=True).click()
    page.wait_for_load_state('load')
    page.get_by_role('searchbox').press_sequentially('made-up')
    page.locator('.tile').click()
    expect(page.get_by_text('2011 · Series · Ended')).to_be_visible()
    page.get_by_role('button', name='Mark episode 1 as watched').click()
    expect(page.get_by_role('button', name='Mark episode 1 as not watched')).to_be_visible()

    # It is under Series → Watching straight away (the Series link opens it), and not under To Watch.
    page.get_by_role('link', name='Series', exact=True).click()
    expect(page.locator('.tile')).to_contain_text('Made-up Series')
    page.get_by_role('link', name='To Watch', exact=True).click()
    expect(page.locator('.tile')).to_have_count(0)
    page.get_by_role('link', name='Watching', exact=True).click()
    expect(page.locator('.tile')).to_contain_text('Made-up Series')

    # Mark the last episode too: the series ended and every episode has aired, so it is finished.
    page.locator('.tile').click()
    page.get_by_role('button', name='Mark episode 2 as watched').click()
    expect(page.get_by_role('button', name='Mark episode 2 as not watched')).to_be_visible()
    page.get_by_role('link', name='Series', exact=True).click()
    page.get_by_role('link', name='Finished', exact=True).click()
    expect(page.locator('.tile')).to_contain_text('Made-up Series')
    page.get_by_role('link', name='Watching', exact=True).click()
    expect(page.get_by_text('No series in Watching yet')).to_be_visible()

    # Un-mark one episode: back under Watching.
    page.get_by_role('link', name='Finished', exact=True).click()
    page.locator('.tile').click()
    page.get_by_role('button', name='Mark episode 2 as not watched').click()
    expect(page.get_by_role('button', name='Mark episode 2 as watched')).to_be_visible()
    page.get_by_role('link', name='Series', exact=True).click()
    expect(page.locator('.tile')).to_contain_text('Made-up Series')


def test_up_next_on_home_follows_the_check_buttons_and_the_series_page_bars(live_server, page):
    user = User.objects.create_user(username='made-up-user', password='made-up-password')
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    # Saved a moment ago, so opening the series page does not ask TMDB (which would be made up here anyway).
    series = Title.objects.create(
        kind='series', tmdb_id=1399, title='Made-up Series', status='Returning Series', episodes_refreshed_at=timezone.now()
    )
    episodes = [
        Episode.objects.create(
            title=series, tmdb_id=6000 + number, season_number=1, episode_number=number, air_date=datetime.date(2011, 4, 17)
        )
        for number in (1, 2, 3)
    ]
    Watch.objects.create(user=user, title=series, episode=episodes[0], watched_on=datetime.date(2026, 10, 28))
    page.route('https://image.tmdb.org/**', lambda route: route.abort())

    page.goto(live_server.url)
    page.get_by_label('Username').fill('made-up-user')
    page.get_by_label('Password').fill('made-up-password')
    page.get_by_role('button', name='Log in').click()
    page.goto(live_server.url)
    page.wait_for_load_state('load')

    # Home: the next episode of the series being watched, and how far along it is.
    card = page.locator('.up-next li')
    expect(card).to_have_count(1)
    expect(card).to_contain_text('Made-up Series')
    expect(card).to_contain_text('S1E2')
    expect(card).to_contain_text('1 of 3 aired episodes watched')

    # Checking it off in place: the next episode appears and the bar moves, without leaving the page.
    page.get_by_role('button', name='Mark S1E2 of Made-up Series as watched').click()
    expect(card).to_contain_text('S1E3')
    expect(card).to_contain_text('2 of 3 aired episodes watched')

    # Checking off the last one: nothing is left, so the card goes and the note takes its place.
    page.get_by_role('button', name='Mark S1E3 of Made-up Series as watched').click()
    expect(card).to_have_count(0)
    expect(page.get_by_text('Nothing to watch next')).to_be_visible()

    # The series page shows the bars full. Undoing an episode there moves both bars back in place.
    page.goto(live_server.url + '/series/1399/')
    expect(page.locator('#progress-series')).to_contain_text('3 of 3 aired episodes watched')
    expect(page.locator('#progress-season-1')).to_contain_text('3 of 3 aired episodes watched')
    page.get_by_role('button', name='Mark episode 3 as not watched').click()
    expect(page.locator('#progress-series')).to_contain_text('2 of 3 aired episodes watched')
    expect(page.locator('#progress-season-1')).to_contain_text('2 of 3 aired episodes watched')

    # And back on Home the episode is next again.
    page.goto(live_server.url)
    expect(card).to_contain_text('S1E3')
    expect(card).to_contain_text('2 of 3 aired episodes watched')


def test_a_series_on_the_to_watch_list_shows_in_the_calendar_until_it_is_removed(
    live_server, page, respx_mock, settings, monkeypatch
):
    # A long window, so a slow machine can never run out of undo time in the middle of this test.
    monkeypatch.setattr('core.views.UNDO_WINDOW', datetime.timedelta(minutes=5))
    settings.TMDB_API_KEY = 'made-up-secret-key'
    user = User.objects.create_user(username='made-up-user', password='made-up-password')
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    series = {'id': 1399, 'name': 'Made-up Series', 'first_air_date': '2011-04-17'}
    airs = datetime.date.today() + datetime.timedelta(days=30)
    respx_mock.get('https://api.themoviedb.org/3/search/multi').respond(
        json={'page': 1, 'results': [{'media_type': 'tv', **series}]}
    )
    respx_mock.get('https://api.themoviedb.org/3/tv/1399').respond(
        json={**series, 'status': 'Returning Series', 'seasons': [{'season_number': 1}]}
    )
    episode = {'id': 6001, 'season_number': 1, 'episode_number': 1, 'name': 'Made-up premiere', 'air_date': airs.isoformat()}
    respx_mock.get('https://api.themoviedb.org/3/tv/1399/season/1').respond(
        json={'season_number': 1, 'episodes': [episode]}
    )
    page.route('https://image.tmdb.org/**', lambda route: route.abort())

    page.goto(live_server.url)
    page.get_by_label('Username').fill('made-up-user')
    page.get_by_label('Password').fill('made-up-password')
    page.get_by_role('button', name='Log in').click()

    # Add the series to the To Watch list from the search results.
    page.get_by_role('link', name='Search', exact=True).click()
    page.wait_for_load_state('load')
    page.get_by_role('searchbox').press_sequentially('made-up')
    # The series is on the list at once and the button asks for its episodes right after, so wait for that answer.
    with page.expect_response('**/to-watch/collect/'):
        page.get_by_role('button', name='Add to To Watch').click()
    expect(page.get_by_role('button', name='Remove from To Watch')).to_be_visible()

    # Adding collected its dates, so the calendar shows the episode on the day TMDB gives, with no job run by hand.
    page.get_by_role('link', name='Calendar', exact=True).click()
    item = page.locator('.calendar li')
    expect(item).to_have_count(1)
    expect(item).to_contain_text('Made-up Series')
    expect(item).to_contain_text('S1E1 · Made-up premiere')
    expect(page.get_by_role('heading', name=f'{airs:%A} {airs.day}')).to_be_visible()

    # Removing the series from the list takes it off the calendar.
    page.get_by_role('link', name='Series', exact=True).click()
    page.get_by_role('link', name='To Watch', exact=True).click()
    page.get_by_role('button', name='Remove from To Watch').click()
    page.get_by_role('link', name='Calendar', exact=True).click()
    expect(item).to_have_count(0)
    expect(page.get_by_text('Nothing coming up')).to_be_visible()

    # Undo brings it back to the calendar too.
    page.get_by_role('link', name='Series', exact=True).click()
    page.get_by_role('link', name='To Watch', exact=True).click()
    page.get_by_role('button', name='Undo').click()
    page.get_by_role('link', name='Calendar', exact=True).click()
    expect(item).to_have_count(1)


def test_rate_a_movie_change_it_and_remove_it(live_server, page, respx_mock, settings):
    settings.TMDB_API_KEY = 'made-up-secret-key'
    user = User.objects.create_user(username='made-up-user', password='made-up-password')
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    respx_mock.get('https://api.themoviedb.org/3/movie/603').respond(json=MADE_UP_MOVIE)
    page.route('https://image.tmdb.org/**', lambda route: route.abort())

    page.goto(live_server.url)
    page.get_by_label('Username').fill('made-up-user')
    page.get_by_label('Password').fill('made-up-password')
    page.get_by_role('button', name='Log in').click()
    page.goto(live_server.url + '/movie/603/')
    page.wait_for_load_state('load')

    # Nothing yet: the form is folded away. Open it, pick 4 stars, write a note and save.
    expect(page.get_by_text('Your rating:')).to_have_count(0)
    page.get_by_text('Rate it or add a note').click()
    page.get_by_label('4 out of 5 stars').check()
    page.locator('textarea[name="note"]').fill('Loved the ending.')
    page.get_by_role('button', name='Save', exact=True).click()

    # Both are shown on the page. There is no Undo button: the edit icon is the way to change them.
    expect(page.get_by_text('Rating saved and note saved.')).to_be_visible()
    expect(page.get_by_text('Your rating: ★★★★☆')).to_be_visible()
    expect(page.get_by_text('Your note: Loved the ending.')).to_be_visible()
    expect(page.get_by_role('button', name='Undo')).to_have_count(0)
    edit = page.get_by_label('Change or remove your rating and note', exact=True).first
    expect(edit).to_be_visible()
    expect(edit.locator('svg')).to_be_visible()

    # Change the stars only: the icon opens the form, which has what is saved.
    edit.click()
    expect(page.get_by_label('4 out of 5 stars')).to_be_checked()
    page.get_by_label('2 out of 5 stars').check()
    page.get_by_role('button', name='Save', exact=True).click()
    expect(page.get_by_text('Your rating: ★★☆☆☆')).to_be_visible()
    expect(page.get_by_text('Your note: Loved the ending.')).to_be_visible()

    # Remove both: "No rating" and an empty note. Nothing is left, and that survives a reload.
    page.get_by_label('Change or remove your rating and note', exact=True).first.click()
    page.get_by_label('No rating').check()
    page.locator('textarea[name="note"]').fill('')
    page.get_by_role('button', name='Save', exact=True).click()
    expect(page.get_by_text('Your rating:')).to_have_count(0)
    expect(page.get_by_text('Your note:')).to_have_count(0)
    page.reload()
    expect(page.get_by_text('Rate it or add a note')).to_be_visible()

    # Editing again puts them back, which is the way back after a mistake.
    page.get_by_text('Rate it or add a note').click()
    page.get_by_label('4 out of 5 stars').check()
    page.locator('textarea[name="note"]').fill('Loved the ending.')
    page.get_by_role('button', name='Save', exact=True).click()
    expect(page.get_by_text('Your rating: ★★★★☆')).to_be_visible()
    expect(page.get_by_text('Your note: Loved the ending.')).to_be_visible()
