"""The first end-to-end test: a real browser walks through the app, as I would."""

import os

from django.contrib.auth.models import User
from playwright.sync_api import expect

from core.models import Profile

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


def test_log_in_search_add_a_title_then_remove_it_and_undo(live_server, page, respx_mock, settings):
    settings.TMDB_API_KEY = 'made-up-secret-key'
    user = User.objects.create_user(username='made-up-user', password='made-up-password')
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    # The app's server asks TMDB (made up here). The browser's poster downloads are blocked.
    respx_mock.get('https://api.themoviedb.org/3/search/multi').respond(
        json={'page': 1, 'results': [{'media_type': 'movie', **MADE_UP_MOVIE}]}
    )
    respx_mock.get('https://api.themoviedb.org/3/movie/603').respond(json=MADE_UP_MOVIE)
    page.route('https://image.tmdb.org/**', lambda route: route.abort())

    # Log in.
    page.goto(live_server.url)
    page.get_by_label('Username').fill('made-up-user')
    page.get_by_label('Password').fill('made-up-password')
    page.get_by_role('button', name='Log in').click()

    # Search: results appear as I type, with no button pressed.
    page.get_by_role('link', name='Search', exact=True).click()
    page.get_by_role('searchbox').press_sequentially('made-up')
    expect(page.locator('.tile')).to_have_count(1)
    expect(page.locator('.tile')).to_contain_text('Made-up Movie')

    # Add it. Only the button changes; the results stay where they are.
    page.get_by_role('button', name='Add to To Watch').click()
    expect(page.get_by_role('button', name='Remove from To Watch')).to_be_visible()

    # It is on the To Watch screen, and still there after reloading.
    page.get_by_role('link', name='To Watch', exact=True).click()
    expect(page.locator('.tile')).to_have_count(1)
    expect(page.locator('.tile')).to_contain_text('Made-up Movie')
    page.reload()
    expect(page.locator('.tile')).to_have_count(1)

    # Remove it: it leaves the list and is offered under "Recently removed".
    page.get_by_role('button', name='Remove from To Watch').click()
    expect(page.locator('.tile')).to_have_count(0)
    expect(page.get_by_role('heading', name='Recently removed')).to_be_visible()

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
