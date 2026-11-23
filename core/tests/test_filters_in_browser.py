"""Filters on the lists (card #120) in a real browser: folded on a phone until opened, always open on a computer, a
change updates only the list and the page's address, and Back brings the earlier list and choices back."""

import os
import re

import pytest
from django.contrib.auth.models import User
from playwright.sync_api import expect

from core.models import Profile, Title, ToWatchItem

# The browser's driver runs inside an event loop, and Django refuses database calls from
# there unless told it is fine. It is fine in a test.
os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')

PHONE = {'width': 390, 'height': 700}
COMPUTER = {'width': 1280, 'height': 800}


@pytest.fixture
def films(db):
    user = User.objects.create_user(username='made-up-user', password='made-up-password')
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    drama = Title.objects.create(
        kind='movie', tmdb_id=1, title='Made-up Drama', year='2001', genres=[{'id': 18, 'name': 'Drama'}]
    )
    comedy = Title.objects.create(
        kind='movie', tmdb_id=2, title='Made-up Comedy', year='1999', genres=[{'id': 35, 'name': 'Comedy'}]
    )
    ToWatchItem.objects.create(user=user, title=drama)
    ToWatchItem.objects.create(user=user, title=comedy)


def log_in(page, live_server, size):
    page.set_viewport_size(size)
    page.route('https://image.tmdb.org/**', lambda route: route.abort())
    page.goto(live_server.url)
    page.get_by_label('Username').fill('made-up-user')
    page.get_by_label('Password').fill('made-up-password')
    page.get_by_role('button', name='Log in').click()
    page.wait_for_url(live_server.url + '/')


def test_on_a_phone_the_filters_are_folded_until_opened(live_server, page, films):
    log_in(page, live_server, PHONE)
    page.goto(live_server.url + '/movies/')

    expect(page.get_by_label('Genre')).to_be_hidden()
    page.get_by_text('Filter and sort').click()
    expect(page.get_by_label('Genre')).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')


def test_on_a_computer_the_filters_are_always_open(live_server, page, films):
    log_in(page, live_server, COMPUTER)
    page.goto(live_server.url + '/movies/')

    expect(page.get_by_label('Genre')).to_be_visible()
    expect(page.get_by_text('Filter and sort')).to_be_hidden()
    # The four boxes sit in one row.
    tops = {round(page.get_by_label(name).bounding_box()['y']) for name in ('Genre', 'My rating', 'Sort')}
    assert len(tops) == 1


def test_a_change_updates_the_list_and_the_address_and_back_brings_the_list_back(live_server, page, films):
    log_in(page, live_server, COMPUTER)
    page.goto(live_server.url + '/movies/')
    tiles = page.locator('#list .tile')
    expect(tiles).to_have_count(2)

    page.get_by_label('Genre').select_option(label='Drama')
    expect(tiles).to_have_count(1)
    expect(tiles.first).to_contain_text('Made-up Drama')
    expect(page).to_have_url(re.compile(r'/movies/\?genre=18&'))
    expect(page.get_by_role('link', name='Clear filters')).to_be_visible()

    page.get_by_label('Sort').select_option(label='Year, oldest first')
    expect(page).to_have_url(re.compile(r'genre=18.*sort=oldest'))

    page.go_back()
    expect(page).to_have_url(re.compile(r'/movies/\?genre=18&rating=&sort=$'))
    expect(tiles).to_have_count(1)
    expect(page.get_by_label('Sort')).to_have_value('')
    expect(page.get_by_label('Genre')).to_have_value('18')

    page.go_back()
    expect(page).to_have_url(live_server.url + '/movies/')
    expect(tiles).to_have_count(2)
    expect(page.get_by_label('Genre')).to_have_value('')

    page.go_forward()
    page.get_by_role('link', name='Clear filters').click()
    expect(page).to_have_url(live_server.url + '/movies/')
    expect(tiles).to_have_count(2)
