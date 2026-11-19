"""Ratings on lists, and a nudge to rate (card #118), in a real browser at phone size: the stars fit on the tiles, the
offer pops up over the page without moving the button (as fixed in #91 and #93), and "Not now" closes it."""

import os

import pytest
from django.contrib.auth.models import User
from playwright.sync_api import expect

from core.models import Profile, Rating, Title, ToWatchItem, Watch

# The browser's driver runs inside an event loop, and Django refuses database calls from
# there unless told it is fine. It is fine in a test.
os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')

PHONE = {'width': 390, 'height': 700}


@pytest.fixture(autouse=True)
def tmdb_key(settings):
    settings.TMDB_API_KEY = 'made-up-secret-key'


def make_user():
    user = User.objects.create_user(username='made-up-user', password='made-up-password')
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    return user


def saved_movie(tmdb_id=603, title='Made-up Movie'):
    """A movie saved with its length and genres, so its page never asks TMDB (the tests never call it)."""
    return Title.objects.create(
        kind='movie', tmdb_id=tmdb_id, title=title, year='1999', runtime=136, genres=[{'id': 18, 'name': 'Drama'}]
    )


def log_in(page, live_server):
    page.set_viewport_size(PHONE)
    page.route('https://image.tmdb.org/**', lambda route: route.abort())
    page.goto(live_server.url)
    page.get_by_label('Username').fill('made-up-user')
    page.get_by_label('Password').fill('made-up-password')
    page.get_by_role('button', name='Log in').click()
    page.wait_for_url(live_server.url + '/')


def test_the_stars_fit_on_the_tiles_of_a_list_on_a_phone(live_server, page):
    user = make_user()
    for number in range(4):
        movie = saved_movie(600 + number, f'Made-up Movie With A Long Name Number {number}')
        ToWatchItem.objects.create(user=user, title=movie)
        Rating.objects.create(user=user, title=movie, stars=5)
    log_in(page, live_server)

    page.goto(live_server.url + '/movies/')

    stars = page.locator('.tile-stars')
    expect(stars).to_have_count(4)
    expect(stars.first).to_have_text('★★★★★Your rating: 5 of 5')
    # Two tiles side by side, as without stars, and each stars line is whole (not cut with "...").
    tops = {round(box['y']) for box in (tile.bounding_box() for tile in page.locator('.tile').all())}
    assert len(tops) == 2
    assert stars.first.evaluate('line => line.scrollWidth <= line.clientWidth')
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')


def test_the_offer_pops_up_over_the_page_and_the_button_does_not_move(live_server, page):
    make_user()
    saved_movie()
    log_in(page, live_server)
    page.goto(live_server.url + '/movie/603/')
    page.wait_for_load_state('load')

    def button_top(name):
        """Where the button is from the top of the title (poster and details). The "Marked as watched" line above the
        title is left out: it moved the button before this card too, and #93 already checks it."""
        return page.get_by_role('button', name=name).evaluate(
            'b => b.getBoundingClientRect().top - document.querySelector(".title-page").getBoundingClientRect().top'
        )

    before = button_top('Mark as watched')
    page.get_by_role('button', name='Mark as watched').click()
    expect(page.get_by_text('How was it?')).to_be_visible()
    page.wait_for_timeout(200)

    # The button did not move: the pop-up is over the page, not in it.
    assert button_top('Watch again') == pytest.approx(before, abs=1)
    # The pop-up fits the phone's width, and its Save can be reached.
    offer = page.locator('.rate-offer article').bounding_box()
    assert offer['x'] >= 0 and offer['x'] + offer['width'] <= PHONE['width']
    expect(page.locator('.rate-offer').get_by_role('button', name='Save', exact=True)).to_be_visible()


def test_not_now_closes_the_offer_and_saves_nothing(live_server, page):
    make_user()
    saved_movie()
    log_in(page, live_server)
    page.goto(live_server.url + '/movie/603/')
    page.wait_for_load_state('load')
    page.get_by_role('button', name='Mark as watched').click()
    expect(page.get_by_text('How was it?')).to_be_visible()

    page.get_by_role('link', name='Not now').click()

    expect(page.locator('.rate-offer')).to_have_count(0)
    assert not Rating.objects.exists()
    assert Watch.objects.count() == 1
