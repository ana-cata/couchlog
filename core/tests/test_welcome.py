"""The welcome page (docs/welcome.md): a new account sees it once, an existing one never by itself, About opens it."""

import pytest
from django.contrib.auth.models import User
from django.contrib.staticfiles import finders
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from core.models import Profile

PAGES = ['/', '/search/', '/movies/', '/series/watching/', '/calendar/', '/about/']
PICTURES = [
    '1-search.jpg',
    '2-to-watch.jpg',
    '3-movie.jpg',
    '4-series-top.jpg',
    '5-series-seasons.jpg',
    '6-lists.jpg',
    '7-home.jpg',
    '8-calendar.jpg',
    '9-profile.jpg',
]
STEPS = [
    '1. Find a title',
    '2. Keep it for later',
    "3. A movie's page",
    "4. A series' page",
    '5. Your lists',
    '6. Home',
    '7. Calendar',
    '8. Profile',
]


@pytest.fixture
def new_account(client, db):
    """An account signing in for the first time, the way it happens at home: no Profile row yet."""
    user = User.objects.create_user(username='made-up-new-friend', password='made-up-password')
    client.force_login(user)
    return user


@pytest.fixture
def old_account(client, db):
    """An account that already uses Couchlog: its Profile row was there before the welcome page existed."""
    user = User.objects.create_user(username='made-up-old-friend', password='made-up-password')
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    client.force_login(user)
    return user


def seen(user):
    return Profile.objects.get(user=user).welcome_seen


def test_a_new_account_sees_the_welcome_page_once_after_its_time_zone(client, new_account):
    assert client.get('/')['Location'] == '/profile/'

    response = client.post('/profile/', {'timezone': 'Europe/Lisbon'})
    assert response['Location'] == '/welcome/'
    assert not seen(new_account)
    # Until it is opened, every other page leads to it.
    for page in PAGES:
        assert client.get(page)['Location'] == '/welcome/'

    page = client.get('/welcome/').content.decode()
    assert all(step in page for step in STEPS)
    assert seen(new_account)

    # Never again by itself.
    for page in PAGES:
        assert client.get(page).status_code == 200
    assert client.post('/profile/', {'timezone': 'Europe/Paris'})['Location'] == '/profile/'


def test_profile_and_log_out_stay_open_before_the_welcome_page(client, new_account):
    Profile.objects.create(user=new_account, timezone='Europe/Lisbon', welcome_seen=False)

    assert client.get('/profile/').status_code == 200
    assert client.post('/logout/').status_code == 302
    assert not seen(new_account)


def test_skip_and_start_both_go_home_and_the_page_counts_as_seen(client, new_account):
    Profile.objects.create(user=new_account, timezone='Europe/Lisbon', welcome_seen=False)

    page = client.get('/welcome/').content.decode()

    # Skip is a quiet button at the top, Start the page's one main button at the end.
    assert '<a href="/" role="button" class="outline secondary">Skip</a>' in page
    assert '<a href="/" role="button">Start using Couchlog</a>' in page
    assert page.index('>Skip<') < page.index('<h1>') < page.index('>Start using Couchlog<')
    assert seen(new_account)
    assert client.get('/').status_code == 200


def test_an_existing_account_never_sees_it_by_itself(client, old_account):
    assert seen(old_account)
    for page in PAGES:
        assert client.get(page).status_code == 200


def test_about_opens_the_welcome_page_at_any_time(client, old_account):
    assert 'href="/welcome/">How Couchlog works</a>' in client.get('/about/').content.decode()

    before = list(Profile.objects.values())
    page = client.get('/welcome/').content.decode()

    assert all(step in page for step in STEPS)
    # Reading it again changes nothing.
    assert list(Profile.objects.values()) == before


def test_the_welcome_page_is_open_without_a_login(client, db):
    assert 'href="/welcome/">How Couchlog works</a>' in client.get('/about/').content.decode()

    response = client.get('/welcome/')

    assert response.status_code == 200
    assert all(step in response.content.decode() for step in STEPS)
    assert not Profile.objects.exists()


def test_each_step_has_its_picture_with_words_for_screen_readers(client, db):
    page = client.get('/welcome/').content.decode()

    for picture in PICTURES:
        assert finders.find(f'core/welcome/{picture}')
        assert f'src="/static/core/welcome/{picture}"' in page
    assert page.count('class="welcome-picture"') == len(PICTURES)
    assert 'alt=""' not in page
    # Each picture has its size, so the page keeps room for it while it loads.
    assert page.count('<img width="390" height="') == len(PICTURES)


def test_the_tmdb_credit_stays_on_about(client, db):
    assert 'This product uses the TMDB API but is not endorsed or certified by TMDB.' in client.get('/about/').content.decode()


@pytest.mark.django_db(transaction=True)
def test_accounts_that_existed_before_the_migration_count_as_seen():
    before, after = [('core', '0016_demo_event')], [('core', '0017_profile_welcome_seen')]
    executor = MigrationExecutor(connection)
    executor.migrate(before)
    old_apps = executor.loader.project_state(before).apps
    user = old_apps.get_model('auth', 'User').objects.create(username='made-up-existing-friend')
    old_apps.get_model('core', 'Profile').objects.create(user=user, timezone='Europe/Lisbon')

    executor = MigrationExecutor(connection)
    executor.migrate(after)

    new_apps = executor.loader.project_state(after).apps
    assert new_apps.get_model('core', 'Profile').objects.get(user_id=user.id).welcome_seen
    # Back to the latest tables for the other tests.
    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())
