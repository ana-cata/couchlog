"""My own tags (card #119) in a real browser at phone size: the chips on a title's page wrap onto new lines and stay
easy to tap, a tap adds or removes a tag, and Profile's list fits the screen."""

import os

import pytest
from django.contrib.auth.models import User
from playwright.sync_api import expect

from core.models import Profile, Tag, Title, TitleTag

# The browser's driver runs inside an event loop, and Django refuses database calls from
# there unless told it is fine. It is fine in a test.
os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')

PHONE = {'width': 390, 'height': 700}
# Easy to tap: at least 40 px high (2.5rem).
TAP_HEIGHT = 40


@pytest.fixture(autouse=True)
def tmdb_key(settings):
    settings.TMDB_API_KEY = 'made-up-secret-key'


def make_user():
    user = User.objects.create_user(username='made-up-user', password='made-up-password')
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    return user


def saved_movie():
    """A movie saved with its length and genres, so its page never asks TMDB (the tests never call it)."""
    return Title.objects.create(
        kind='movie', tmdb_id=603, title='Made-up Movie', year='1999', runtime=136, genres=[{'id': 18, 'name': 'Drama'}]
    )


def log_in(page, live_server):
    page.set_viewport_size(PHONE)
    page.route('https://image.tmdb.org/**', lambda route: route.abort())
    page.goto(live_server.url)
    page.get_by_label('Username').fill('made-up-user')
    page.get_by_label('Password').fill('made-up-password')
    page.get_by_role('button', name='Log in').click()
    page.wait_for_url(live_server.url + '/')


def test_the_chips_wrap_and_stay_easy_to_tap_on_a_phone(live_server, page):
    user = make_user()
    movie = saved_movie()
    names = ['comfort', 'with family', 'to show a friend', 'rainy sunday', 'thirty characters long tag xyz', 'cosy']
    tags = [Tag.objects.create(user=user, name=name) for name in names]
    for tag in tags[:3]:
        TitleTag.objects.create(tag=tag, title=movie)
    log_in(page, live_server)

    page.goto(live_server.url + '/movie/603/')

    chips = page.locator('.tag-chips > li')
    expect(chips).to_have_count(6)
    boxes = [chip.bounding_box() for chip in chips.all()]
    # They wrap onto more than one line, and none runs off the screen.
    assert len({round(box['y']) for box in boxes}) > 1
    assert all(box['x'] >= 0 and box['x'] + box['width'] <= PHONE['width'] for box in boxes)
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    # Every button in them (the × and the "+ name") is easy to tap.
    for button in page.locator('.tag-chips button').all():
        box = button.bounding_box()
        assert box['height'] >= TAP_HEIGHT - 0.5
        assert box['width'] >= TAP_HEIGHT - 0.5


def test_a_tap_adds_a_tag_and_another_takes_it_off(live_server, page):
    user = make_user()
    movie = saved_movie()
    Tag.objects.create(user=user, name='comfort')
    log_in(page, live_server)
    page.goto(live_server.url + '/movie/603/')

    page.get_by_role('button', name='Add the tag comfort').click()
    expect(page.get_by_role('button', name='Remove the tag comfort')).to_be_visible()
    assert TitleTag.objects.filter(title=movie).count() == 1

    page.get_by_role('button', name='Remove the tag comfort').click()
    expect(page.get_by_role('button', name='Add the tag comfort')).to_be_visible()
    assert not TitleTag.objects.exists()


def test_a_new_tag_typed_on_the_titles_page_shows_as_a_chip(live_server, page):
    make_user()
    saved_movie()
    log_in(page, live_server)
    page.goto(live_server.url + '/movie/603/')

    page.get_by_label('New tag for this title').fill('to show a friend')
    page.get_by_role('button', name='Add', exact=True).click()

    expect(page.get_by_role('button', name='Remove the tag to show a friend')).to_be_visible()


def test_profiles_tags_fit_a_phone_and_delete_can_be_undone(live_server, page):
    user = make_user()
    Tag.objects.create(user=user, name='thirty characters long tag xyz')
    log_in(page, live_server)
    page.goto(live_server.url + '/profile/')

    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    # Rename opens its box on its own line under the tag, still inside the screen.
    box = page.get_by_label('New name for thirty characters long tag xyz')
    expect(box).to_be_hidden()
    page.get_by_text('Rename', exact=True).click()
    expect(box).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    box.fill('thirty characters long tag abc')
    page.get_by_role('button', name='Save', exact=True).click()
    expect(page.get_by_text('Renamed “thirty characters long tag xyz” to “thirty characters long tag abc”.')).to_be_visible()

    page.get_by_role('button', name='Delete the tag thirty characters long tag abc').click()
    expect(page.get_by_text('Deleted “thirty characters long tag abc”')).to_be_visible()

    page.get_by_role('button', name='Undo').click()
    expect(page.get_by_text('Brought back the tag')).to_be_visible()
    assert Tag.objects.get(user=user).deleted_at is None
