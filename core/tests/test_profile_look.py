"""The Profile page in a real browser: the time zone box and its two buttons are only as wide as what they say, on a
computer and on a phone, and nothing goes off the screen."""

import os

import pytest
from django.contrib.auth.models import User

from core.models import Profile

# The browser's driver runs inside an event loop, and Django refuses database calls from
# there unless told it is fine. It is fine in a test.
os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')

COMPUTER = {'width': 1280, 'height': 800}
PHONE = {'width': 390, 'height': 800}


def width_of(page, selector):
    return page.locator(selector).evaluate('element => element.getBoundingClientRect().width')


@pytest.mark.parametrize('screen', [COMPUTER, PHONE], ids=['computer', 'phone'])
def test_the_time_zone_box_and_the_buttons_are_only_as_wide_as_what_they_say(live_server, browser, screen):
    user = User.objects.create_user(username='made-up-user', password='made-up-password')
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    is_phone = screen is PHONE
    context = browser.new_context(viewport=screen, has_touch=is_phone, is_mobile=is_phone)
    page = context.new_page()
    page.goto(live_server.url)
    page.get_by_label('Username').fill('made-up-user')
    page.get_by_label('Password').fill('made-up-password')
    page.get_by_role('button', name='Log in').click()
    page.wait_for_url(live_server.url + '/')

    page.goto(live_server.url + '/profile/')

    page_width = width_of(page, 'main')
    for selector in ['#id_timezone', 'button:has-text("Save time zone")', 'button:has-text("Log out")']:
        width = width_of(page, selector)
        assert width < page_width / 2 if not is_phone else width < page_width, selector
    # A button is as wide as its words plus its padding: far narrower than the box on a computer.
    assert width_of(page, 'button:has-text("Save time zone")') < 250
    assert width_of(page, 'button:has-text("Log out")') < 150
    # Still easy to tap: at least 40 pixels tall.
    for name in ['Save time zone', 'Log out']:
        assert page.get_by_role('button', name=name).bounding_box()['height'] >= 40
    # The words "Time zone" stay above the box, not beside it.
    label = page.locator('label:has(#id_timezone)').bounding_box()
    box = page.locator('#id_timezone').bounding_box()
    assert box['x'] == label['x']
    assert box['y'] >= label['y'] + 20
    # Nothing goes off the screen sideways.
    assert page.evaluate('document.documentElement.scrollWidth') <= screen['width']
    context.close()


def test_other_pages_keep_their_full_width_buttons(live_server, browser):
    context = browser.new_context(viewport=COMPUTER)
    page = context.new_page()

    page.goto(live_server.url + '/login/')

    login_button = width_of(page, 'button:has-text("Log in")')
    assert login_button == width_of(page, 'form')
    context.close()
