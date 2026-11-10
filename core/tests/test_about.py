import pytest
from django.contrib.auth.models import User
from django.contrib.staticfiles import finders

from core.models import Profile

NOTICE = 'This product uses the TMDB API but is not endorsed or certified by TMDB.'


@pytest.mark.django_db
def test_the_about_page_is_open_and_shows_the_tmdb_credit(client):
    response = client.get('/about/')

    page = response.content.decode()
    assert response.status_code == 200
    assert NOTICE in page
    assert 'tmdb-logo.svg' in page


@pytest.mark.django_db
def test_the_about_page_has_the_privacy_note_next_to_the_credit(client):
    page = ' '.join(client.get('/about/').content.decode().split())

    assert NOTICE in page
    assert 'Couchlog stores what you add: your watch history, ratings and notes, your time zone and your email.' in page
    assert 'Daily backups are kept in private storage at Cloudflare R2.' in page
    assert 'the connection goes through Cloudflare' in page
    assert 'If you want your data removed, tell me.' in page


def test_the_logo_file_is_in_the_project():
    assert finders.find('core/tmdb-logo.svg')


@pytest.mark.django_db
def test_the_header_links_to_about_on_every_page(client):
    user = User.objects.create_user(username='made-up-user', password='made-up-password')
    Profile.objects.create(user=user, timezone='Europe/Lisbon')

    # The login page is open to everyone, so the credit is reachable before logging in.
    assert 'href="/about/"' in client.get('/login/').content.decode()

    client.force_login(user)
    for url in ['/', '/profile/', '/search/']:
        assert 'href="/about/"' in client.get(url).content.decode()
