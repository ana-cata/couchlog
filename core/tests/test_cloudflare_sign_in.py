"""Sign-in by email code on the Cloudflare address.

Every token here is made up and signed with a made-up key. Cloudflare's list of public keys is replaced by one holding
the made-up key, so the real Cloudflare is never contacted.
"""

import datetime
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from django.contrib.auth.models import User
from django.test import Client

from core.cloudflare_access import keys_from
from core.models import Profile, Title, Watch
from core.tests.test_production_settings import run_python

CLOUDFLARE_HOST = 'couchlog.example.com'
HOME_HOST = '192.168.1.164:3000'
TEAM_DOMAIN = 'made-up-team.cloudflareaccess.com'
ISSUER = f'https://{TEAM_DOMAIN}'
AUDIENCE = 'made-up-audience-tag'
KEY_ID = 'made-up-key'
MY_EMAIL = 'me@example.com'
PASSWORD = 'made-up-password'

READ_THE_SETTINGS = (
    'from django.conf import settings; '
    'print(settings.CLOUDFLARE_ACCESS_TEAM_DOMAIN, settings.CLOUDFLARE_ACCESS_AUD, settings.CLOUDFLARE_ACCESS_ADDRESS)'
)
ALL_EMPTY = {'CLOUDFLARE_ACCESS_TEAM_DOMAIN': '', 'CLOUDFLARE_ACCESS_AUD': '', 'CLOUDFLARE_ACCESS_ADDRESS': ''}

CLOUDFLARE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
SOMEONE_ELSES_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def public_keys():
    key = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(CLOUDFLARE_KEY.public_key()))
    return {'keys': [{**key, 'kid': KEY_ID, 'use': 'sig', 'alg': 'RS256'}]}


@pytest.fixture(autouse=True)
def cloudflare(settings, monkeypatch):
    settings.ALLOWED_HOSTS = [CLOUDFLARE_HOST, '192.168.1.164']
    settings.CSRF_TRUSTED_ORIGINS = [f'https://{CLOUDFLARE_HOST}']
    settings.CLOUDFLARE_ACCESS_TEAM_DOMAIN = TEAM_DOMAIN
    settings.CLOUDFLARE_ACCESS_AUD = AUDIENCE
    settings.CLOUDFLARE_ACCESS_ADDRESS = CLOUDFLARE_HOST
    keys_from.cache_clear()
    monkeypatch.setattr(jwt.PyJWKClient, 'fetch_data', lambda self: public_keys())


@pytest.fixture
def me(db):
    user = User.objects.create_superuser(username='made-up-owner', email=MY_EMAIL, password=PASSWORD)
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    return user


def token(
    email=MY_EMAIL, key=CLOUDFLARE_KEY, audience=AUDIENCE, issuer=ISSUER, expires_in=600, issued_in=0, leave_out=()
):
    now = int(time.time())
    claims = {
        'aud': [audience],
        'iss': issuer,
        'iat': now + issued_in,
        'nbf': now + issued_in,
        'exp': now + expires_in,
        'email': email,
        'sub': 'made-up',
    }
    claims = {name: value for name, value in claims.items() if name not in leave_out}
    return jwt.encode(claims, key, algorithm='RS256', headers={'kid': KEY_ID})


def visit(path='/profile/', the_token=None, client=None, host=CLOUDFLARE_HOST):
    """Open a page the way Cloudflare passes it on: at its address, with its token if there is one."""
    headers = {} if the_token is None else {'HTTP_CF_ACCESS_JWT_ASSERTION': the_token}
    return (client or Client()).get(path, HTTP_HOST=host, **headers)


def signed_in_as(response):
    return response.context['user'].get_username()


def test_a_valid_token_signs_in_to_the_account_with_that_email(me):
    response = visit(the_token=token())

    assert response.status_code == 200
    assert signed_in_as(response) == 'made-up-owner'


@pytest.mark.parametrize(
    'bad_token',
    [
        lambda: token(key=SOMEONE_ELSES_KEY),
        lambda: token(audience='another-application'),
        lambda: token(issuer='https://another-team.cloudflareaccess.com'),
        lambda: token(expires_in=-600),
        lambda: token(leave_out=['exp']),
        lambda: token(leave_out=['aud']),
        lambda: token(leave_out=['iss']),
        lambda: jwt.encode({'aud': [AUDIENCE], 'iss': ISSUER, 'exp': 9999999999, 'email': MY_EMAIL}, None, algorithm='none'),
        lambda: 'not-a-token',
        lambda: '',
    ],
    ids=[
        'wrong signature',
        'wrong audience',
        'wrong issuer',
        'expired',
        'no expiry',
        'no audience',
        'no issuer',
        'unsigned',
        'garbage',
        'empty',
    ],
)
def test_a_bad_token_signs_nobody_in(me, bad_token):
    response = visit(the_token=bad_token())

    assert response.status_code == 403
    assert not response.context['user'].is_authenticated
    assert b'Cannot sign in' in response.content


def test_a_pi_clock_a_little_behind_cloudflares_does_not_refuse_a_new_token(me):
    assert visit(the_token=token(issued_in=10)).status_code == 200


def test_a_token_from_far_in_the_future_is_refused(me):
    assert visit(the_token=token(issued_in=300)).status_code == 403


def test_a_missing_token_signs_nobody_in(me):
    response = visit()

    assert response.status_code == 403
    assert not response.context['user'].is_authenticated


def test_keys_are_read_from_the_teams_own_address():
    assert keys_from(TEAM_DOMAIN).uri == f'https://{TEAM_DOMAIN}/cdn-cgi/access/certs'


def test_no_answer_from_cloudflares_keys_is_a_friendly_refusal(me, monkeypatch):
    def no_answer(self):
        raise jwt.PyJWKClientConnectionError('made-up failure')

    monkeypatch.setattr(jwt.PyJWKClient, 'fetch_data', no_answer)

    response = visit(the_token=token())

    assert response.status_code == 503
    assert b'Try again' in response.content


def test_capital_letters_in_the_email_do_not_matter(me):
    assert signed_in_as(visit(the_token=token(email='ME@Example.COM'))) == 'made-up-owner'
    assert User.objects.count() == 1


@pytest.mark.parametrize('blank', ['', '   ', None])
def test_a_blank_email_never_matches_anyone(db, blank):
    # This account has a blank email, the way accounts made without one do.
    User.objects.create_user(username='no-email', email='')

    response = visit(the_token=token(email=blank))

    assert response.status_code == 403
    assert User.objects.count() == 1


def test_a_token_with_no_email_at_all_signs_nobody_in(me):
    response = visit(the_token=token(leave_out=['email']))

    assert response.status_code == 403
    assert User.objects.count() == 1


def test_an_email_is_matched_whole_and_not_as_a_pattern(db):
    # The _ in a database LIKE search means "any letter", and must not here.
    User.objects.create_user(username='other', email='axb@example.com')

    response = visit(the_token=token(email='a_b@example.com'))

    assert signed_in_as(response) == 'a_b@example.com'


def test_two_accounts_with_the_same_email_are_refused(db):
    User.objects.create_user(username='first', email='friend@example.com')
    User.objects.create_user(username='second', email='FRIEND@example.com')

    response = visit(the_token=token(email='friend@example.com'))

    assert response.status_code == 403
    assert not response.context['user'].is_authenticated
    assert b'More than one' in response.content


def test_a_deactivated_account_stays_out_and_stays_deactivated(db):
    friend = User.objects.create_user(username='friend', email='friend@example.com', is_active=False)

    response = visit(the_token=token(email='friend@example.com'))

    assert response.status_code == 403
    assert not response.context['user'].is_authenticated
    friend.refresh_from_db()
    assert not friend.is_active
    assert User.objects.count() == 1


def test_a_deactivated_account_with_a_second_active_one_is_still_refused(db):
    User.objects.create_user(username='old', email='friend@example.com', is_active=False)
    User.objects.create_user(username='new', email='friend@example.com')

    assert visit(the_token=token(email='friend@example.com')).status_code == 403


def test_a_new_email_gets_a_new_account_with_no_password(db):
    response = visit(the_token=token(email='New.Friend@Example.com'))

    friend = User.objects.get(username='new.friend@example.com')
    assert friend.email == 'new.friend@example.com'
    assert not friend.has_usable_password()
    assert not friend.is_staff
    assert not friend.is_superuser
    # The first page leads to the time zone step.
    assert response.status_code == 200
    assert response.context['profile'].timezone == ''


def test_the_second_visit_finds_the_same_new_account(db):
    visit(the_token=token(email='friend@example.com'))
    visit(the_token=token(email='friend@example.com'))

    assert User.objects.filter(email='friend@example.com').count() == 1


def test_a_new_account_goes_through_the_time_zone_step(db):
    friends_token = token(email='friend@example.com')
    client = Client()

    response = visit('/about/', friends_token, client)
    assert response.status_code == 302
    assert response['Location'] == '/profile/'

    client.post(
        '/profile/',
        {'timezone': 'Europe/Paris'},
        HTTP_HOST=CLOUDFLARE_HOST,
        HTTP_CF_ACCESS_JWT_ASSERTION=friends_token,
    )
    assert Profile.objects.get(user__username='friend@example.com').timezone == 'Europe/Paris'
    assert visit('/about/', friends_token, client).status_code == 200


def test_an_email_that_is_another_accounts_username_is_refused(db):
    # Someone else's account must never be opened because its username happens to be this email.
    User.objects.create_user(username='friend@example.com', email='someone.else@example.com')

    response = visit(the_token=token(email='friend@example.com'))

    assert response.status_code == 403
    assert not response.context['user'].is_authenticated
    assert User.objects.count() == 1


def test_the_token_wins_over_whoever_is_signed_in(me):
    friend = User.objects.create_user(username='friend', email='friend@example.com')
    Profile.objects.create(user=friend, timezone='Europe/Lisbon')
    client = Client()
    client.force_login(me)

    response = visit(the_token=token(email='friend@example.com'), client=client)

    assert signed_in_as(response) == 'friend'


def test_an_old_login_does_not_replace_the_token(me):
    client = Client()
    client.force_login(me)

    assert visit(client=client).status_code == 403


@pytest.mark.parametrize('host', [CLOUDFLARE_HOST, f'{CLOUDFLARE_HOST}:8443', f'{CLOUDFLARE_HOST}.', 'COUCHLOG.example.com'])
@pytest.mark.parametrize('path', ['/admin/', '/admin/login/', '/admin/auth/user/'])
def test_admin_is_refused_on_the_cloudflare_address(me, settings, path, host):
    settings.ALLOWED_HOSTS = [CLOUDFLARE_HOST, f'{CLOUDFLARE_HOST}.']

    response = visit(path, token(), host=host)

    assert response.status_code == 403
    assert b'home address' in response.content


def test_admin_works_on_the_home_address(me):
    client = Client()
    client.force_login(me)

    assert visit('/admin/', client=client, host=HOME_HOST).status_code == 200


def test_the_password_form_is_not_used_on_the_cloudflare_address(me):
    client = Client()

    response = client.post(
        '/login/',
        {'username': 'made-up-owner', 'password': PASSWORD},
        HTTP_HOST=CLOUDFLARE_HOST,
        HTTP_CF_ACCESS_JWT_ASSERTION=token(email='friend@example.com'),
    )

    assert response.status_code == 302
    assert response['Location'] == '/'
    assert '_auth_user_id' not in client.session
    assert visit('/login/', token()).status_code == 302


def test_the_password_form_without_a_token_is_refused_on_the_cloudflare_address(me):
    client = Client()

    response = client.post(
        '/login/', {'username': 'made-up-owner', 'password': PASSWORD}, HTTP_HOST=CLOUDFLARE_HOST
    )

    assert response.status_code == 403
    assert '_auth_user_id' not in client.session


def test_the_password_login_works_on_the_home_address(me):
    client = Client()

    response = client.post('/login/', {'username': 'made-up-owner', 'password': PASSWORD}, HTTP_HOST=HOME_HOST)

    assert response.status_code == 302
    assert visit(client=client, host=HOME_HOST).status_code == 200


def test_a_header_at_the_home_address_signs_nobody_in(me):
    # Even a token Cloudflare really signed does nothing here.
    response = visit(the_token=token(), host=HOME_HOST)

    assert response.status_code == 302
    assert response['Location'].startswith('/login/')


def test_a_header_at_the_home_address_creates_no_account(db):
    visit(the_token=token(email='stranger@example.com'), host=HOME_HOST)

    assert not User.objects.exists()


def test_my_account_signed_in_both_ways_sees_the_same_history(me):
    title = Title.objects.create(kind='movie', tmdb_id=603, title='Made-up Movie')
    Watch.objects.create(user=me, title=title, watched_on=datetime.date(2026, 10, 1))
    at_home = Client()
    at_home.post('/login/', {'username': 'made-up-owner', 'password': PASSWORD}, HTTP_HOST=HOME_HOST)

    from_outside = visit('/movies/history/', token())
    from_home = visit('/movies/history/', client=at_home, host=HOME_HOST)

    assert b'Made-up Movie' in from_outside.content
    assert b'Made-up Movie' in from_home.content


def test_a_new_friend_does_not_see_my_data(me):
    title = Title.objects.create(kind='movie', tmdb_id=603, title='Made-up Movie')
    Watch.objects.create(user=me, title=title, watched_on=datetime.date(2026, 10, 1))
    friend = User.objects.create_user(username='friend', email='friend@example.com')
    Profile.objects.create(user=friend, timezone='Europe/Lisbon')

    response = visit('/movies/history/', token(email='friend@example.com'))

    assert signed_in_as(response) == 'friend'
    assert b'Made-up Movie' not in response.content


def test_a_form_is_accepted_on_the_cloudflare_address(me):
    # With Django's real protection against forged requests, which the normal test client switches off.
    the_token = token()
    client = Client(enforce_csrf_checks=True)
    visit(the_token=the_token, client=client)

    response = client.post(
        '/profile/',
        {'timezone': 'Europe/Paris', 'csrfmiddlewaretoken': client.cookies['csrftoken'].value},
        HTTP_HOST=CLOUDFLARE_HOST,
        HTTP_ORIGIN=f'https://{CLOUDFLARE_HOST}',
        HTTP_CF_ACCESS_JWT_ASSERTION=the_token,
    )

    assert response.status_code == 302
    assert Profile.objects.get(user=me).timezone == 'Europe/Paris'


def test_log_out_on_the_cloudflare_address_ends_cloudflares_session(me):
    response = Client().post('/logout/', HTTP_HOST=CLOUDFLARE_HOST, HTTP_CF_ACCESS_JWT_ASSERTION=token())

    assert response.status_code == 302
    assert response['Location'] == '/cdn-cgi/access/logout'


def test_log_out_on_the_home_address_goes_to_the_login_page(me):
    client = Client()
    client.force_login(me)

    response = client.post('/logout/', HTTP_HOST=HOME_HOST)

    assert response['Location'] == '/login/'
    assert visit(client=client, host=HOME_HOST).status_code == 302


def test_an_account_made_by_mistake_can_be_deleted_and_my_data_stays(me):
    # Signing in changes none of my data. The one thing it adds, an account, can be taken back in /admin/.
    title = Title.objects.create(kind='movie', tmdb_id=603, title='Made-up Movie')
    watch = Watch.objects.create(user=me, title=title, watched_on=datetime.date(2026, 10, 1))
    visit(the_token=token(email='mistake@example.com'))
    mistake = User.objects.get(username='mistake@example.com')
    at_home = Client()
    at_home.force_login(me)

    response = at_home.post(f'/admin/auth/user/{mistake.pk}/delete/', {'post': 'yes'}, HTTP_HOST=HOME_HOST)

    assert response.status_code == 302
    assert not User.objects.filter(username='mistake@example.com').exists()
    assert list(Watch.objects.all()) == [watch]


def test_an_account_made_by_mistake_can_be_deactivated(me):
    visit(the_token=token(email='mistake@example.com'))
    User.objects.filter(username='mistake@example.com').update(is_active=False)

    assert visit(the_token=token(email='mistake@example.com')).status_code == 403


def test_with_the_settings_empty_the_sign_in_is_off(me, settings):
    settings.CLOUDFLARE_ACCESS_TEAM_DOMAIN = ''
    settings.CLOUDFLARE_ACCESS_AUD = ''
    settings.CLOUDFLARE_ACCESS_ADDRESS = ''
    client = Client()

    # A token does nothing, and the address behaves like any other.
    assert visit(the_token=token(), client=client).status_code == 302
    client.post('/login/', {'username': 'made-up-owner', 'password': PASSWORD}, HTTP_HOST=CLOUDFLARE_HOST)
    assert visit(client=client).status_code == 200


def test_the_settings_are_read_from_the_environment():
    result = run_python(
        READ_THE_SETTINGS,
        CLOUDFLARE_ACCESS_TEAM_DOMAIN=TEAM_DOMAIN,
        CLOUDFLARE_ACCESS_AUD=AUDIENCE,
        CLOUDFLARE_ACCESS_ADDRESS='Couchlog.Example.com',
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == [TEAM_DOMAIN, AUDIENCE, CLOUDFLARE_HOST]


def test_the_settings_are_all_empty_by_default():
    result = run_python(READ_THE_SETTINGS, **ALL_EMPTY)

    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == []


@pytest.mark.parametrize(
    'filled_in',
    [
        {'CLOUDFLARE_ACCESS_TEAM_DOMAIN': TEAM_DOMAIN},
        {'CLOUDFLARE_ACCESS_AUD': AUDIENCE},
        {'CLOUDFLARE_ACCESS_ADDRESS': CLOUDFLARE_HOST},
        {'CLOUDFLARE_ACCESS_TEAM_DOMAIN': TEAM_DOMAIN, 'CLOUDFLARE_ACCESS_AUD': AUDIENCE},
    ],
    ids=['only team', 'only audience', 'only address', 'address missing'],
)
def test_half_filled_settings_refuse_to_start(filled_in):
    result = run_python(READ_THE_SETTINGS, **{**ALL_EMPTY, **filled_in})

    assert result.returncode != 0
    assert 'CLOUDFLARE_ACCESS_' in result.stderr


def test_an_address_written_with_https_refuses_to_start():
    result = run_python(
        READ_THE_SETTINGS,
        CLOUDFLARE_ACCESS_TEAM_DOMAIN=TEAM_DOMAIN,
        CLOUDFLARE_ACCESS_AUD=AUDIENCE,
        CLOUDFLARE_ACCESS_ADDRESS=f'https://{CLOUDFLARE_HOST}',
    )

    assert result.returncode != 0
    assert 'without https://' in result.stderr
