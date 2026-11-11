"""DJANGO_HTTPS_ONLY, only set on the public demo: the cookies only travel over HTTPS and browsers are told to always
use HTTPS for the address (HSTS). Off, as on the PC and the Pi, nothing changes, so the plain-HTTP home login works.

Each test starts a fresh Python with the setting, because the settings file is read once when Python starts.
"""

from core.tests.test_production_settings import run_python

# Opens the login page as a visitor who came over HTTPS (Render's proxy says so in X-Forwarded-Proto), and prints the
# HSTS header and whether each cookie is HTTPS only.
OPEN_THE_LOGIN_PAGE = """
import django
django.setup()
from django.test import Client
response = Client().get('/login/', headers={'X-Forwarded-Proto': 'https'})
print(response.status_code)
print(response.headers.get('Strict-Transport-Security', 'no HSTS'))
print('csrftoken secure' if response.cookies['csrftoken']['secure'] else 'csrftoken not secure')
from django.conf import settings
print('session secure' if settings.SESSION_COOKIE_SECURE else 'session not secure')
"""


def test_on_the_cookies_are_https_only_and_browsers_are_told_to_keep_to_https():
    result = run_python(OPEN_THE_LOGIN_PAGE, DJANGO_HTTPS_ONLY='true', DJANGO_ALLOWED_HOSTS='testserver')

    assert result.returncode == 0, result.stderr
    assert result.stdout.split('\n')[:4] == [
        '200',
        'max-age=15724800',  # six months, for this address only (no includeSubDomains)
        'csrftoken secure',
        'session secure',
    ]


def test_off_nothing_changes_so_the_plain_http_home_login_keeps_working():
    # Empty counts as off. It also keeps a DJANGO_HTTPS_ONLY in the real .env from reaching this test.
    result = run_python(OPEN_THE_LOGIN_PAGE, DJANGO_HTTPS_ONLY='', DJANGO_ALLOWED_HOSTS='testserver')

    assert result.returncode == 0, result.stderr
    assert result.stdout.split('\n')[:4] == ['200', 'no HSTS', 'csrftoken not secure', 'session not secure']
