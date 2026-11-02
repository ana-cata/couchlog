"""Every page tells the browser not to keep a copy, so Back shows what is true now (the real-browser test of this is
in test_back.py). The CSS, logo and htmx are not pages: their test is in test_production_settings.py."""

import pytest
from django.contrib.auth.models import User

from core.models import Profile

PAGES = ['/', '/movies/', '/movies/history/', '/series/', '/calendar/', '/profile/', '/about/']


@pytest.fixture
def logged_in(client, db):
    user = User.objects.create_user(username='made-up-user', password='made-up-password')
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    client.force_login(user)
    return client


@pytest.mark.parametrize('url', PAGES)
def test_a_page_is_sent_with_no_store(logged_in, url):
    response = logged_in.get(url)

    assert response.status_code == 200
    assert 'no-store' in response['Cache-Control']


def test_the_login_page_is_sent_with_no_store(client, db):
    assert 'no-store' in client.get('/login/')['Cache-Control']


def test_a_redirect_is_sent_with_no_store_too(client, db):
    # A page opened while logged out sends me to the login page.
    response = client.get('/movies/')

    assert response.status_code == 302
    assert 'no-store' in response['Cache-Control']


def test_the_answer_to_a_button_is_sent_with_no_store_too(logged_in):
    response = logged_in.post('/to-watch/remove/', {'kind': 'movie', 'tmdb_id': 603}, HTTP_HX_REQUEST='true')

    assert 'no-store' in response['Cache-Control']
