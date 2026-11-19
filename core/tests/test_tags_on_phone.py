"""My own tags (card #119) in a real browser at phone size: the chips wrap onto new lines and stay easy to tap, the ×
sits small on each chip's corner, a tap adds, removes, renames or deletes a tag, and the page does not move."""

import os

import pytest
from django.contrib.auth.models import User
from playwright.sync_api import expect

from core.models import Profile, Tag, Title, TitleTag

# The browser's driver runs inside an event loop, and Django refuses database calls from
# there unless told it is fine. It is fine in a test.
os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')

PHONE = {'width': 390, 'height': 700}
# Easy to tap: the chips and the "+" at least 40 px high (2.5rem). The small × in a chip's corner is drawn small, but
# what can be tapped is 28 px square (1.75rem).
TAP_HEIGHT = 40
CORNER_TAP = 28


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


def scrolled_to(page, selector):
    """Scroll so that `selector` is at the bottom of the screen, and say how far the page is scrolled."""
    page.locator(selector).first.evaluate('element => element.scrollIntoView({block: "end"})')
    return page.evaluate('window.scrollY')


def assert_corner_x(chip):
    """The × is small and on the chip's top-right corner, and can still be tapped."""
    tag = chip.bounding_box()
    button = chip.locator('.tag-chip-remove').bounding_box()
    drawn = chip.locator('.tag-chip-remove span').bounding_box()
    centre_x, centre_y = drawn['x'] + drawn['width'] / 2, drawn['y'] + drawn['height'] / 2
    assert drawn['width'] <= 20
    assert abs(centre_x - (tag['x'] + tag['width'])) <= 8
    assert abs(centre_y - tag['y']) <= 8
    assert button['width'] >= CORNER_TAP - 0.5 and button['height'] >= CORNER_TAP - 0.5


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
    # The "+ name" chips are easy to tap, and each tag on the title has its small × on the corner.
    for button in page.locator('.tag-chip-add').all():
        assert button.bounding_box()['height'] >= TAP_HEIGHT - 0.5
    for chip in page.locator('.tag-chip').all():
        assert_corner_x(chip)


def test_a_tap_adds_a_tag_and_another_takes_it_off_without_moving_the_page(live_server, page):
    user = make_user()
    movie = saved_movie()
    Tag.objects.create(user=user, name='comfort')
    log_in(page, live_server)
    page.goto(live_server.url + '/movie/603/')
    page.wait_for_load_state('load')
    before = scrolled_to(page, '.tags-section')
    assert before > 0  # the page is scrolled, so a jump to the top would show

    page.get_by_role('button', name='Add the tag comfort').click()
    expect(page.get_by_role('button', name='Remove the tag comfort')).to_be_visible()
    assert TitleTag.objects.filter(title=movie).count() == 1
    assert page.evaluate('window.scrollY') == pytest.approx(before, abs=2)

    page.get_by_role('button', name='Remove the tag comfort').click()
    expect(page.get_by_role('button', name='Add the tag comfort')).to_be_visible()
    assert not TitleTag.objects.exists()
    assert page.evaluate('window.scrollY') == pytest.approx(before, abs=2)


def test_a_new_tag_typed_on_the_titles_page_shows_as_a_chip(live_server, page):
    make_user()
    saved_movie()
    log_in(page, live_server)
    page.goto(live_server.url + '/movie/603/')

    page.get_by_label('New tag for this title').fill('to show a friend')
    page.get_by_role('button', name='Add', exact=True).click()

    expect(page.get_by_role('button', name='Remove the tag to show a friend')).to_be_visible()


def test_profiles_tags_are_chips_that_fit_a_phone(live_server, page):
    user = make_user()
    for name in ['comfort', 'cosy', 'with family', 'thirty characters long tag xyz']:
        Tag.objects.create(user=user, name=name)
    log_in(page, live_server)
    page.goto(live_server.url + '/profile/')

    chips = page.locator('.tag-chip')
    expect(chips).to_have_count(4)
    # Small chips, several on a line, inside the screen, the pencil easy to tap and the × on the corner.
    boxes = [chip.bounding_box() for chip in chips.all()]
    assert len({round(box['y']) for box in boxes}) < 4
    assert all(box['height'] < 50 for box in boxes)
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    for pencil in page.locator('.tag-chip summary').all():
        assert pencil.bounding_box()['height'] >= TAP_HEIGHT - 0.5
    for chip in chips.all():
        assert_corner_x(chip)


def test_on_profile_a_tag_is_made_renamed_and_deleted_without_moving_the_page(live_server, page):
    user = make_user()
    Tag.objects.create(user=user, name='thirty characters long tag xyz')
    log_in(page, live_server)
    page.goto(live_server.url + '/profile/')
    page.wait_for_load_state('load')
    before = scrolled_to(page, '.tags-section')
    assert before > 0

    page.get_by_label('New tag', exact=True).fill('comfort')
    page.get_by_role('button', name='Add tag').click()
    expect(page.get_by_label('Rename the tag comfort')).to_be_visible()
    assert page.evaluate('window.scrollY') == pytest.approx(before, abs=2)

    # The pencil opens the rename box under the name, still inside the screen. No Save until then.
    box = page.get_by_label('New name for thirty characters long tag xyz')
    expect(box).to_be_hidden()
    expect(page.get_by_role('button', name='Save', exact=True)).to_have_count(0)
    page.get_by_label('Rename the tag thirty characters long tag xyz').click()
    expect(box).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    box.fill('thirty characters long tag abc')
    page.get_by_role('button', name='Save', exact=True).click()
    expect(page.get_by_label('Rename the tag thirty characters long tag abc')).to_be_visible()

    # The × deletes it for good, with no Undo.
    page.get_by_role('button', name='Delete the tag thirty characters long tag abc').click()
    expect(page.get_by_label('Rename the tag thirty characters long tag abc')).to_have_count(0)
    expect(page.get_by_role('button', name='Undo')).to_have_count(0)
    assert list(Tag.objects.filter(user=user).values_list('name', flat=True)) == ['comfort']
