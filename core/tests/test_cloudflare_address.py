"""Forms sent through the Cloudflare address, and the setting that allows them.

The app receives plain HTTP from the tunnel while the browser is on https://, so Django only accepts those forms if
the address is listed in DJANGO_CSRF_TRUSTED_ORIGINS. These tests use Django's real protection against forged requests
(the normal test client switches it off).
"""

import pytest
from django.contrib.auth.models import User
from django.test import Client

from core.models import Profile
from core.tests.test_production_settings import run_python

CLOUDFLARE_HOST = 'couchlog.example.com'
CLOUDFLARE_ORIGIN = f'https://{CLOUDFLARE_HOST}'
HOME_HOST = '192.168.1.164:3000'
PASSWORD = 'made-up-password'

READ_THE_SETTING = 'from django.conf import settings; print(settings.CSRF_TRUSTED_ORIGINS)'


@pytest.fixture
def user(db):
    user = User.objects.create_user(username='made-up-user', password=PASSWORD)
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    return user


@pytest.fixture
def cloudflare_settings(settings):
    settings.ALLOWED_HOSTS = [CLOUDFLARE_HOST, '192.168.1.164']
    settings.CSRF_TRUSTED_ORIGINS = [CLOUDFLARE_ORIGIN]


def log_in(host, origin):
    """Open the login page and send its form the way a browser on `origin` does; return the answer and the client."""
    client = Client(enforce_csrf_checks=True)
    client.get('/login/', HTTP_HOST=host)
    response = client.post(
        '/login/',
        {'username': 'made-up-user', 'password': PASSWORD, 'csrfmiddlewaretoken': client.cookies['csrftoken'].value},
        HTTP_HOST=host,
        HTTP_ORIGIN=origin,
    )
    return response, client


def test_the_trusted_addresses_come_from_the_setting():
    result = run_python(
        READ_THE_SETTING,
        DJANGO_CSRF_TRUSTED_ORIGINS='https://couchlog.example.com, https://other.example.com',
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "['https://couchlog.example.com', 'https://other.example.com']"


def test_with_the_setting_empty_no_address_is_trusted():
    # An empty value counts as not set. It also keeps a value in the real .env from reaching this test.
    result = run_python(READ_THE_SETTING, DJANGO_CSRF_TRUSTED_ORIGINS='')

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == '[]'


def test_a_form_from_the_trusted_address_is_accepted(user, cloudflare_settings):
    response, client = log_in(CLOUDFLARE_HOST, CLOUDFLARE_ORIGIN)

    assert response.status_code == 302
    assert response['Location'] == '/'
    assert client.get('/', HTTP_HOST=CLOUDFLARE_HOST).status_code == 200


def test_a_form_from_another_address_is_refused(user, cloudflare_settings):
    response, client = log_in(CLOUDFLARE_HOST, 'https://not-couchlog.example.net')

    assert response.status_code == 403
    assert client.get('/', HTTP_HOST=CLOUDFLARE_HOST).status_code == 302


def test_the_cloudflare_address_needs_the_setting(user, settings):
    settings.ALLOWED_HOSTS = [CLOUDFLARE_HOST]
    settings.CSRF_TRUSTED_ORIGINS = []

    response, _ = log_in(CLOUDFLARE_HOST, CLOUDFLARE_ORIGIN)

    assert response.status_code == 403


def test_logging_in_at_the_home_address_still_works(user, cloudflare_settings):
    response, client = log_in(HOME_HOST, f'http://{HOME_HOST}')

    assert response.status_code == 302
    assert response['Location'] == '/'
    assert client.get('/', HTTP_HOST=HOME_HOST).status_code == 200
